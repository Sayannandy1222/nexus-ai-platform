from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from nexus.llm.protocol import LLMProvider


@dataclass
class ProviderStats:
    """
    Runtime performance statistics for one LLM provider.
    """

    requests: int = 0
    successes: int = 0
    failures: int = 0

    total_latency_seconds: float = 0.0

    consecutive_failures: int = 0
    last_failure_at: float | None = None

    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 1.0

        return self.successes / self.requests

    @property
    def error_rate(self) -> float:
        if self.requests == 0:
            return 0.0

        return self.failures / self.requests

    @property
    def average_latency_seconds(self) -> float:
        if self.successes == 0:
            return 0.0

        return self.total_latency_seconds / self.successes

    @property
    def is_healthy(self) -> bool:
        return self.consecutive_failures < 3


@dataclass(frozen=True)
class ProviderScore:
    provider_name: str
    score: float
    average_latency_seconds: float
    success_rate: float
    healthy: bool


class ProviderRouter:
    """
    Performance-aware LLM provider router.

    Responsibilities:

    - Track provider performance.
    - Measure successful request latency.
    - Track failures.
    - Detect unhealthy providers.
    - Explore previously unobserved providers.
    - Select the best healthy provider.
    - Recover providers after a cooldown period.
    - Balance exploration and exploitation.

    The router does NOT replace the gateway's retry/fallback logic.
    """

    FAILURE_THRESHOLD = 3

    def __init__(
        self,
        providers: list[LLMProvider],
        recovery_cooldown_seconds: float = 30.0,
    ) -> None:
        if not providers:
            raise ValueError(
                "at least one LLM provider is required",
            )

        if recovery_cooldown_seconds <= 0:
            raise ValueError(
                "recovery cooldown must be positive",
            )

        self._providers = providers
        self._recovery_cooldown_seconds = recovery_cooldown_seconds

        self._stats: dict[str, ProviderStats] = {
            self._provider_name(provider): ProviderStats() for provider in providers
        }

    def select_provider(self) -> LLMProvider:
        """
        Select the best currently available provider.

        Every provider receives an initial request before optimization
        begins.

        Providers that have failed repeatedly are skipped until their
        recovery cooldown expires. Once the cooldown expires, the
        provider becomes eligible for a half-open probe request.
        """

        for provider in self._providers:
            stats = self._get_stats(provider)

            if stats.requests == 0:
                return provider

        scored = [
            self._score_provider(provider)
            for provider in self._providers
            if self._is_available(provider)
        ]

        if not scored:
            scored = [self._score_provider(provider) for provider in self._providers]

        best = min(
            scored,
            key=lambda result: result.score,
        )

        return self._provider_by_name(best.provider_name)

    def record_success(
        self,
        provider: LLMProvider,
        latency_seconds: float,
    ) -> None:
        """
        Record a successful provider request.

        A successful recovery probe immediately restores the provider
        to a healthy state.
        """

        if latency_seconds < 0:
            raise ValueError(
                "latency must not be negative",
            )

        stats = self._get_stats(provider)

        stats.requests += 1
        stats.successes += 1
        stats.total_latency_seconds += latency_seconds

        stats.consecutive_failures = 0
        stats.last_failure_at = None

    def record_failure(
        self,
        provider: LLMProvider,
    ) -> None:
        """
        Record a failed provider request.
        """

        stats = self._get_stats(provider)

        stats.requests += 1
        stats.failures += 1
        stats.consecutive_failures += 1
        stats.last_failure_at = monotonic()

    def get_stats(
        self,
        provider: LLMProvider,
    ) -> ProviderStats:
        """
        Return a copy of the provider's current statistics.
        """

        stats = self._get_stats(provider)

        return ProviderStats(
            requests=stats.requests,
            successes=stats.successes,
            failures=stats.failures,
            total_latency_seconds=stats.total_latency_seconds,
            consecutive_failures=stats.consecutive_failures,
            last_failure_at=stats.last_failure_at,
        )

    def get_scores(self) -> list[ProviderScore]:
        """
        Return the current score for every configured provider.
        """

        return [self._score_provider(provider) for provider in self._providers]

    def _is_available(
        self,
        provider: LLMProvider,
    ) -> bool:
        stats = self._get_stats(provider)

        if stats.consecutive_failures < self.FAILURE_THRESHOLD:
            return True

        if stats.last_failure_at is None:
            return False

        elapsed = monotonic() - stats.last_failure_at

        return elapsed >= self._recovery_cooldown_seconds

    def _score_provider(
        self,
        provider: LLMProvider,
    ) -> ProviderScore:
        name = self._provider_name(provider)
        stats = self._get_stats(provider)

        if stats.requests == 0:
            score = 1.0
        else:
            latency_score = (
                stats.average_latency_seconds if stats.average_latency_seconds > 0 else 1.0
            )

            reliability_penalty = 1.0 - stats.success_rate

            score = latency_score + reliability_penalty

        return ProviderScore(
            provider_name=name,
            score=score,
            average_latency_seconds=stats.average_latency_seconds,
            success_rate=stats.success_rate,
            healthy=self._is_available(provider),
        )

    def _get_stats(
        self,
        provider: LLMProvider,
    ) -> ProviderStats:
        name = self._provider_name(provider)

        try:
            return self._stats[name]
        except KeyError as exc:
            raise ValueError(
                f"provider is not managed by this router: {name}",
            ) from exc

    def _provider_by_name(
        self,
        provider_name: str,
    ) -> LLMProvider:
        for provider in self._providers:
            if self._provider_name(provider) == provider_name:
                return provider

        raise RuntimeError(
            f"provider not found: {provider_name}",
        )

    @staticmethod
    def _provider_name(
        provider: LLMProvider,
    ) -> str:
        name = getattr(provider, "name", None)

        if isinstance(name, str) and name:
            return name

        return provider.__class__.__name__.lower()
