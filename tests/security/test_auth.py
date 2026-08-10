from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from nexus.core.config import Settings
from nexus.security.auth import require_api_key


def create_test_app(
    monkeypatch,
    api_key: str | None,
) -> FastAPI:
    app = FastAPI()

    settings = Settings(api_key=api_key)

    def fake_get_settings() -> Settings:
        return settings

    monkeypatch.setattr(
        "nexus.security.auth.get_settings",
        fake_get_settings,
    )

    @app.get(
        "/protected",
        dependencies=[Depends(require_api_key)],
    )
    async def protected() -> dict[str, str]:
        return {"status": "authenticated"}

    return app


def test_missing_api_key_returns_401(monkeypatch) -> None:
    app = create_test_app(
        monkeypatch,
        "test-secret",
    )

    with TestClient(app) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Missing API key",
    }
    assert response.headers["WWW-Authenticate"] == "ApiKey"


def test_invalid_api_key_returns_401(monkeypatch) -> None:
    app = create_test_app(
        monkeypatch,
        "test-secret",
    )

    with TestClient(app) as client:
        response = client.get(
            "/protected",
            headers={"X-API-Key": "wrong-secret"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid API key",
    }
    assert response.headers["WWW-Authenticate"] == "ApiKey"


def test_valid_api_key_returns_200(monkeypatch) -> None:
    app = create_test_app(
        monkeypatch,
        "test-secret",
    )

    with TestClient(app) as client:
        response = client.get(
            "/protected",
            headers={"X-API-Key": "test-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "authenticated",
    }


def test_authentication_not_configured_returns_503(monkeypatch) -> None:
    app = create_test_app(
        monkeypatch,
        None,
    )

    with TestClient(app) as client:
        response = client.get(
            "/protected",
            headers={"X-API-Key": "test-secret"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "API authentication is not configured",
    }
