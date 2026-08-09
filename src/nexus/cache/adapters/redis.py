from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from nexus.cache.adapters.protocol import CacheStore
from nexus.core.config import Settings


class RedisCacheAdapter(CacheStore):
    """
    Redis/Valkey infrastructure adapter.

    Design goals:
    - Async/non-blocking Redis I/O.
    - Connection pooling.
    - Explicit connection and socket timeouts.
    - Atomic rate-limit increment + TTL initialization.
    - Bounded Redis state.
    - Redis implementation details isolated behind CacheStore.
    """

    _INCREMENT_WITH_TTL_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])

    if count == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end

    return count
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisCacheAdapter:
        pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=settings.redis_health_check_interval_seconds,
            decode_responses=True,
        )

        client = Redis(connection_pool=pool)

        return cls(client)

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError("Redis cache value must be a string")

        return value

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        result = await self._client.set(
            key,
            value,
            ex=ttl_seconds,
        )

        return bool(result)

    async def increment(
        self,
        key: str,
        *,
        ttl_seconds: int,
    ) -> int:
        """
        Atomically increment a counter and initialize its TTL.

        Redis/Valkey executes the Lua script server-side:

            INCR
              ↓
            if first write
              ↓
            EXPIRE

        This prevents a counter from becoming permanent if INCR
        succeeds but EXPIRE fails at the application layer.
        """

        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        result: Any = self._client.eval(
            self._INCREMENT_WITH_TTL_SCRIPT,
            1,
            key,
            str(ttl_seconds),
        )

        result = await cast(Any, result)

        return int(result)

    async def ttl(self, key: str) -> int:
        """
        Return remaining TTL in seconds.

        Redis semantics:
        - >= 0: remaining TTL
        - -1: key exists but has no expiration
        - -2: key does not exist
        """

        return int(await self._client.ttl(key))

    async def delete(self, key: str) -> int:
        return int(await self._client.delete(key))

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def close(self) -> None:
        await self._client.aclose()
