"""Enrichment tests. GitHub is mocked with httpx.MockTransport — no real API calls.

The store test needs Postgres (docker compose up -d); it uses a throwaway
schema and is skipped if the database isn't reachable.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import psycopg2
import pytest
from tenacity import wait_none

from src.enrichment.actor_fetcher import ActorProfile, fetch_actor
from src.enrichment.github_client import GitHubClient

NOW = 1_800_000_000.0  # fixed fake epoch

USER_JSON = {
    "login": "octocat",
    "id": 583231,
    "type": "User",
    "created_at": "2011-01-25T18:44:36Z",
    "followers": 25280,
    "following": 9,
    "public_repos": 8,
    "bio": None,
    "company": "@github",
    "location": "  San Francisco ",
    "avatar_url": "https://avatars.githubusercontent.com/u/583231?v=4",
}


def rl_headers(remaining: int, reset: float = NOW + 30, limit: int = 5000) -> dict:
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(reset)),
    }


def make_client(handler, sleeps: list[float]) -> GitHubClient:
    return GitHubClient(
        "test-token",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        clock=lambda: NOW,
        retry_wait=wait_none(),
    )


# ---------------------------------------------------------------- rate limits


def test_sleeps_until_reset_when_budget_exhausted():
    sleeps: list[float] = []
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=USER_JSON, headers=rl_headers(remaining=0, reset=NOW + 30))

    client = make_client(handler, sleeps)
    client.get_user(1)
    assert sleeps == []  # first call: no budget info yet
    assert client.rate_limit.remaining == 0

    client.get_user(2)
    assert sleeps == [31.0]  # reset in 30s + 1s safety margin
    assert len(calls) == 2


def test_does_not_sleep_while_budget_remains():
    sleeps: list[float] = []
    client = make_client(
        lambda r: httpx.Response(200, json=USER_JSON, headers=rl_headers(remaining=4000)), sleeps
    )
    for i in range(3):
        client.get_user(i)
    assert sleeps == []
    assert client.rate_limit.remaining == 4000


def test_403_rate_limited_sleeps_then_retries():
    sleeps: list[float] = []
    responses = iter(
        [
            httpx.Response(403, json={"message": "API rate limit exceeded"},
                           headers=rl_headers(remaining=0, reset=NOW + 120)),
            httpx.Response(200, json=USER_JSON, headers=rl_headers(remaining=4999)),
        ]
    )
    client = make_client(lambda r: next(responses), sleeps)
    assert client.get_user(583231)["login"] == "octocat"
    assert sleeps == [121.0]


def test_secondary_rate_limit_honours_retry_after():
    sleeps: list[float] = []
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json=USER_JSON, headers=rl_headers(remaining=4999)),
        ]
    )
    client = make_client(lambda r: next(responses), sleeps)
    client.get_user(583231)
    assert sleeps == [8.0]


def test_retries_5xx_then_succeeds():
    sleeps: list[float] = []
    responses = iter(
        [httpx.Response(502), httpx.Response(503),
         httpx.Response(200, json=USER_JSON, headers=rl_headers(remaining=4999))]
    )
    client = make_client(lambda r: next(responses), sleeps)
    assert client.get_user(583231)["id"] == 583231


def test_token_not_sent_to_avatar_cdn():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("Authorization")
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=USER_JSON, headers=rl_headers(4999))
        return httpx.Response(200, headers={"Last-Modified": "Thu, 02 Jul 2020 15:05:28 GMT"})

    fetch_actor(make_client(handler, []), 583231)
    assert seen["api.github.com"] == "Bearer test-token"
    assert seen["avatars.githubusercontent.com"] is None


# ---------------------------------------------------------------- fetcher


def test_fetch_actor_extracts_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            assert request.url.path == "/user/583231"
            return httpx.Response(200, json=USER_JSON, headers=rl_headers(4999))
        return httpx.Response(200, headers={"Last-Modified": "Thu, 02 Jul 2020 15:05:28 GMT"})

    p = fetch_actor(make_client(handler, []), 583231)
    assert p.status == "found"
    assert p.login == "octocat"
    assert p.account_created_at == datetime(2011, 1, 25, 18, 44, 36, tzinfo=UTC)
    assert (p.followers, p.following, p.public_repos) == (25280, 9, 8)
    assert (p.has_bio, p.has_company, p.has_location) == (False, True, True)
    assert p.has_custom_avatar is True


def test_default_identicon_detected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=USER_JSON, headers=rl_headers(4999))
        return httpx.Response(200, headers={"Last-Modified": "Sat, 12 Nov 2016 06:45:13 GMT"})

    assert fetch_actor(make_client(handler, []), 583231).has_custom_avatar is False


def test_fetch_actor_404_marks_missing():
    client = make_client(
        lambda r: httpx.Response(404, json={"message": "Not Found"}, headers=rl_headers(4998)), []
    )
    p = fetch_actor(client, 999)
    assert p.status == "missing"
    assert p.actor_id == 999
    assert p.login is None and p.followers is None
    assert p._enriched_at is not None


# ---------------------------------------------------------------- store

DB_URL = os.environ.get(
    "METADATA_DB_URL", "postgresql://ghsignal:ghsignal_dev_password@localhost:5432/ghsignal_meta"
)


@pytest.fixture
def store():
    try:
        psycopg2.connect(DB_URL, connect_timeout=2).close()
    except psycopg2.OperationalError:
        pytest.skip("Postgres not reachable")
    from src.enrichment.store import DimActorsStore

    schema = f"test_{uuid.uuid4().hex[:8]}"
    s = DimActorsStore(DB_URL, schema=schema)
    s.init_schema()
    yield s, schema
    with s._conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
    s.close()


def _rows(store, schema):
    with store._conn.cursor() as cur:
        cur.execute(f'SELECT actor_id, status, followers, _enriched_at FROM "{schema}".dim_actors')
        return cur.fetchall()


def test_upsert_is_idempotent(store):
    s, schema = store
    t = datetime(2026, 11, 20, tzinfo=UTC)
    profile = ActorProfile(actor_id=1, status="found", login="a", followers=5, _enriched_at=t)

    s.upsert(profile)
    first = _rows(s, schema)
    s.upsert(profile)
    s.upsert(profile)
    assert _rows(s, schema) == first
    assert s.count() == 1


def test_upsert_updates_existing_row(store):
    s, schema = store
    t1 = datetime(2026, 10, 1, tzinfo=UTC)
    t2 = datetime(2026, 11, 20, tzinfo=UTC)
    s.upsert(ActorProfile(actor_id=1, status="found", followers=5, _enriched_at=t1))
    s.upsert(ActorProfile(actor_id=1, status="missing", _enriched_at=t2))
    assert _rows(s, schema) == [(1, "missing", None, t2)]


def test_fresh_actor_ids_respects_ttl(store):
    s, _ = store
    now = datetime(2026, 11, 20, tzinfo=UTC)
    s.upsert(ActorProfile(actor_id=1, status="found", _enriched_at=now - timedelta(days=2)))
    s.upsert(ActorProfile(actor_id=2, status="found", _enriched_at=now - timedelta(days=45)))
    assert s.fresh_actor_ids(30, now=now) == {1}
