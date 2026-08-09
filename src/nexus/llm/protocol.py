from typing import Protocol

from nexus.llm.models import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse: ...
