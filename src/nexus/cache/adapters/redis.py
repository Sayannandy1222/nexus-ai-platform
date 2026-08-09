from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from nexus.cache.adapters.protocol import CacheStore
from nexus.core.config import Settings


class RedisCacheAdapter(CacheStore):
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

        return bool(
            await self._client.set(
                key,
                value,
                ex=ttl_seconds,
            )
        )

    async def delete(self, key: str) -> int:
        return int(await self._client.delete(key))

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(key))

    async def close(self) -> None:
        await self._client.aclose()
