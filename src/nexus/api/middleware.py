from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from nexus.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Add request correlation, structured logging, and HTTP metrics.

    Metrics use the resolved route template instead of the raw URL path
    to keep Prometheus label cardinality bounded.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
        )

        started = perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_seconds = perf_counter() - started
            elapsed_ms = elapsed_seconds * 1000
            route = self._get_route(request)

            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                route=route,
                status_code="500",
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                route=route,
            ).observe(elapsed_seconds)

            structlog.get_logger("nexus.http").exception(
                "request_failed",
                method=request.method,
                path=route,
                latency_ms=round(elapsed_ms, 2),
            )

            raise

        elapsed_seconds = perf_counter() - started
        elapsed_ms = elapsed_seconds * 1000
        route = self._get_route(request)

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            route=route,
            status_code=str(response.status_code),
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            route=route,
        ).observe(elapsed_seconds)

        response.headers["X-Request-ID"] = request_id

        structlog.get_logger("nexus.http").info(
            "request_completed",
            method=request.method,
            path=route,
            status_code=response.status_code,
            latency_ms=round(elapsed_ms, 2),
        )

        return response

    @staticmethod
    def _get_route(request: Request) -> str:
        route = request.scope.get("route")

        if route is not None:
            path = getattr(route, "path", None)

            if isinstance(path, str):
                return path

        return request.url.path
