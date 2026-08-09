from __future__ import annotations

import asyncio
from time import perf_counter

from opentelemetry import trace

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
from nexus.observability.llm_metrics import (
    LLM_ERRORS_TOTAL,
    LLM_FALLBACKS_TOTAL,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_RETRIES_TOTAL,
)

tracer = trace.get_tracer(__name__)


class LLMGateway:
    """
    Provider-agnostic LLM gateway.

    Responsibilities:
    - Provider selection.
    - Request timeout enforcement.
    - Retry transient provider failures.
    - Exponential backoff.
    - Fallback to another provider.
    - Provider-level Prometheus metrics.
    - OpenTelemetry tracing.
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
        with tracer.start_as_current_span("llm.gateway.generate") as span:
            span.set_attribute(
                "llm.provider.count",
                len(self._providers),
            )
            span.set_attribute(
                "llm.request.prompt_length",
                len(request.prompt),
            )

            last_error: LLMProviderError | None = None

            for index, provider in enumerate(self._providers):
                provider_name = self._provider_name(provider)

                span.set_attribute(
                    "llm.provider.attempt",
                    index + 1,
                )

                try:
                    response = await self._generate_with_retry(
                        provider,
                        request,
                    )

                    span.set_attribute(
                        "llm.provider.selected",
                        provider_name,
                    )

                    return response

                except (
                    LLMProviderRateLimitError,
                    LLMProviderUnavailableError,
                    LLMProviderTimeoutError,
                ) as exc:
                    last_error = exc

                    span.record_exception(exc)

                    span.add_event(
                        "llm.provider.failure",
                        {
                            "llm.provider": provider_name,
                            "llm.error_type": self._error_type(exc),
                            "llm.provider_index": index,
                        },
                    )

                    if index + 1 < len(self._providers):
                        next_provider = self._provider_name(
                            self._providers[index + 1],
                        )

                        LLM_FALLBACKS_TOTAL.labels(
                            from_provider=provider_name,
                            to_provider=next_provider,
                        ).inc()

                        span.add_event(
                            "llm.provider.fallback",
                            {
                                "llm.from_provider": provider_name,
                                "llm.to_provider": next_provider,
                            },
                        )

                    continue

                except LLMProviderAuthenticationError as exc:
                    span.record_exception(exc)
                    span.set_attribute(
                        "llm.error_type",
                        "authentication",
                    )
                    raise

                except LLMProviderError as exc:
                    span.record_exception(exc)
                    span.set_attribute(
                        "llm.error_type",
                        self._error_type(exc),
                    )
                    raise

            if last_error is not None:
                span.record_exception(last_error)
                raise last_error

            error = LLMProviderError(
                "all LLM providers failed",
            )
            span.record_exception(error)
            raise error

    async def _generate_with_retry(
        self,
        provider: LLMProvider,
        request: LLMRequest,
    ) -> LLMResponse:
        provider_name = self._provider_name(provider)
        attempt = 0

        with tracer.start_as_current_span(
            f"llm.provider.{provider_name}",
        ) as provider_span:
            provider_span.set_attribute(
                "llm.provider",
                provider_name,
            )
            provider_span.set_attribute(
                "llm.request.prompt_length",
                len(request.prompt),
            )

            while True:
                started_at = perf_counter()

                with tracer.start_as_current_span(
                    "llm.provider.attempt",
                ) as attempt_span:
                    attempt_span.set_attribute(
                        "llm.provider",
                        provider_name,
                    )
                    attempt_span.set_attribute(
                        "llm.attempt",
                        attempt + 1,
                    )

                    try:
                        response = await asyncio.wait_for(
                            provider.generate(request),
                            timeout=self._timeout_seconds,
                        )

                    except TimeoutError as exc:
                        duration = perf_counter() - started_at

                        LLM_REQUEST_DURATION_SECONDS.labels(
                            provider=provider_name,
                        ).observe(duration)

                        LLM_REQUESTS_TOTAL.labels(
                            provider=provider_name,
                            status="error",
                        ).inc()

                        LLM_ERRORS_TOTAL.labels(
                            provider=provider_name,
                            error_type="timeout",
                        ).inc()

                        attempt_span.record_exception(exc)
                        attempt_span.set_attribute(
                            "llm.error_type",
                            "timeout",
                        )

                        if attempt >= self._max_retries:
                            raise LLMProviderTimeoutError(
                                "LLM provider request timed out",
                            ) from exc

                        LLM_RETRIES_TOTAL.labels(
                            provider=provider_name,
                            error_type="timeout",
                        ).inc()

                        attempt_span.add_event(
                            "llm.retry",
                            {
                                "llm.provider": provider_name,
                                "llm.attempt": attempt + 1,
                            },
                        )

                        await self._backoff(attempt)
                        attempt += 1

                    except (
                        LLMProviderRateLimitError,
                        LLMProviderUnavailableError,
                    ) as exc:
                        duration = perf_counter() - started_at

                        LLM_REQUEST_DURATION_SECONDS.labels(
                            provider=provider_name,
                        ).observe(duration)

                        LLM_REQUESTS_TOTAL.labels(
                            provider=provider_name,
                            status="error",
                        ).inc()

                        error_type = self._error_type(exc)

                        LLM_ERRORS_TOTAL.labels(
                            provider=provider_name,
                            error_type=error_type,
                        ).inc()

                        attempt_span.record_exception(exc)
                        attempt_span.set_attribute(
                            "llm.error_type",
                            error_type,
                        )

                        if attempt >= self._max_retries:
                            raise

                        LLM_RETRIES_TOTAL.labels(
                            provider=provider_name,
                            error_type=error_type,
                        ).inc()

                        attempt_span.add_event(
                            "llm.retry",
                            {
                                "llm.provider": provider_name,
                                "llm.attempt": attempt + 1,
                                "llm.error_type": error_type,
                            },
                        )

                        await self._backoff(attempt)
                        attempt += 1

                    except LLMProviderAuthenticationError as exc:
                        duration = perf_counter() - started_at

                        LLM_REQUEST_DURATION_SECONDS.labels(
                            provider=provider_name,
                        ).observe(duration)

                        LLM_REQUESTS_TOTAL.labels(
                            provider=provider_name,
                            status="error",
                        ).inc()

                        LLM_ERRORS_TOTAL.labels(
                            provider=provider_name,
                            error_type="authentication",
                        ).inc()

                        attempt_span.record_exception(exc)
                        attempt_span.set_attribute(
                            "llm.error_type",
                            "authentication",
                        )

                        raise

                    except LLMProviderError as exc:
                        duration = perf_counter() - started_at

                        LLM_REQUEST_DURATION_SECONDS.labels(
                            provider=provider_name,
                        ).observe(duration)

                        LLM_REQUESTS_TOTAL.labels(
                            provider=provider_name,
                            status="error",
                        ).inc()

                        error_type = self._error_type(exc)

                        LLM_ERRORS_TOTAL.labels(
                            provider=provider_name,
                            error_type=error_type,
                        ).inc()

                        attempt_span.record_exception(exc)
                        attempt_span.set_attribute(
                            "llm.error_type",
                            error_type,
                        )

                        raise

                    else:
                        duration = perf_counter() - started_at

                        LLM_REQUEST_DURATION_SECONDS.labels(
                            provider=provider_name,
                        ).observe(duration)

                        LLM_REQUESTS_TOTAL.labels(
                            provider=provider_name,
                            status="success",
                        ).inc()

                        attempt_span.set_attribute(
                            "llm.response.model",
                            response.model,
                        )

                        provider_span.set_attribute(
                            "llm.response.model",
                            response.model,
                        )

                        return response

    @staticmethod
    def _provider_name(provider: LLMProvider) -> str:
        """
        Return a stable provider name for observability.

        Real providers expose `name`. Test doubles and legacy providers
        may not, so fall back to their class name.
        """
        name = getattr(provider, "name", None)

        if isinstance(name, str) and name.strip():
            return name

        return provider.__class__.__name__.lower()

    @staticmethod
    def _error_type(exc: LLMProviderError) -> str:
        if isinstance(exc, LLMProviderRateLimitError):
            return "rate_limit"

        if isinstance(exc, LLMProviderUnavailableError):
            return "unavailable"

        if isinstance(exc, LLMProviderTimeoutError):
            return "timeout"

        return "provider_error"

    async def _backoff(self, attempt: int) -> None:
        delay = min(
            self._retry_base_delay * (2**attempt),
            self._retry_max_delay,
        )

        await asyncio.sleep(delay)
