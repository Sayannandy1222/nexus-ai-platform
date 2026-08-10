from __future__ import annotations

from typing import Any

from redis.asyncio import Redis

from nexus.cache.adapters.memory_protocol import SessionMemoryStore
from nexus.core.config import Settings


class RedisSessionMemoryAdapter(SessionMemoryStore):
    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisSessionMemoryAdapter:
        client = Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=settings.redis_health_check_interval_seconds,
            decode_responses=True,
        )

        return cls(client)

    async def append_bounded(
        self,
        key: str,
        value: str,
        *,
        max_items: int,
        ttl_seconds: int,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")

        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        async with self._client.pipeline(transaction=True) as pipeline:
            pipeline.rpush(key, value)
            pipeline.ltrim(key, -max_items, -1)
            pipeline.expire(key, ttl_seconds)

            execute_result: Any = pipeline.execute()
            await execute_result

    async def get_recent(
        self,
        key: str,
        *,
        max_items: int,
    ) -> list[str]:
        if max_items <= 0:
            raise ValueError("max_items must be positive")

        values: Any = self._client.lrange(
            key,
            -max_items,
            -1,
        )

        result = await values

        return [str(value) for value in result]

    async def delete(self, key: str) -> int:
        result: Any = self._client.delete(key)
        return int(await result)

    async def close(self) -> None:
        result: Any = self._client.aclose()
        await result
