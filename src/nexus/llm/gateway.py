from __future__ import annotations

from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.protocol import LLMProvider


class LLMGateway:
    """
    Provider-agnostic entry point for LLM generation.

    The gateway depends only on the LLMProvider protocol, so the
    application does not need to know whether the request is handled
    by Mistral, Gemini, Groq, or another provider.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        return await self._provider.generate(request)
