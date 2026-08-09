from __future__ import annotations

import asyncio

from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.protocol import LLMProvider


class LLMGatewayError(Exception):
    """Base exception for LLM gateway failures."""


class LLMProviderTimeoutError(LLMGatewayError):
    """Raised when an LLM provider exceeds the configured timeout."""


class LLMGateway:
    """
    Provider-neutral LLM execution gateway.

    Responsibilities:
    - Validate incoming LLM requests.
    - Apply execution timeouts.
    - Delegate generation to an LLMProvider.
    - Keep provider-specific implementation details outside
      the application layer.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_request(request)

        try:
            return await asyncio.wait_for(
                self._provider.generate(request),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise LLMProviderTimeoutError(
                "LLM provider request timed out",
            ) from exc

    @staticmethod
    def _validate_request(request: LLMRequest) -> None:
        prompt = request.prompt.strip()

        if not prompt:
            raise ValueError("prompt must not be empty")

        if len(prompt) > 32_000:
            raise ValueError("prompt exceeds maximum length")

        if request.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        if request.temperature < 0 or request.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")
