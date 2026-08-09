from __future__ import annotations

import asyncio

from nexus.core.config import Settings
from nexus.llm.errors import (
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.protocol import LLMProvider


class LLMGateway:
    """
    Provider-agnostic LLM gateway.

    Responsibilities:
    - Provider selection.
    - Request timeout enforcement.
    - Retry transient provider failures.
    - Exponential backoff.
    - Fallback to another provider after transient failure.
    """

    def __init__(
        self,
        providers: list[LLMProvider],
        settings: Settings,
    ) -> None:
        if not providers:
            raise ValueError("at least one LLM provider is required")

        self._providers = providers
        self._timeout_seconds = settings.llm_request_timeout_seconds
        self._max_retries = settings.llm_max_retries
        self._retry_base_delay = settings.llm_retry_base_delay_seconds
        self._retry_max_delay = settings.llm_retry_max_delay_seconds

        if self._timeout_seconds <= 0:
            raise ValueError(
                "LLM request timeout must be positive",
            )

        if self._max_retries < 0:
            raise ValueError(
                "LLM max retries must not be negative",
            )

        if self._retry_base_delay <= 0:
            raise ValueError(
                "LLM retry base delay must be positive",
            )

        if self._retry_max_delay <= 0:
            raise ValueError(
                "LLM retry max delay must be positive",
            )

        if self._retry_base_delay > self._retry_max_delay:
            raise ValueError(
                "LLM retry base delay must not exceed max delay",
            )

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        last_error: LLMProviderError | None = None

        for provider in self._providers:
            try:
                return await self._generate_with_retry(
                    provider,
                    request,
                )

            except (
                LLMProviderRateLimitError,
                LLMProviderUnavailableError,
                LLMProviderTimeoutError,
            ) as exc:
                last_error = exc
                continue

            except LLMProviderAuthenticationError:
                raise

            except LLMProviderError:
                raise

        if last_error is not None:
            raise last_error

        raise LLMProviderError(
            "all LLM providers failed",
        )

    async def _generate_with_retry(
        self,
        provider: LLMProvider,
        request: LLMRequest,
    ) -> LLMResponse:
        attempt = 0

        while True:
            try:
                return await asyncio.wait_for(
                    provider.generate(request),
                    timeout=self._timeout_seconds,
                )

            except TimeoutError as exc:
                error = LLMProviderTimeoutError(
                    "LLM provider request timed out",
                )

                if attempt >= self._max_retries:
                    raise error from exc

                await self._backoff(attempt)
                attempt += 1

            except (
                LLMProviderRateLimitError,
                LLMProviderUnavailableError,
            ):
                if attempt >= self._max_retries:
                    raise

                await self._backoff(attempt)
                attempt += 1

            except LLMProviderAuthenticationError:
                raise

            except LLMProviderError:
                raise

    async def _backoff(self, attempt: int) -> None:
        delay = min(
            self._retry_base_delay * (2**attempt),
            self._retry_max_delay,
        )

        await asyncio.sleep(delay)
