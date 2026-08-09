import pytest

from nexus.cache.services.rate_limiter import RateLimiter
from nexus.core.config import Settings


class FakeRateLimitStore:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        value = self.values.get(key)
        return None if value is None else str(value)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        self.values[key] = int(value)

        if ttl_seconds is not None:
            self.ttls[key] = ttl_seconds

        return True

    async def increment(
        self,
        key: str,
        *,
        ttl_seconds: int,
    ) -> int:
        value = self.values.get(key, 0) + 1
        self.values[key] = value

        if value == 1:
            self.ttls[key] = ttl_seconds

        return value

    async def delete(self, key: str) -> int:
        existed = key in self.values

        self.values.pop(key, None)
        self.ttls.pop(key, None)

        return int(existed)

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_request_within_limits_is_allowed() -> None:
    store = FakeRateLimitStore()

    settings = Settings(
        rate_limit_per_minute=3,
        rate_limit_per_hour=10,
    )

    limiter = RateLimiter(store, settings)

    result = await limiter.check("user-1")

    assert result.allowed
    assert result.minute_count == 1
    assert result.hour_count == 1


@pytest.mark.asyncio
async def test_minute_limit_blocks_request() -> None:
    store = FakeRateLimitStore()

    settings = Settings(
        rate_limit_per_minute=2,
        rate_limit_per_hour=10,
    )

    limiter = RateLimiter(store, settings)

    first = await limiter.check("user-1")
    second = await limiter.check("user-1")
    third = await limiter.check("user-1")

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.minute_count == 3


@pytest.mark.asyncio
async def test_hour_limit_blocks_request() -> None:
    store = FakeRateLimitStore()

    settings = Settings(
        rate_limit_per_minute=10,
        rate_limit_per_hour=2,
    )

    limiter = RateLimiter(store, settings)

    await limiter.check("user-1")
    await limiter.check("user-1")
    result = await limiter.check("user-1")

    assert not result.allowed
    assert result.hour_count == 3


@pytest.mark.asyncio
async def test_users_have_independent_limits() -> None:
    store = FakeRateLimitStore()

    settings = Settings(
        rate_limit_per_minute=1,
        rate_limit_per_hour=10,
    )

    limiter = RateLimiter(store, settings)

    user_one = await limiter.check("user-1")
    user_two = await limiter.check("user-2")

    assert user_one.allowed
    assert user_two.allowed


@pytest.mark.asyncio
async def test_rate_limit_counters_have_ttl() -> None:
    store = FakeRateLimitStore()

    settings = Settings(
        rate_limit_per_minute=10,
        rate_limit_per_hour=100,
    )

    limiter = RateLimiter(store, settings)

    await limiter.check("user-1")

    minute_keys = [key for key in store.ttls if ":minute:" in key]

    hour_keys = [key for key in store.ttls if ":hour:" in key]

    assert len(minute_keys) == 1
    assert len(hour_keys) == 1

    assert store.ttls[minute_keys[0]] == 60
    assert store.ttls[hour_keys[0]] == 3600


@pytest.mark.asyncio
async def test_invalid_minute_limit_is_rejected() -> None:
    store = FakeRateLimitStore()

    with pytest.raises(
        ValueError,
        match="rate limit per minute must be positive",
    ):
        RateLimiter(
            store,
            Settings(rate_limit_per_minute=0),
        )


@pytest.mark.asyncio
async def test_invalid_hour_limit_is_rejected() -> None:
    store = FakeRateLimitStore()

    with pytest.raises(
        ValueError,
        match="rate limit per hour must be positive",
    ):
        RateLimiter(
            store,
            Settings(rate_limit_per_hour=0),
        )
