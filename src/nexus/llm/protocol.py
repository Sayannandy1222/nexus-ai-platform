from typing import Protocol

from nexus.llm.models import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse: ...
