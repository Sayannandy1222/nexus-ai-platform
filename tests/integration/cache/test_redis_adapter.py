import asyncio

import pytest

from nexus.cache.adapters.redis import RedisCacheAdapter
from nexus.core.config import Settings


@pytest.fixture
def redis_settings() -> Settings:
    return Settings(
        redis_url="redis://localhost:6379/0",
    )


@pytest.mark.asyncio
async def test_redis_increment_is_atomic_and_ttl_bounded(
    redis_settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(redis_settings)

    key = "nexus:v1:test:integration:counter"

    try:
        await adapter.delete(key)

        first = await adapter.increment(
            key,
            ttl_seconds=60,
        )

        second = await adapter.increment(
            key,
            ttl_seconds=60,
        )

        value = await adapter.get(key)
        ttl = await adapter.ttl(key)

        assert first == 1
        assert second == 2
        assert value == "2"

        assert 0 < ttl <= 60

    finally:
        await adapter.delete(key)
        await adapter.close()


@pytest.mark.asyncio
async def test_redis_increment_initializes_ttl_only_on_first_write(
    redis_settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(redis_settings)

    key = "nexus:v1:test:integration:ttl"

    try:
        await adapter.delete(key)

        first = await adapter.increment(
            key,
            ttl_seconds=60,
        )

        assert first == 1

        ttl_after_first = await adapter.ttl(key)

        assert 0 < ttl_after_first <= 60

        await asyncio.sleep(2)

        second = await adapter.increment(
            key,
            ttl_seconds=60,
        )

        assert second == 2

        ttl_after_second = await adapter.ttl(key)

        assert 0 < ttl_after_second < ttl_after_first

    finally:
        await adapter.delete(key)
        await adapter.close()


@pytest.mark.asyncio
async def test_redis_ttl_returns_missing_key_state(
    redis_settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(redis_settings)

    key = "nexus:v1:test:integration:missing"

    try:
        await adapter.delete(key)

        ttl = await adapter.ttl(key)

        assert ttl == -2

    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_redis_delete_removes_key(
    redis_settings: Settings,
) -> None:
    adapter = RedisCacheAdapter.from_settings(redis_settings)

    key = "nexus:v1:test:integration:delete"

    try:
        await adapter.set(
            key,
            "test",
            ttl_seconds=60,
        )

        assert await adapter.exists(key)

        deleted = await adapter.delete(key)

        assert deleted == 1
        assert not await adapter.exists(key)

    finally:
        await adapter.delete(key)
        await adapter.close()
