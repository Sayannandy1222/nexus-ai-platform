from __future__ import annotations

import json
from dataclasses import dataclass

from nexus.cache.adapters.memory_protocol import SessionMemoryStore
from nexus.cache.keys import session_memory_key
from nexus.core.config import Settings


@dataclass(frozen=True)
class MemoryMessage:
    role: str
    content: str


class AgentMemory:
    def __init__(
        self,
        store: SessionMemoryStore,
        settings: Settings,
    ) -> None:
        self._store = store
        self._ttl_seconds = settings.session_ttl_seconds
        self._max_messages = settings.session_max_messages
        self._max_message_bytes = settings.session_max_message_bytes

        if self._ttl_seconds <= 0:
            raise ValueError("session TTL must be positive")

        if self._max_messages <= 0:
            raise ValueError("session max messages must be positive")

        if self._max_message_bytes <= 0:
            raise ValueError("session max message bytes must be positive")

    async def append(
        self,
        session_id: str,
        message: MemoryMessage,
    ) -> None:
        payload = json.dumps(
            {
                "role": message.role,
                "content": message.content,
            },
            separators=(",", ":"),
        )

        payload_size = len(payload.encode("utf-8"))

        if payload_size > self._max_message_bytes:
            raise ValueError("message exceeds maximum allowed size")

        await self._store.append_bounded(
            session_memory_key(session_id),
            payload,
            max_items=self._max_messages,
            ttl_seconds=self._ttl_seconds,
        )

    async def get_recent(
        self,
        session_id: str,
    ) -> list[MemoryMessage]:
        values = await self._store.get_recent(
            session_memory_key(session_id),
            max_items=self._max_messages,
        )

        messages: list[MemoryMessage] = []

        for value in values:
            data = json.loads(value)

            role = data.get("role")
            content = data.get("content")

            if not isinstance(role, str) or not isinstance(content, str):
                raise ValueError("invalid session memory payload")

            messages.append(
                MemoryMessage(
                    role=role,
                    content=content,
                )
            )

        return messages

    async def clear(self, session_id: str) -> int:
        return await self._store.delete(
            session_memory_key(session_id),
        )
