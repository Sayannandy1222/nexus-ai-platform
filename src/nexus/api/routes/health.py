from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from nexus.cache.adapters.redis import RedisCacheAdapter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """
    Liveness probe.

    This only verifies that the FastAPI process is running.
    It intentionally does not depend on external services.
    """
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request) -> JSONResponse:
    """
    Readiness probe.

    The instance is ready only when its shared Valkey connection
    can successfully respond to a health check.
    """

    cache = getattr(request.app.state, "cache_adapter", None)

    if not isinstance(cache, RedisCacheAdapter):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )

    try:
        await cache.ping()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready"},
    )
