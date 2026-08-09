from nexus.llm.models import LLMRequest, LLMResponse


class FakeLLMProvider:
    def __init__(
        self,
        model: str = "fake-model",
        name: str = "fake",
    ) -> None:
        self._model = model
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        self.calls += 1

        return LLMResponse(
            content=f"Generated response for: {request.prompt}",
            model=self._model,
        )
