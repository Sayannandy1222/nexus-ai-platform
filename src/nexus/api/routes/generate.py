from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from nexus.cache.services.semantic_cache import SemanticCache
from nexus.llm.models import LLMRequest, LLMResponse

router = APIRouter(
    prefix="/generate",
    tags=["LLM"],
)


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
)
async def generate(
    payload: GenerateRequest,
    request: Request,
) -> GenerateResponse:
    gateway = request.app.state.llm_gateway
    semantic_cache: SemanticCache = request.app.state.semantic_cache

    # Cache failures must not take down the LLM API.
    try:
        cached = await semantic_cache.get(payload.prompt)
    except Exception:
        cached = None

    if cached is not None:
        return GenerateResponse(
            content=cached.response,
            model="cache",
            source="semantic_cache",
        )

    response: LLMResponse = await gateway.generate(
        LLMRequest(
            prompt=payload.prompt,
        ),
    )

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
