from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from nexus.api.dependencies import enforce_rate_limit
from nexus.api.routes.rate_limit import router
from nexus.cache.services.rate_limiter import RateLimitResult
from nexus.security.auth import require_api_key


class FakeRateLimiter:
    def __init__(self, result: RateLimitResult) -> None:
        self.result = result
        self.calls: list[str] = []

    async def check(self, user_id: str) -> RateLimitResult:
        self.calls.append(user_id)
        return self.result


def create_test_app(
    monkeypatch,
    api_key: str | None,
    limiter: FakeRateLimiter,
) -> FastAPI:
    app = FastAPI()

    app.include_router(
        router,
        prefix="/v1",
    )

    from nexus.core.config import Settings

    settings = Settings(api_key=api_key)

    def fake_get_settings() -> Settings:
        return settings

    monkeypatch.setattr(
        "nexus.security.auth.get_settings",
        fake_get_settings,
    )

    monkeypatch.setattr(
        "nexus.api.dependencies.get_rate_limiter",
        lambda request: limiter,
    )

    return app


def test_rate_limit_missing_api_key_returns_401(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=True,
            minute_count=1,
            hour_count=1,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=0,
        ),
    )

    app = create_test_app(
        monkeypatch,
        "test-secret",
        limiter,
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/rate-limit/check",
        )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Missing API key",
    }
    assert response.headers["WWW-Authenticate"] == "ApiKey"

    assert limiter.calls == []


def test_rate_limit_invalid_api_key_returns_401(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=True,
            minute_count=1,
            hour_count=1,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=0,
        ),
    )

    app = create_test_app(
        monkeypatch,
        "test-secret",
        limiter,
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/rate-limit/check",
            headers={
                "X-API-Key": "wrong-secret",
            },
        )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid API key",
    }

    assert limiter.calls == []


def test_rate_limit_allows_authenticated_request(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=True,
            minute_count=1,
            hour_count=1,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=0,
        ),
    )

    app = create_test_app(
        monkeypatch,
        "test-secret",
        limiter,
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/rate-limit/check",
            headers={
                "X-API-Key": "test-secret",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "allowed",
    }

    assert len(limiter.calls) == 1

    # The limiter receives the SHA-256-derived caller identity,
    # never the raw API key.
    assert limiter.calls[0] != "test-secret"
    assert len(limiter.calls[0]) == 64


def test_rate_limit_returns_429_when_exceeded(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=False,
            minute_count=61,
            hour_count=61,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=42,
        ),
    )

    app = create_test_app(
        monkeypatch,
        "test-secret",
        limiter,
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/rate-limit/check",
            headers={
                "X-API-Key": "test-secret",
            },
        )

    assert response.status_code == 429
    assert response.json() == {
        "detail": "rate limit exceeded",
    }

    assert response.headers["Retry-After"] == "42"
    assert response.headers["X-RateLimit-Limit-Minute"] == "60"
    assert response.headers["X-RateLimit-Remaining-Minute"] == "0"
    assert response.headers["X-RateLimit-Limit-Hour"] == "1000"
    assert response.headers["X-RateLimit-Remaining-Hour"] == "939"

    assert len(limiter.calls) == 1
    assert limiter.calls[0] != "test-secret"
    assert len(limiter.calls[0]) == 64


def test_rate_limit_never_exposes_api_key_to_limiter(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=True,
            minute_count=1,
            hour_count=1,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=0,
        ),
    )

    app = create_test_app(
        monkeypatch,
        "super-secret-api-key",
        limiter,
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/rate-limit/check",
            headers={
                "X-API-Key": "super-secret-api-key",
            },
        )

    assert response.status_code == 200
    assert limiter.calls

    caller_id = limiter.calls[0]

    assert caller_id != "super-secret-api-key"
    assert "super-secret-api-key" not in caller_id
    assert len(caller_id) == 64


def test_rate_limit_dependency_can_be_used_directly(
    monkeypatch,
) -> None:
    limiter = FakeRateLimiter(
        RateLimitResult(
            allowed=True,
            minute_count=1,
            hour_count=1,
            minute_limit=60,
            hour_limit=1000,
            retry_after_seconds=0,
        ),
    )

    app = FastAPI()

    monkeypatch.setattr(
        "nexus.api.dependencies.get_rate_limiter",
        lambda request: limiter,
    )

    app.dependency_overrides[require_api_key] = lambda: "test-caller"

    @app.get(
        "/protected",
        dependencies=[Depends(enforce_rate_limit)],
    )
    async def protected() -> dict[str, str]:
        return {"status": "allowed"}

    with TestClient(app) as client:
        response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {
        "status": "allowed",
    }
    assert limiter.calls == ["test-caller"]
