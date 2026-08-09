from nexus.llm.models import LLMRequest, LLMResponse


class FakeLLMProvider:
    def __init__(self, model: str = "fake-model") -> None:
        self._model = model
        self.calls = 0

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        self.calls += 1

        return LLMResponse(
            content=f"Generated response for: {request.prompt}",
            model=self._model,
        )
