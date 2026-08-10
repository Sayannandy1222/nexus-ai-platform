from __future__ import annotations

from typing import Protocol


class SessionMemoryStore(Protocol):
    async def append_bounded(
        self,
        key: str,
        value: str,
        *,
        max_items: int,
        ttl_seconds: int,
    ) -> None: ...

    async def get_recent(
        self,
        key: str,
        *,
        max_items: int,
    ) -> list[str]: ...

    async def delete(self, key: str) -> int: ...

    async def close(self) -> None: ...
