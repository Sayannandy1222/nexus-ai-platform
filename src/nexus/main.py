from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nexus.api.router import api_router
from nexus.cache.adapters.redis import RedisCacheAdapter
from nexus.cache.services.rate_limiter import RateLimiter
from nexus.core.config import get_settings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """
    Manage application resources across startup and shutdown.

    Startup:
        - Load application settings.
        - Create the Redis/Valkey connection pool.
        - Initialize shared application services.

    Shutdown:
        - Gracefully close the Redis/Valkey connection pool.
    """

    settings = get_settings()

    cache_adapter = RedisCacheAdapter.from_settings(settings)

    rate_limiter = RateLimiter(
        store=cache_adapter,
        settings=settings,
    )

    application.state.cache_adapter = cache_adapter
    application.state.rate_limiter = rate_limiter

    try:
        yield
    finally:
        await cache_adapter.close()


def create_app() -> FastAPI:
    application = FastAPI(
        title="NEXUS AI Platform",
        description=(
            "Production-grade AI context, RAG, Redis/Valkey observability and LLMOps platform."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    application.include_router(api_router)

    return application


app = create_app()
