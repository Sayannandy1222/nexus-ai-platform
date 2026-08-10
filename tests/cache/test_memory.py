import pytest

from nexus.cache.services.memory import AgentMemory, MemoryMessage
from nexus.core.config import Settings


class FakeMemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def append_bounded(
        self,
        key: str,
        value: str,
        *,
        max_items: int,
        ttl_seconds: int,
    ) -> None:
        messages = self.values.setdefault(key, [])
        messages.append(value)
        self.values[key] = messages[-max_items:]
        self.ttls[key] = ttl_seconds

    async def get_recent(
        self,
        key: str,
        *,
        max_items: int,
    ) -> list[str]:
        return self.values.get(key, [])[-max_items:]

    async def delete(self, key: str) -> int:
        existed = key in self.values

        self.values.pop(key, None)
        self.ttls.pop(key, None)

        return int(existed)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_append_and_read_memory() -> None:
    store = FakeMemoryStore()
    memory = AgentMemory(store, Settings())

    await memory.append(
        "session-1",
        MemoryMessage(
            role="user",
            content="Hello",
        ),
    )

    messages = await memory.get_recent("session-1")

    assert messages == [
        MemoryMessage(
            role="user",
            content="Hello",
        )
    ]


@pytest.mark.asyncio
async def test_memory_is_session_isolated() -> None:
    store = FakeMemoryStore()
    memory = AgentMemory(store, Settings())

    await memory.append(
        "session-1",
        MemoryMessage(
            role="user",
            content="session one",
        ),
    )

    await memory.append(
        "session-2",
        MemoryMessage(
            role="user",
            content="session two",
        ),
    )

    session_one = await memory.get_recent("session-1")
    session_two = await memory.get_recent("session-2")

    assert session_one[0].content == "session one"
    assert session_two[0].content == "session two"


@pytest.mark.asyncio
async def test_memory_has_bounded_message_count() -> None:
    settings = Settings(session_max_messages=3)

    store = FakeMemoryStore()
    memory = AgentMemory(store, settings)

    for index in range(5):
        await memory.append(
            "session-1",
            MemoryMessage(
                role="user",
                content=f"message-{index}",
            ),
        )

    messages = await memory.get_recent("session-1")

    assert len(messages) == 3
    assert [message.content for message in messages] == [
        "message-2",
        "message-3",
        "message-4",
    ]


@pytest.mark.asyncio
async def test_memory_enforces_message_size_limit() -> None:
    settings = Settings(session_max_message_bytes=50)

    store = FakeMemoryStore()
    memory = AgentMemory(store, settings)

    with pytest.raises(
        ValueError,
        match="maximum allowed size",
    ):
        await memory.append(
            "session-1",
            MemoryMessage(
                role="user",
                content="x" * 100,
            ),
        )


@pytest.mark.asyncio
async def test_memory_applies_ttl() -> None:
    settings = Settings(session_ttl_seconds=1234)

    store = FakeMemoryStore()
    memory = AgentMemory(store, settings)

    await memory.append(
        "session-1",
        MemoryMessage(
            role="user",
            content="hello",
        ),
    )

    key = "nexus:v1:langchain:memory:session:session-1"

    assert store.ttls[key] == 1234


@pytest.mark.asyncio
async def test_memory_clear() -> None:
    store = FakeMemoryStore()
    memory = AgentMemory(store, Settings())

    await memory.append(
        "session-1",
        MemoryMessage(
            role="user",
            content="hello",
        ),
    )

    deleted = await memory.clear("session-1")

    assert deleted == 1
    assert await memory.get_recent("session-1") == []


@pytest.mark.asyncio
async def test_malformed_memory_payload_is_rejected() -> None:
    store = FakeMemoryStore()
    memory = AgentMemory(store, Settings())

    key = "nexus:v1:langchain:memory:session:session-1"

    store.values[key] = ['{"role": "user"}']

    with pytest.raises(
        ValueError,
        match="invalid session memory payload",
    ):
        await memory.get_recent("session-1")
