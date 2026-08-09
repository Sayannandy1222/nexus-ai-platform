from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from opentelemetry import trace
from pydantic import BaseModel, Field

from nexus.cache.services.semantic_cache import SemanticCache
from nexus.llm.models import LLMRequest, LLMResponse
from nexus.security.auth import require_api_key

router = APIRouter(
    prefix="/generate",
    tags=["LLM"],
)

tracer = trace.get_tracer(__name__)


class GenerateRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        max_length=10_000,
    )


class GenerateResponse(BaseModel):
    content: str
    model: str
    source: str


@router.post(
    "",
    response_model=GenerateResponse,
    dependencies=[Depends(require_api_key)],
)
async def generate(
    payload: GenerateRequest,
    request: Request,
) -> GenerateResponse:
    gateway = request.app.state.llm_gateway
    semantic_cache: SemanticCache = request.app.state.semantic_cache

    with tracer.start_as_current_span("semantic_cache.get") as span:
        span.set_attribute("cache.key_type", "semantic")

        try:
            cached = await semantic_cache.get(payload.prompt)
        except Exception as exc:
            span.record_exception(exc)
            span.set_attribute("cache.hit", False)
            span.set_attribute("cache.error", True)
            cached = None

        if cached is not None:
            span.set_attribute("cache.hit", True)

    if cached is not None:
        with tracer.start_as_current_span("generate.cache_hit") as span:
            span.set_attribute("cache.hit", True)
            span.set_attribute("response.source", "semantic_cache")

        return GenerateResponse(
            content=cached.response,
            model="cache",
            source="semantic_cache",
        )

    with tracer.start_as_current_span("llm.generate") as span:
        span.set_attribute("llm.request.prompt_length", len(payload.prompt))

        response: LLMResponse = await gateway.generate(
            LLMRequest(
                prompt=payload.prompt,
            ),
        )

        span.set_attribute("llm.model", response.model)
        span.set_attribute("response.source", "llm")

    with tracer.start_as_current_span("semantic_cache.set") as span:
        span.set_attribute("cache.key_type", "semantic")

        with suppress(Exception):
            await semantic_cache.set(
                payload.prompt,
                response.content,
            )

    return GenerateResponse(
        content=response.content,
        model=response.model,
        source="llm",
    )
