from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.middleware import RequestContextMiddleware
from nexus.observability.metrics import HTTP_REQUESTS_TOTAL


def test_request_id_is_preserved() -> None:
    application = FastAPI()

    @application.get("/users/{user_id}")
    async def get_user(user_id: str) -> dict[str, str]:
        return {"user_id": user_id}

    application.add_middleware(RequestContextMiddleware)

    with TestClient(application) as client:
        response = client.get(
            "/users/123",
            headers={"X-Request-ID": "test-request-123"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_metrics_use_route_template() -> None:
    application = FastAPI()

    @application.get("/users/{user_id}")
    async def get_user(user_id: str) -> dict[str, str]:
        return {"user_id": user_id}

    application.add_middleware(RequestContextMiddleware)

    with TestClient(application) as client:
        response = client.get("/users/123")

    assert response.status_code == 200

    metric_samples = list(
        HTTP_REQUESTS_TOTAL.collect()[0].samples,
    )

    matching_samples = [
        sample
        for sample in metric_samples
        if sample.name == "nexus_http_requests_total"
        and sample.labels.get("method") == "GET"
        and sample.labels.get("route") == "/users/{user_id}"
        and sample.labels.get("status_code") == "200"
    ]

    assert matching_samples


def test_metrics_use_low_cardinality_route_for_multiple_users() -> None:
    application = FastAPI()

    @application.get("/accounts/{account_id}")
    async def get_account(account_id: str) -> dict[str, str]:
        return {"account_id": account_id}

    application.add_middleware(RequestContextMiddleware)

    with TestClient(application) as client:
        first = client.get("/accounts/100")
        second = client.get("/accounts/200")

    assert first.status_code == 200
    assert second.status_code == 200

    metric_samples = list(
        HTTP_REQUESTS_TOTAL.collect()[0].samples,
    )

    matching_samples = [
        sample
        for sample in metric_samples
        if sample.name == "nexus_http_requests_total"
        and sample.labels.get("method") == "GET"
        and sample.labels.get("route") == "/accounts/{account_id}"
        and sample.labels.get("status_code") == "200"
    ]

    assert len(matching_samples) == 1
    assert matching_samples[0].value >= 2
