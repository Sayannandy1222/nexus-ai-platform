from __future__ import annotations

import time

import pytest

from nexus.cache.adapters.redis import RedisCacheAdapter
from nexus.cache.keys import (
    rate_limit_hour_key,
    rate_limit_minute_key,
)
from nexus.cache.services.rate_limiter import RateLimiter
from nexus.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        redis_url="redis://localhost:6379/0",
        rate_limit_per_minute=3,
        rate_limit_per_hour=10,
    )


@pytest.mark.asyncio
async def test_rate_limiter_works_with_real_valkey(
    settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(settings)
    limiter = RateLimiter(adapter, settings)

    user_id = "integration-user"

    now = int(time.time())

    minute_bucket = now // 60
    hour_bucket = now // 3600

    minute_key = rate_limit_minute_key(
        user_id,
        minute_bucket,
    )

    hour_key = rate_limit_hour_key(
        user_id,
        hour_bucket,
    )

    try:
        # Ensure this integration test starts from clean state.
        await adapter.delete(minute_key)
        await adapter.delete(hour_key)

        first = await limiter.check(user_id)
        second = await limiter.check(user_id)
        third = await limiter.check(user_id)
        fourth = await limiter.check(user_id)

        assert first.allowed
        assert second.allowed
        assert third.allowed

        assert not fourth.allowed
        assert fourth.minute_count == 4

        assert fourth.retry_after_seconds > 0

    finally:
        await adapter.delete(minute_key)
        await adapter.delete(hour_key)
        await adapter.close()


@pytest.mark.asyncio
async def test_rate_limiter_creates_bounded_redis_keys(
    settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(settings)
    limiter = RateLimiter(adapter, settings)

    user_id = "ttl-integration-user"

    now = int(time.time())

    minute_bucket = now // 60
    hour_bucket = now // 3600

    minute_key = rate_limit_minute_key(
        user_id,
        minute_bucket,
    )

    hour_key = rate_limit_hour_key(
        user_id,
        hour_bucket,
    )

    try:
        await adapter.delete(minute_key)
        await adapter.delete(hour_key)

        result = await limiter.check(user_id)

        assert result.allowed

        minute_ttl = await adapter.ttl(minute_key)
        hour_ttl = await adapter.ttl(hour_key)

        assert 0 < minute_ttl <= 60
        assert 0 < hour_ttl <= 3600

    finally:
        await adapter.delete(minute_key)
        await adapter.delete(hour_key)
        await adapter.close()


@pytest.mark.asyncio
async def test_users_have_independent_real_valkey_limits(
    settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(settings)
    limiter = RateLimiter(adapter, settings)

    user_a = "real-user-a"
    user_b = "real-user-b"

    now = int(time.time())

    minute_bucket = now // 60
    hour_bucket = now // 3600

    user_a_minute_key = rate_limit_minute_key(
        user_a,
        minute_bucket,
    )

    user_a_hour_key = rate_limit_hour_key(
        user_a,
        hour_bucket,
    )

    user_b_minute_key = rate_limit_minute_key(
        user_b,
        minute_bucket,
    )

    user_b_hour_key = rate_limit_hour_key(
        user_b,
        hour_bucket,
    )

    try:
        await adapter.delete(user_a_minute_key)
        await adapter.delete(user_a_hour_key)
        await adapter.delete(user_b_minute_key)
        await adapter.delete(user_b_hour_key)

        first_a = await limiter.check(user_a)
        second_a = await limiter.check(user_a)
        third_a = await limiter.check(user_a)
        fourth_a = await limiter.check(user_a)

        first_b = await limiter.check(user_b)

        assert first_a.allowed
        assert second_a.allowed
        assert third_a.allowed
        assert not fourth_a.allowed

        assert first_b.allowed
        assert first_b.minute_count == 1
        assert first_b.hour_count == 1

    finally:
        await adapter.delete(user_a_minute_key)
        await adapter.delete(user_a_hour_key)
        await adapter.delete(user_b_minute_key)
        await adapter.delete(user_b_hour_key)
        await adapter.close()
