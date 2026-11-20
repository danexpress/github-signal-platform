"""Thin GitHub REST client: rate-limit aware, retries 5xx/network errors."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.github.com"

# GitHub serves default identicons from a generator whose output carries this
# Last-Modified date; uploaded avatars carry their upload time instead.
IDENTICON_LAST_MODIFIED_DATE = "12 Nov 2016"


class ServerError(Exception):
    """5xx from GitHub — transient, retry."""


class RateLimited(Exception):
    """403/429 rate-limit response — we've already slept; retry."""


@dataclass
class RateLimitState:
    limit: int
    remaining: int
    reset_at: int  # epoch seconds

    @classmethod
    def from_headers(cls, headers: httpx.Headers) -> RateLimitState | None:
        try:
            return cls(
                limit=int(headers["X-RateLimit-Limit"]),
                remaining=int(headers["X-RateLimit-Remaining"]),
                reset_at=int(headers["X-RateLimit-Reset"]),
            )
        except (KeyError, ValueError):
            return None


class GitHubClient:
    """REST client for the handful of endpoints enrichment needs.

    Rate limiting is proactive: after every response we record the
    X-RateLimit-* headers, and before the next request we sleep until reset if
    the remaining budget has dropped below `min_remaining`. A 403/429 that slips
    through (e.g. secondary limits) sleeps for Retry-After or until reset, then
    retries.
    """

    def __init__(
        self,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        min_remaining: int = 1,
        max_attempts: int = 6,
        retry_wait: wait_base | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-signal-platform",
        }
        self._api = httpx.Client(
            base_url=API_BASE_URL,
            headers={**headers, "Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=30,
        )
        # Separate client so the token is never sent to the avatar CDN.
        self._cdn = httpx.Client(
            headers={"User-Agent": headers["User-Agent"]},
            transport=transport,
            timeout=15,
            follow_redirects=True,
        )
        self._sleep = sleep
        self._clock = clock
        self._min_remaining = min_remaining
        self._retrying = Retrying(
            retry=retry_if_exception_type((ServerError, RateLimited, httpx.TransportError)),
            stop=stop_after_attempt(max_attempts),
            wait=retry_wait or wait_exponential(min=1, max=60),
            reraise=True,
        )
        self.rate_limit: RateLimitState | None = None

    # ------------------------------------------------------------ rate limits

    def _sleep_until_reset(self, reason: str) -> None:
        reset_at = self.rate_limit.reset_at if self.rate_limit else self._clock() + 60
        wait = max(0.0, reset_at - self._clock()) + 1
        logger.warning("%s; sleeping %.0fs until rate-limit reset", reason, wait)
        self._sleep(wait)

    def _wait_for_budget(self) -> None:
        if self.rate_limit and self.rate_limit.remaining < self._min_remaining:
            self._sleep_until_reset(
                f"Rate-limit budget at {self.rate_limit.remaining}/{self.rate_limit.limit}"
            )
            self.rate_limit = None  # unknown until the next response tells us

    def _handle_rate_limited(self, resp: httpx.Response) -> None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            logger.warning("Secondary rate limit; sleeping %ss", retry_after)
            self._sleep(float(retry_after) + 1)
        else:
            self._sleep_until_reset(f"HTTP {resp.status_code} rate limited")
        self.rate_limit = None
        raise RateLimited(f"HTTP {resp.status_code}")

    @staticmethod
    def _is_rate_limited(resp: httpx.Response) -> bool:
        if resp.status_code == 429:
            return True
        return resp.status_code == 403 and (
            resp.headers.get("X-RateLimit-Remaining") == "0"
            or "Retry-After" in resp.headers
        )

    # ---------------------------------------------------------------- requests

    def _get_once(self, path: str) -> httpx.Response:
        self._wait_for_budget()
        resp = self._api.get(path)
        self.rate_limit = RateLimitState.from_headers(resp.headers) or self.rate_limit
        if resp.status_code >= 500:
            raise ServerError(f"HTTP {resp.status_code} for {path}")
        if self._is_rate_limited(resp):
            self._handle_rate_limited(resp)
        return resp

    def get(self, path: str) -> httpx.Response:
        return self._retrying(self._get_once, path)

    def get_user(self, user_id: int) -> dict | None:
        """GET /user/{id}. Lookup by id, so renamed accounts still resolve.

        Returns None for 404 (deleted, suspended, or never existed).
        """
        resp = self.get(f"/user/{int(user_id)}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def has_custom_avatar(self, avatar_url: str | None) -> bool | None:
        """HEAD the avatar; default identicons have a fixed 2016 Last-Modified.

        Returns None if it can't be determined (network error, no header).
        CDN requests don't count against the API rate limit.
        """
        if not avatar_url:
            return None
        try:
            resp = self._cdn.head(avatar_url)
        except httpx.HTTPError as e:
            logger.debug("Avatar HEAD failed for %s: %s", avatar_url, e)
            return None
        last_modified = resp.headers.get("Last-Modified")
        if resp.status_code != 200 or not last_modified:
            return None
        return IDENTICON_LAST_MODIFIED_DATE not in last_modified

    def close(self) -> None:
        self._api.close()
        self._cdn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
