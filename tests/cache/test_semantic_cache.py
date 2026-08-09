import pytest

from nexus.cache.services.semantic_cache import SemanticCache
from nexus.core.config import Settings


class FakeCacheStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, int | None]] = {}
        self.last_set_ttl: int | None = None

    async def get(self, key: str) -> str | None:
        value = self.values.get(key)
        return value[0] if value else None

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        self.values[key] = (value, ttl_seconds)
        self.last_set_ttl = ttl_seconds
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    store = FakeCacheStore()
    cache = SemanticCache(store, Settings())

    result = await cache.get("hello")

    assert result is None


@pytest.mark.asyncio
async def test_cache_round_trip() -> None:
    store = FakeCacheStore()
    cache = SemanticCache(store, Settings())

    await cache.set("hello", "world")

    result = await cache.get("hello")

    assert result is not None
    assert result.response == "world"


@pytest.mark.asyncio
async def test_cache_normalizes_query() -> None:
    store = FakeCacheStore()
    cache = SemanticCache(store, Settings())

    await cache.set("  HELLO   WORLD  ", "cached")

    result = await cache.get("hello world")

    assert result is not None
    assert result.response == "cached"


@pytest.mark.asyncio
async def test_cache_write_has_ttl() -> None:
    store = FakeCacheStore()
    cache = SemanticCache(store, Settings())

    await cache.set("hello", "world")

    assert store.last_set_ttl == 3600


@pytest.mark.asyncio
async def test_cache_rejects_oversized_payload() -> None:
    settings = Settings(semantic_cache_max_bytes=10)
    store = FakeCacheStore()
    cache = SemanticCache(store, settings)

    with pytest.raises(ValueError, match="maximum size"):
        await cache.set("hello", "this response is too large")
