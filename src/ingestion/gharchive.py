"""GH Archive ingestion: download hourly .json.gz → parse → write Parquet to S3."""

import gzip
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import Config
from src.storage.s3_client import get_s3_client
from src.ingestion import metadata

logger = logging.getLogger(__name__)

SOURCE = "gharchive"

# Explicit schema — never trust inferred schemas across months of data.
# GitHub adds/removes fields; we pin the fields we care about.
EVENT_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("type", pa.string()),
        ("actor_id", pa.int64()),
        ("actor_login", pa.string()),
        ("repo_id", pa.int64()),
        ("repo_name", pa.string()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("payload_json", pa.string()),  # keep raw payload for later enrichment
        ("public", pa.bool_()),
        ("org_id", pa.int64()),
        ("org_login", pa.string()),
    ]
)


@dataclass
class HourPartition:
    year: int
    month: int
    day: int
    hour: int

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}-{self.hour}"

    @property
    def s3_key(self) -> str:
        return (
            f"raw/gharchive/year={self.year:04d}/month={self.month:02d}/"
            f"day={self.day:02d}/hour={self.hour:02d}/events.parquet"
        )

    def source_url(self, base: str) -> str:
        # GH Archive uses single-digit hour, no padding
        return f"{base}/{self.year:04d}-{self.month:02d}-{self.day:02d}-{self.hour}.json.gz"


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=60))
def _download(url: str) -> bytes:
    logger.info("Downloading %s", url)
    resp = requests.get(url, timeout=120, stream=True)
    if resp.status_code == 404:
        raise FileNotFoundError(f"Not published yet: {url}")
    resp.raise_for_status()
    return resp.content


def _parse_events(raw_gz: bytes) -> Iterator[dict]:
    """Stream-parse the gzipped NDJSON. Yields one dict per event."""
    with gzip.GzipFile(fileobj=io.BytesIO(raw_gz)) as gz:
        for line_num, raw_line in enumerate(gz, start=1):
            try:
                event = json.loads(raw_line)
                yield _normalize(event)
            except json.JSONDecodeError as e:
                logger.warning("Skipping bad line %d: %s", line_num, e)
                continue


def _normalize(event: dict) -> dict:
    """Pull the fields we care about; leave the rest in payload_json."""
    actor = event.get("actor") or {}
    repo = event.get("repo") or {}
    org = event.get("org") or {}
    return {
        "id": event.get("id"),
        "type": event.get("type"),
        "actor_id": actor.get("id"),
        "actor_login": actor.get("login"),
        "repo_id": repo.get("id"),
        "repo_name": repo.get("name"),
        "created_at": event.get("created_at"),
        "payload_json": (
            json.dumps(event.get("payload")) if event.get("payload") else None
        ),
        "public": event.get("public", True),
        "org_id": org.get("id"),
        "org_login": org.get("login"),
    }


def _write_parquet(rows: list[dict], config: Config, s3_key: str) -> int:
    """Write rows as a single Parquet object to S3. Returns row count."""
    if not rows:
        return 0

    # Convert created_at strings to timestamps at Arrow-level
    for r in rows:
        if r["created_at"]:
            r["created_at"] = datetime.fromisoformat(
                r["created_at"].replace("Z", "+00:00")
            )

    table = pa.Table.from_pylist(rows, schema=EVENT_SCHEMA)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)

    client = get_s3_client(config)
    client.put_object(Bucket=config.s3_raw_bucket, Key=s3_key, Body=buf.getvalue())
    return len(rows)


def ingest_hour(
    config: Config, partition: HourPartition, *, force: bool = False
) -> dict:
    """Ingest one hour of GH Archive. Idempotent unless force=True."""
    if not force and metadata.already_succeeded(config, SOURCE, partition.key):
        logger.info("Skipping %s (already succeeded)", partition.key)
        return {"status": "skipped", "partition": partition.key}

    url = partition.source_url(config.gharchive_base_url)
    run_id = metadata.start_run(config, SOURCE, partition.key, url)

    try:
        raw_gz = _download(url)
        rows = list(_parse_events(raw_gz))
        written = _write_parquet(rows, config, partition.s3_key)

        metadata.finish_run(
            config,
            run_id,
            output_s3_key=partition.s3_key,
            output_rows=written,
            source_bytes=len(raw_gz),
        )
        logger.info(
            "Ingested %s: %d events, %d bytes", partition.key, written, len(raw_gz)
        )
        return {"status": "success", "partition": partition.key, "rows": written}

    except Exception as e:
        metadata.fail_run(config, run_id, f"{type(e).__name__}: {e}")
        logger.exception("Failed partition %s", partition.key)
        raise


def hour_range(start: datetime, end: datetime) -> Iterator[HourPartition]:
    """Yield every HourPartition from start (inclusive) to end (exclusive)."""
    current = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = end.replace(tzinfo=timezone.utc)
    while current < end:
        yield HourPartition(current.year, current.month, current.day, current.hour)
        current += timedelta(hours=1)
