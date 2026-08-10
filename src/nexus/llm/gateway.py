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
from nexus.llm.routing.router import ProviderRouter
from nexus.observability.llm_metrics import (
    LLM_ERRORS_TOTAL,
    LLM_FALLBACKS_TOTAL,
    LLM_PROVIDER_AVERAGE_LATENCY_SECONDS,
    LLM_PROVIDER_CONSECUTIVE_FAILURES,
    LLM_PROVIDER_ERROR_RATE,
    LLM_PROVIDER_HEALTHY,
    LLM_PROVIDER_REQUESTS,
    LLM_PROVIDER_SCORE,
    LLM_PROVIDER_SELECTED_TOTAL,
    LLM_PROVIDER_SUCCESS_RATE,
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_RETRIES_TOTAL,
)

tracer = trace.get_tracer(__name__)


class LLMGateway:
    """
    Provider-agnostic LLM gateway.

    Responsibilities:
    - Intelligent provider selection.
    - Provider performance tracking.
    - Request timeout enforcement.
    - Retry transient provider failures.
    - Exponential backoff.
    - Fallback to another provider.
    - Provider-level Prometheus metrics.
    - Provider routing metrics.
    - OpenTelemetry tracing.

    The ProviderRouter chooses the best provider based on observed
    performance. The gateway remains responsible for reliability.
    """

    def __init__(
        self,
        providers: list[LLMProvider],
        settings: Settings,
    ) -> None:
        if not providers:
            raise ValueError("at least one LLM provider is required")

        self._providers = providers
        self._router = ProviderRouter(providers)

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

        # Publish initial router state.
        self._update_provider_metrics()

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        with tracer.start_as_current_span(
            "llm.gateway.generate",
        ) as span:
            span.set_attribute(
                "llm.provider.count",
                len(self._providers),
            )

            span.set_attribute(
                "llm.request.prompt_length",
                len(request.prompt),
            )

            selected_provider = self._router.select_provider()

            selected_provider_name = self._provider_name(
                selected_provider,
            )

            LLM_PROVIDER_SELECTED_TOTAL.labels(
                provider=selected_provider_name,
            ).inc()

            self._update_provider_metrics()

            span.set_attribute(
                "llm.provider.selected",
                selected_provider_name,
            )

            span.set_attribute(
                "llm.routing.enabled",
                True,
            )

            last_error: LLMProviderError | None = None

            # Try the router-selected provider first.
            ordered_providers = self._ordered_providers(
                selected_provider,
            )

            for index, provider in enumerate(ordered_providers):
                provider_name = self._provider_name(provider)

                span.set_attribute(
                    "llm.provider.attempt",
                    index + 1,
                )

                started_at = perf_counter()

                try:
                    response = await self._generate_with_retry(
                        provider,
                        request,
                    )

                    routing_latency = perf_counter() - started_at

                    self._router.record_success(
                        provider,
                        latency_seconds=routing_latency,
                    )

                    self._update_provider_metrics()

                    span.set_attribute(
                        "llm.provider.selected",
                        provider_name,
                    )

                    span.set_attribute(
                        "llm.routing.latency_seconds",
                        routing_latency,
                    )

                    return response

                except (
                    LLMProviderRateLimitError,
                    LLMProviderUnavailableError,
                    LLMProviderTimeoutError,
                ) as exc:
                    self._router.record_failure(provider)

                    self._update_provider_metrics()

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

                    if index + 1 < len(ordered_providers):
                        next_provider = self._provider_name(
                            ordered_providers[index + 1],
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
                    self._router.record_failure(provider)

                    self._update_provider_metrics()

                    span.record_exception(exc)

                    span.set_attribute(
                        "llm.error_type",
                        "authentication",
                    )

                    raise

                except LLMProviderError as exc:
                    self._router.record_failure(provider)

                    self._update_provider_metrics()

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

    def _update_provider_metrics(self) -> None:
        """
        Publish the current ProviderRouter state to Prometheus.

        Router state is maintained in memory while Prometheus receives
        the latest snapshot for each configured provider.
        """

        for score in self._router.get_scores():
            provider = score.provider_name

            stats_provider = next(
                (
                    configured_provider
                    for configured_provider in self._providers
                    if self._provider_name(configured_provider) == provider
                ),
                None,
            )

            if stats_provider is None:
                continue

            stats = self._router.get_stats(stats_provider)

            LLM_PROVIDER_REQUESTS.labels(
                provider=provider,
            ).set(stats.requests)

            LLM_PROVIDER_SUCCESS_RATE.labels(
                provider=provider,
            ).set(stats.success_rate)

            LLM_PROVIDER_ERROR_RATE.labels(
                provider=provider,
            ).set(stats.error_rate)

            LLM_PROVIDER_AVERAGE_LATENCY_SECONDS.labels(
                provider=provider,
            ).set(stats.average_latency_seconds)

            LLM_PROVIDER_CONSECUTIVE_FAILURES.labels(
                provider=provider,
            ).set(stats.consecutive_failures)

            LLM_PROVIDER_HEALTHY.labels(
                provider=provider,
            ).set(1.0 if score.healthy else 0.0)

            LLM_PROVIDER_SCORE.labels(
                provider=provider,
            ).set(score.score)

    def _ordered_providers(
        self,
        selected_provider: LLMProvider,
    ) -> list[LLMProvider]:
        """
        Put the router-selected provider first.

        The remaining providers preserve their configured order so the
        existing deterministic fallback behavior remains intact.
        """

        ordered = [selected_provider]

        for provider in self._providers:
            if provider is selected_provider:
                continue

            ordered.append(provider)

        return ordered

    @staticmethod
    def _provider_name(
        provider: LLMProvider,
    ) -> str:
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
    def _error_type(
        exc: LLMProviderError,
    ) -> str:
        if isinstance(exc, LLMProviderRateLimitError):
            return "rate_limit"

        if isinstance(exc, LLMProviderUnavailableError):
            return "unavailable"

        if isinstance(exc, LLMProviderTimeoutError):
            return "timeout"

        return "provider_error"

    async def _backoff(
        self,
        attempt: int,
    ) -> None:
        delay = min(
            self._retry_base_delay * (2**attempt),
            self._retry_max_delay,
        )

        await asyncio.sleep(delay)
