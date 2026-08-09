from __future__ import annotations

from typing import Protocol


class CacheStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool: ...

    async def delete(self, key: str) -> int: ...

    async def exists(self, key: str) -> bool: ...

    async def close(self) -> None: ...
