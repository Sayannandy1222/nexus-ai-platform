from __future__ import annotations

from typing import Any

import httpx

from nexus.llm.errors import (
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderResponseError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from nexus.llm.models import LLMRequest, LLMResponse


class MistralLLMProvider:
    """HTTP-based Mistral implementation of the Nexus LLM contract."""

    BASE_URL = "https://api.mistral.ai/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-small-latest",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Mistral API key must not be empty")

        if timeout_seconds <= 0:
            raise ValueError("Mistral timeout must be positive")

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "mistral"

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt,
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(self._timeout_seconds)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
            ) as client:
                response = await client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

        except httpx.TimeoutException as exc:
            raise LLMProviderTimeoutError(
                "Mistral request timed out",
            ) from exc

        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError(
                f"Mistral network request failed: {exc}",
            ) from exc

        self._raise_for_status(response)

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMProviderResponseError(
                "Mistral returned invalid JSON",
            ) from exc

        try:
            choices = data["choices"]

            if not isinstance(choices, list) or not choices:
                raise LLMProviderResponseError(
                    "Mistral returned no choices",
                )

            message = choices[0]["message"]
            content = message["content"]

        except LLMProviderResponseError:
            raise

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderResponseError(
                "Mistral returned an unexpected response format",
            ) from exc

        if not isinstance(content, str):
            raise LLMProviderResponseError(
                "Mistral response content is not a string",
            )

        return LLMResponse(
            content=content,
            model=self._model,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code = response.status_code

        if status_code in (401, 403):
            raise LLMProviderAuthenticationError(
                "Mistral authentication failed",
            )

        if status_code == 429:
            raise LLMProviderRateLimitError(
                "Mistral rate limit exceeded",
            )

        if status_code in (500, 502, 503, 504):
            raise LLMProviderUnavailableError(
                "Mistral service is temporarily unavailable",
            )

        if status_code >= 400:
            raise LLMProviderError(
                f"Mistral provider request failed with HTTP {status_code}",
            )
