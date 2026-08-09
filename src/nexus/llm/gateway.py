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
    - Enforce request timeouts.
    - Retry transient provider failures.
    - Apply exponential backoff.
    - Never retry permanent failures.
    """

    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings,
    ) -> None:
        self._provider = provider
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
        attempt = 0

        while True:
            try:
                return await asyncio.wait_for(
                    self._provider.generate(request),
                    timeout=self._timeout_seconds,
                )

            except TimeoutError as exc:
                error = LLMProviderTimeoutError(
                    "LLM provider request timed out",
                )

                if not self._should_retry(error, attempt):
                    raise error from exc

                await self._backoff(attempt)
                attempt += 1

            except (
                LLMProviderRateLimitError,
                LLMProviderUnavailableError,
            ) as exc:
                if not self._should_retry(exc, attempt):
                    raise

                await self._backoff(attempt)
                attempt += 1

            except (
                LLMProviderAuthenticationError,
                LLMProviderError,
            ):
                raise

    def _should_retry(
        self,
        error: LLMProviderError,
        attempt: int,
    ) -> bool:
        return (
            isinstance(
                error,
                (
                    LLMProviderTimeoutError,
                    LLMProviderRateLimitError,
                    LLMProviderUnavailableError,
                ),
            )
            and attempt < self._max_retries
        )

    async def _backoff(self, attempt: int) -> None:
        delay = min(
            self._retry_base_delay * (2**attempt),
            self._retry_max_delay,
        )

        await asyncio.sleep(delay)
