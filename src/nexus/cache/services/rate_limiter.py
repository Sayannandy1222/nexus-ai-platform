from __future__ import annotations

from dataclasses import dataclass
from time import time

from nexus.cache.adapters.protocol import CacheStore
from nexus.cache.keys import (
    rate_limit_hour_key,
    rate_limit_minute_key,
)
from nexus.core.config import Settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    minute_count: int
    hour_count: int
    minute_limit: int
    hour_limit: int
    retry_after_seconds: int


class RateLimiter:
    """
    Distributed rate limiter backed by Redis/Valkey.

    Design goals:
    - Safe under concurrent API workers.
    - Atomic Redis increments.
    - Bounded rate-limit keys through TTLs.
    - No local process state.
    - Horizontally scalable.
    """

    MINUTE_WINDOW_SECONDS = 60
    HOUR_WINDOW_SECONDS = 3600

    def __init__(
        self,
        store: CacheStore,
        settings: Settings,
    ) -> None:
        self._store = store
        self._minute_limit = settings.rate_limit_per_minute
        self._hour_limit = settings.rate_limit_per_hour

        if self._minute_limit <= 0:
            raise ValueError(
                "rate limit per minute must be positive",
            )

        if self._hour_limit <= 0:
            raise ValueError(
                "rate limit per hour must be positive",
            )

    async def check(self, user_id: str) -> RateLimitResult:
        now = int(time())

        minute_bucket = now // self.MINUTE_WINDOW_SECONDS
        hour_bucket = now // self.HOUR_WINDOW_SECONDS

        minute_key = rate_limit_minute_key(
            user_id,
            minute_bucket,
        )

        hour_key = rate_limit_hour_key(
            user_id,
            hour_bucket,
        )

        minute_count = await self._store.increment(
            minute_key,
            ttl_seconds=self.MINUTE_WINDOW_SECONDS,
        )

        hour_count = await self._store.increment(
            hour_key,
            ttl_seconds=self.HOUR_WINDOW_SECONDS,
        )

        minute_exceeded = minute_count > self._minute_limit
        hour_exceeded = hour_count > self._hour_limit

        allowed = not minute_exceeded and not hour_exceeded

        retry_after_seconds = 0

        if minute_exceeded:
            retry_after_seconds = self.MINUTE_WINDOW_SECONDS - (now % self.MINUTE_WINDOW_SECONDS)

        if hour_exceeded:
            hour_retry = self.HOUR_WINDOW_SECONDS - (now % self.HOUR_WINDOW_SECONDS)

            retry_after_seconds = max(
                retry_after_seconds,
                hour_retry,
            )

        return RateLimitResult(
            allowed=allowed,
            minute_count=minute_count,
            hour_count=hour_count,
            minute_limit=self._minute_limit,
            hour_limit=self._hour_limit,
            retry_after_seconds=retry_after_seconds,
        )
