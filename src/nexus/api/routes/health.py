from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nexus.cache.adapters.redis import RedisCacheAdapter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """
    Liveness probe.

    Only verifies that the FastAPI process is running.
    """
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request) -> JSONResponse:
    """
    Readiness probe.

    The instance is ready when the configured Valkey/Redis
    cache adapter exists and successfully responds to ping().
    """

    cache = getattr(request.app.state, "cache_adapter", None)

    if cache is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": "cache_adapter_missing",
            },
        )

    if not isinstance(cache, RedisCacheAdapter):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": "invalid_cache_adapter",
                "cache_type": type(cache).__name__,
            },
        )

    try:
        result = await cache.ping()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ready",
                "cache": "ok",
                "ping": str(result),
            },
        )

    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": "cache_ping_failed",
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )