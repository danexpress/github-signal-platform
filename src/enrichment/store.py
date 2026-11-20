"""Postgres-backed dim_actors: one row per enriched actor, upserted in place."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Self

import psycopg2
from psycopg2 import sql

from src.enrichment.actor_fetcher import ActorProfile

DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.dim_actors (
    actor_id            BIGINT PRIMARY KEY,
    status              VARCHAR(10) NOT NULL CHECK (status IN ('found', 'missing')),
    login               TEXT,
    user_type           TEXT,            -- User | Organization | Bot
    account_created_at  TIMESTAMPTZ,
    followers           INTEGER,
    following           INTEGER,
    public_repos        INTEGER,
    has_bio             BOOLEAN,
    has_company         BOOLEAN,
    has_location        BOOLEAN,
    has_custom_avatar   BOOLEAN,         -- NULL = couldn't determine
    _enriched_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS dim_actors_enriched_at_idx
    ON {schema}.dim_actors (_enriched_at);
"""

COLUMNS = [
    "actor_id",
    "status",
    "login",
    "user_type",
    "account_created_at",
    "followers",
    "following",
    "public_repos",
    "has_bio",
    "has_company",
    "has_location",
    "has_custom_avatar",
    "_enriched_at",
]


class DimActorsStore:
    """Writes are autocommitted one actor at a time, so a crash mid-run loses
    at most the actor in flight; the next run's freshness filter resumes."""

    def __init__(self, db_url: str, *, schema: str = "public"):
        self._schema = sql.Identifier(schema)
        self._conn = psycopg2.connect(db_url)
        self._conn.autocommit = True

    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql.SQL(DDL).format(schema=self._schema))

    def upsert(self, profile: ActorProfile) -> None:
        query = sql.SQL(
            "INSERT INTO {schema}.dim_actors ({cols}) VALUES ({vals}) "
            "ON CONFLICT (actor_id) DO UPDATE SET {updates}"
        ).format(
            schema=self._schema,
            cols=sql.SQL(", ").join(map(sql.Identifier, COLUMNS)),
            vals=sql.SQL(", ").join(sql.Placeholder(c) for c in COLUMNS),
            updates=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c))
                for c in COLUMNS
                if c != "actor_id"
            ),
        )
        with self._conn.cursor() as cur:
            cur.execute(query, profile.as_row())

    def fresh_actor_ids(self, ttl_days: int, *, now: datetime | None = None) -> set[int]:
        """Actors enriched within the TTL — skipped by the next run."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=ttl_days)
        with self._conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT actor_id FROM {schema}.dim_actors WHERE _enriched_at > %s").format(
                    schema=self._schema
                ),
                (cutoff,),
            )
            return {row[0] for row in cur.fetchall()}

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {schema}.dim_actors").format(schema=self._schema))
            return cur.fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
