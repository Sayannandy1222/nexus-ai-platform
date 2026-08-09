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


class GeminiLLMProvider:
    """Google Gemini implementation of the Nexus LLM provider contract."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key must not be empty")

        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return "gemini"

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        url = f"{self.BASE_URL}/{self._model}:generateContent"

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": request.prompt,
                        },
                    ],
                },
            ],
        }

        params = {
            "key": self._api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    json=payload,
                )

        except httpx.TimeoutException as exc:
            raise LLMProviderTimeoutError(
                "Gemini request timed out",
            ) from exc

        except httpx.HTTPError as exc:
            raise LLMProviderUnavailableError(
                "Gemini HTTP request failed",
            ) from exc

        self._raise_for_status(response)

        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMProviderResponseError(
                "Gemini returned invalid JSON",
            ) from exc

        try:
            candidates = data["candidates"]

            if not candidates:
                raise LLMProviderResponseError(
                    "Gemini returned no candidates",
                )

            parts = candidates[0]["content"]["parts"]

            if not parts:
                raise LLMProviderResponseError(
                    "Gemini returned no content parts",
                )

            content = parts[0]["text"]

        except LLMProviderResponseError:
            raise

        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderResponseError(
                "Gemini returned an unexpected response format",
            ) from exc

        if not isinstance(content, str):
            raise LLMProviderResponseError(
                "Gemini response content is not a string",
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
                "Gemini authentication failed",
            )

        if status_code == 429:
            raise LLMProviderRateLimitError(
                "Gemini rate limit exceeded",
            )

        if status_code in (500, 502, 503, 504):
            raise LLMProviderUnavailableError(
                "Gemini service is temporarily unavailable",
            )

        if status_code >= 400:
            raise LLMProviderError(
                f"Gemini provider request failed: HTTP {status_code}",
            )
