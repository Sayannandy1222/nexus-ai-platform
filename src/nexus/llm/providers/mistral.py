from __future__ import annotations

from typing import Any

from mistralai import Mistral  # type: ignore[import-untyped]

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
    """Mistral implementation of the Nexus LLM provider contract."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-small-latest",
    ) -> None:
        if not api_key.strip():
            raise ValueError("Mistral API key must not be empty")

        self._client = Mistral(api_key=api_key)
        self._model = model

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Generate a response using Mistral.

        Provider-specific failures are translated into Nexus domain
        exceptions so the rest of the application remains provider-agnostic.
        """

        try:
            response = await self._client.chat.complete_async(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": request.prompt,
                    },
                ],
            )

        except TimeoutError as exc:
            raise LLMProviderTimeoutError(
                "Mistral request timed out",
            ) from exc

        except Exception as exc:
            self._raise_provider_error(exc)

        if response is None:
            raise LLMProviderResponseError(
                "Mistral returned an empty response",
            )

        try:
            choices = response.choices

            if not choices:
                raise LLMProviderResponseError(
                    "Mistral returned no choices",
                )

            message = choices[0].message
            content = message.content

        except LLMProviderResponseError:
            raise

        except (AttributeError, IndexError, TypeError) as exc:
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
    def _raise_provider_error(exc: Exception) -> None:
        """
        Translate Mistral/API failures into Nexus domain exceptions.

        The rest of the application should never need to depend on
        Mistral-specific exception types.
        """

        status_code: Any = getattr(exc, "status_code", None)

        if status_code in (401, 403):
            raise LLMProviderAuthenticationError(
                "Mistral authentication failed",
            ) from exc

        if status_code == 429:
            raise LLMProviderRateLimitError(
                "Mistral rate limit exceeded",
            ) from exc

        if status_code in (500, 502, 503, 504):
            raise LLMProviderUnavailableError(
                "Mistral service is temporarily unavailable",
            ) from exc

        raise LLMProviderError(
            f"Mistral provider request failed: {exc}",
        ) from exc
