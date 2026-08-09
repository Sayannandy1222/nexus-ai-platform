from __future__ import annotations

import json
from dataclasses import dataclass

from nexus.cache.adapters.protocol import CacheStore
from nexus.cache.keys import hash_text, semantic_cache_key
from nexus.core.config import Settings


@dataclass(frozen=True)
class CacheEntry:
    response: str
    source: str = "semantic_cache"


class SemanticCache:
    def __init__(
        self,
        store: CacheStore,
        settings: Settings,
    ) -> None:
        self._store = store
        self._ttl_seconds = settings.semantic_cache_ttl_seconds
        self._max_bytes = settings.semantic_cache_max_bytes

        if self._ttl_seconds <= 0:
            raise ValueError("semantic cache TTL must be positive")

        if self._max_bytes <= 0:
            raise ValueError("semantic cache max bytes must be positive")

    async def get(self, query: str) -> CacheEntry | None:
        key = semantic_cache_key(hash_text(self._normalize(query)))

        payload = await self._store.get(key)

        if payload is None:
            return None

        data = json.loads(payload)

        response = data.get("response")

        if not isinstance(response, str):
            raise ValueError("invalid semantic cache payload")

        return CacheEntry(response=response)

    async def set(self, query: str, response: str) -> bool:
        payload = json.dumps(
            {"response": response},
            separators=(",", ":"),
        )

        payload_size = len(payload.encode("utf-8"))

        if payload_size > self._max_bytes:
            raise ValueError("semantic cache payload exceeds maximum size")

        key = semantic_cache_key(hash_text(self._normalize(query)))

        return await self._store.set(
            key,
            payload,
            ttl_seconds=self._ttl_seconds,
        )

    async def delete(self, query: str) -> int:
        key = semantic_cache_key(hash_text(self._normalize(query)))
        return await self._store.delete(key)

    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join(query.strip().split()).casefold()
