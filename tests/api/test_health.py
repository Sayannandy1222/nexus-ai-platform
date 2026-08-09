from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.routes.health import router
from nexus.cache.adapters.redis import RedisCacheAdapter


def create_test_app(cache: RedisCacheAdapter | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.state.cache_adapter = cache
    return app


def test_liveness_is_independent_of_cache() -> None:
    app = create_test_app(None)

    with TestClient(app) as client:
        response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_requires_cache() -> None:
    app = create_test_app(None)

    with TestClient(app) as client:
        response = client.get("/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_readiness_when_cache_is_healthy() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    cache = object.__new__(RedisCacheAdapter)
    cache.ping = AsyncMock(return_value=True)  # type: ignore[attr-defined]

    app.state.cache_adapter = cache

    with TestClient(app) as client:
        response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_when_cache_is_unavailable() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    cache = object.__new__(RedisCacheAdapter)
    cache.ping = AsyncMock(side_effect=ConnectionError("Valkey unavailable"))  # type: ignore[attr-defined]

    app.state.cache_adapter = cache

    with TestClient(app) as client:
        response = client.get("/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
