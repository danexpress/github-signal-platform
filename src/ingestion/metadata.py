"""Ingestion metadata — the source of truth for what's been processed."""

from contextlib import contextmanager
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from src.config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,             -- 'gharchive'
    partition_key VARCHAR(50) NOT NULL,      -- '2026-11-01-00'
    status VARCHAR(20) NOT NULL,             -- running, success, failed
    source_url TEXT,
    source_bytes BIGINT,
    output_s3_key TEXT,
    output_rows BIGINT,
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    UNIQUE (source, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON ingestion_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_partition ON ingestion_runs(source, partition_key);
"""


@contextmanager
def db_cursor(config: Config):
    conn = psycopg2.connect(config.metadata_db_url, cursor_factory=RealDictCursor)
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(config: Config) -> None:
    with db_cursor(config) as cur:
        cur.execute(SCHEMA)


def already_succeeded(config: Config, source: str, partition_key: str) -> bool:
    """Idempotency check — don't re-run successful partitions."""
    with db_cursor(config) as cur:
        cur.execute(
            """
            SELECT 1 FROM ingestion_runs
            WHERE source = %s AND partition_key = %s AND status = 'success'
            """,
            (source, partition_key),
        )
        return cur.fetchone() is not None


def start_run(config: Config, source: str, partition_key: str, source_url: str) -> int:
    with db_cursor(config) as cur:
        cur.execute(
            """
            INSERT INTO ingestion_runs (source, partition_key, status, source_url)
            VALUES (%s, %s, 'running', %s)
            ON CONFLICT (source, partition_key) DO UPDATE
                SET status = 'running',
                    source_url = EXCLUDED.source_url,
                    started_at = NOW(),
                    error_message = NULL
            RETURNING id
            """,
            (source, partition_key, source_url),
        )
        return cur.fetchone()["id"]


def finish_run(
    config: Config,
    run_id: int,
    *,
    output_s3_key: str,
    output_rows: int,
    source_bytes: int
) -> None:
    with db_cursor(config) as cur:
        cur.execute(
            """
            UPDATE ingestion_runs
            SET status = 'success', output_s3_key = %s, output_rows = %s,
                source_bytes = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (output_s3_key, output_rows, source_bytes, run_id),
        )


def fail_run(config: Config, run_id: int, error: str) -> None:
    with db_cursor(config) as cur:
        cur.execute(
            """
            UPDATE ingestion_runs
            SET status = 'failed', error_message = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (error[:5000], run_id),
        )
