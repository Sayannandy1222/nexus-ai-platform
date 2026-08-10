from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from nexus.api.middleware import RequestContextMiddleware
from nexus.api.router import api_router
from nexus.cache.adapters.redis import RedisCacheAdapter
from nexus.cache.services.rate_limiter import RateLimiter
from nexus.cache.services.semantic_cache import SemanticCache
from nexus.core.config import get_settings
from nexus.core.logging import configure_logging
from nexus.llm.factory import build_llm_providers
from nexus.llm.gateway import LLMGateway
from nexus.llm.http.client import HTTPClientPool
from nexus.observability.tracing import configure_tracing


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """
    Manage application resources across startup and shutdown.

    Startup:
    - Load settings.
    - Configure logging.
    - Create Redis/Valkey cache.
    - Create rate limiter.
    - Create semantic cache.
    - Create a shared HTTP client pool.
    - Build LLM providers using the shared HTTP client.
    - Create the LLM gateway.

    Shutdown:
    - Close the shared HTTP client pool.
    - Close the cache connection.
    """

    settings = get_settings()

    configure_logging(settings.log_level)

    cache_adapter = RedisCacheAdapter.from_settings(settings)

    rate_limiter = RateLimiter(
        store=cache_adapter,
        settings=settings,
    )

    semantic_cache = SemanticCache(
        store=cache_adapter,
        settings=settings,
    )

    http_client = HTTPClientPool(
        timeout_seconds=settings.llm_request_timeout_seconds,
        max_connections=100,
        max_keepalive_connections=20,
    )

    await http_client.start()

    llm_providers = build_llm_providers(
        settings,
        http_client=http_client,
    )

    llm_gateway = LLMGateway(
        providers=llm_providers,
        settings=settings,
    )

    application.state.cache_adapter = cache_adapter
    application.state.rate_limiter = rate_limiter
    application.state.semantic_cache = semantic_cache
    application.state.http_client = http_client
    application.state.llm_gateway = llm_gateway

    try:
        yield

    finally:
        await http_client.close()
        await cache_adapter.close()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """

    settings = get_settings()

    configure_tracing(settings)

    application = FastAPI(
        title="NEXUS AI Platform",
        description=(
            "Production-grade AI context, RAG, Redis/Valkey observability and LLMOps platform."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    if settings.otel_enabled:
        FastAPIInstrumentor.instrument_app(application)

    application.add_middleware(RequestContextMiddleware)

    application.include_router(api_router)

    return application


app = create_app()
