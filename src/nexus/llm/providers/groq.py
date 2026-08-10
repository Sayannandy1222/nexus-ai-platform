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
from nexus.llm.http.client import HTTPClientPool
from nexus.llm.models import LLMRequest, LLMResponse


class GroqLLMProvider:
    """HTTP-based Groq implementation of the Nexus LLM contract."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout_seconds: float = 30.0,
        http_client: HTTPClientPool | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Groq API key must not be empty")

        if timeout_seconds <= 0:
            raise ValueError("Groq timeout must be positive")

        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "groq"

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

        try:
            if self._http_client is not None:
                if not self._http_client.is_started:
                    await self._http_client.start()

                response = await self._http_client.client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

            else:
                timeout = httpx.Timeout(self._timeout_seconds)

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
                "Groq request timed out",
            ) from exc

        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError(
                f"Groq network request failed: {exc}",
            ) from exc

        self._raise_for_status(response)

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMProviderResponseError(
                "Groq returned invalid JSON",
            ) from exc

        try:
            choices = data["choices"]

            if not isinstance(choices, list) or not choices:
                raise LLMProviderResponseError(
                    "Groq returned no choices",
                )

            message = choices[0]["message"]
            content = message["content"]

        except LLMProviderResponseError:
            raise

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderResponseError(
                "Groq returned an unexpected response format",
            ) from exc

        if not isinstance(content, str):
            raise LLMProviderResponseError(
                "Groq response content is not a string",
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
                "Groq authentication failed",
            )

        if status_code == 429:
            raise LLMProviderRateLimitError(
                "Groq rate limit exceeded",
            )

        if status_code in (500, 502, 503, 504):
            raise LLMProviderUnavailableError(
                "Groq service is temporarily unavailable",
            )

        if status_code >= 400:
            raise LLMProviderError(
                f"Groq provider request failed with HTTP {status_code}",
            )
