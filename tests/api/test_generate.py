from __future__ import annotations

from fastapi.testclient import TestClient

from nexus.cache.services.semantic_cache import CacheEntry
from nexus.llm.models import LLMResponse
from nexus.main import create_app


class FakeGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return LLMResponse(
            content=f"Generated: {request.prompt}",
            model="fake-model",
        )


class FakeSemanticCache:
    def __init__(self) -> None:
        self.entries: dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0
        self.fail_get = False
        self.fail_set = False

    async def get(self, query: str) -> CacheEntry | None:
        self.get_calls += 1

        if self.fail_get:
            raise RuntimeError("cache unavailable")

        response = self.entries.get(query)

        if response is None:
            return None

        return CacheEntry(response=response)

    async def set(self, query: str, response: str) -> bool:
        self.set_calls += 1

        if self.fail_set:
            raise RuntimeError("cache unavailable")

        self.entries[query] = response
        return True


def make_client() -> tuple[TestClient, FakeGateway, FakeSemanticCache]:
    app = create_app()

    gateway = FakeGateway()
    cache = FakeSemanticCache()

    app.state.llm_gateway = gateway
    app.state.semantic_cache = cache

    return TestClient(app), gateway, cache


def test_generate_cache_miss_calls_gateway_and_caches_response() -> None:
    client, gateway, cache = make_client()

    response = client.post(
        "/v1/generate",
        json={"prompt": "Hello Nexus"},
    )

    assert response.status_code == 200
    assert gateway.calls == 1
    assert cache.get_calls == 1
    assert cache.set_calls == 1


def test_generate_cache_hit_does_not_call_gateway() -> None:
    client, gateway, cache = make_client()

    cache.entries["Hello Nexus"] = "Cached response"

    response = client.post(
        "/v1/generate",
        json={"prompt": "Hello Nexus"},
    )

    assert response.status_code == 200
    assert gateway.calls == 0
    assert cache.get_calls == 1
    assert cache.set_calls == 0


def test_generate_cache_get_failure_does_not_break_request() -> None:
    client, gateway, cache = make_client()

    cache.fail_get = True

    response = client.post(
        "/v1/generate",
        json={"prompt": "Hello Nexus"},
    )

    assert response.status_code == 200
    assert gateway.calls == 1
    assert cache.get_calls == 1


def test_generate_cache_set_failure_does_not_break_request() -> None:
    client, gateway, cache = make_client()

    cache.fail_set = True

    response = client.post(
        "/v1/generate",
        json={"prompt": "Hello Nexus"},
    )

    assert response.status_code == 200
    assert gateway.calls == 1
    assert cache.get_calls == 1
    assert cache.set_calls == 1


def test_generate_rejects_empty_prompt() -> None:
    client, gateway, _ = make_client()

    response = client.post(
        "/v1/generate",
        json={"prompt": ""},
    )

    assert response.status_code == 422
    assert gateway.calls == 0


def test_generate_rejects_oversized_prompt() -> None:
    client, gateway, _ = make_client()

    response = client.post(
        "/v1/generate",
        json={"prompt": "x" * 10_001},
    )

    assert response.status_code == 422
    assert gateway.calls == 0
