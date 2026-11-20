"""Pick which silver actors to enrich, fetch their profiles, hand rows to the store."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import duckdb

from src.config import Config
from src.enrichment.github_client import GitHubClient

if TYPE_CHECKING:
    from src.enrichment.store import DimActorsStore

logger = logging.getLogger(__name__)

# Push-only actors are excluded: too many (~400k/day) and low value for
# trending. These are the events that express interest in or contribution to
# someone else's repo.
ENRICH_EVENT_TYPES = ("WatchEvent", "ForkEvent", "PullRequestEvent")


@dataclass(frozen=True)
class Candidate:
    actor_id: int
    actor_login: str
    event_count: int


@dataclass(frozen=True)
class ActorProfile:
    """Fields extracted from GET /user/{id}. The raw response is discarded."""

    actor_id: int
    status: str  # found | missing
    login: str | None = None
    user_type: str | None = None
    account_created_at: datetime | None = None
    followers: int | None = None
    following: int | None = None
    public_repos: int | None = None
    has_bio: bool | None = None
    has_company: bool | None = None
    has_location: bool | None = None
    has_custom_avatar: bool | None = None
    _enriched_at: datetime | None = None

    def as_row(self) -> dict:
        return asdict(self)


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def _parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def fetch_actor(
    client: GitHubClient, actor_id: int, *, now: datetime | None = None
) -> ActorProfile:
    """Fetch one actor. 404 → status='missing' (deleted/suspended), not an error."""
    enriched_at = now or datetime.now(UTC)
    user = client.get_user(actor_id)
    if user is None:
        return ActorProfile(actor_id=actor_id, status="missing", _enriched_at=enriched_at)

    return ActorProfile(
        actor_id=actor_id,
        status="found",
        login=user.get("login"),
        user_type=user.get("type"),
        account_created_at=_parse_ts(user.get("created_at")),
        followers=user.get("followers"),
        following=user.get("following"),
        public_repos=user.get("public_repos"),
        has_bio=_present(user.get("bio")),
        has_company=_present(user.get("company")),
        has_location=_present(user.get("location")),
        has_custom_avatar=client.has_custom_avatar(user.get("avatar_url")),
        _enriched_at=enriched_at,
    )


def _duckdb(config: Config) -> duckdb.DuckDBPyConnection:
    endpoint = urlparse(config.s3_endpoint)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET lake (TYPE S3, KEY_ID ?, SECRET ?, REGION ?, "
        "ENDPOINT ?, URL_STYLE 'path', USE_SSL ?)",
        [
            config.s3_access_key,
            config.s3_secret_key,
            config.s3_region,
            endpoint.netloc or endpoint.path,
            endpoint.scheme == "https",
        ],
    )
    return con


def select_candidates(
    config: Config, *, exclude: set[int], max_actors: int | None = None
) -> tuple[int, list[Candidate]]:
    """Human actors with Watch/Fork/PR events, busiest first, minus `exclude`.

    Returns (total_in_scope, candidates_to_fetch).
    """
    placeholders = ", ".join("?" for _ in ENRICH_EVENT_TYPES)
    rows = _duckdb(config).execute(
        f"""
        select actor_id, arg_max(actor_login, created_at) as actor_login, count(*) as n
        from read_parquet('s3://{config.s3_raw_bucket}/silver/events')
        where event_type in ({placeholders})
          and not actor_is_bot
          and actor_id is not null
        group by actor_id
        order by n desc, actor_id
        """,
        list(ENRICH_EVENT_TYPES),
    ).fetchall()
    candidates = [Candidate(a, login, n) for a, login, n in rows if a not in exclude]
    if max_actors is not None:
        candidates = candidates[:max_actors]
    return len(rows), candidates


def enrich(
    client: GitHubClient,
    store: DimActorsStore,
    candidates: Iterable[Candidate],
    *,
    progress_every: int = 100,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Fetch sequentially, upserting each actor as soon as it's fetched."""
    candidates = list(candidates)
    stats = {"found": 0, "missing": 0}
    started = clock()
    for i, cand in enumerate(candidates, start=1):
        profile = fetch_actor(client, cand.actor_id)
        store.upsert(profile)
        stats[profile.status] += 1

        if i % progress_every == 0 or i == len(candidates):
            elapsed = clock() - started
            rate = i / elapsed if elapsed else 0.0
            eta_min = (len(candidates) - i) / rate / 60 if rate else 0.0
            budget = (
                f"{client.rate_limit.remaining}/{client.rate_limit.limit}"
                if client.rate_limit
                else "?"
            )
            logger.info(
                "%d/%d actors | %.1f/s | ETA %.0f min | found=%d missing=%d | API budget %s",
                i, len(candidates), rate, eta_min, stats["found"], stats["missing"], budget,
            )
    return stats
