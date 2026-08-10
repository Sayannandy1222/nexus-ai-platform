from __future__ import annotations

import pytest

from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.routing.router import ProviderRouter


class FakeProvider:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        return LLMResponse(
            content=f"response from {self._name}",
            model=f"{self._name}-model",
        )


def test_router_requires_at_least_one_provider() -> None:
    with pytest.raises(
        ValueError,
        match="at least one LLM provider",
    ):
        ProviderRouter([])


def test_router_rejects_non_positive_recovery_cooldown() -> None:
    provider = FakeProvider("mistral")

    with pytest.raises(
        ValueError,
        match="recovery cooldown must be positive",
    ):
        ProviderRouter(
            [provider],
            recovery_cooldown_seconds=0,
        )


def test_router_initially_explores_first_provider() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")

    router = ProviderRouter(
        [mistral, groq],
    )

    selected = router.select_provider()

    assert selected.name == "mistral"


def test_router_prefers_lower_latency_provider() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")

    router = ProviderRouter(
        [mistral, groq],
    )

    router.record_success(
        mistral,
        latency_seconds=1.0,
    )

    router.record_success(
        groq,
        latency_seconds=0.1,
    )

    selected = router.select_provider()

    assert selected.name == "groq"


def test_router_tracks_success_statistics() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter([provider])

    router.record_success(
        provider,
        latency_seconds=0.25,
    )

    router.record_success(
        provider,
        latency_seconds=0.35,
    )

    stats = router.get_stats(provider)

    assert stats.requests == 2
    assert stats.successes == 2
    assert stats.failures == 0
    assert stats.success_rate == 1.0
    assert stats.error_rate == 0.0
    assert stats.average_latency_seconds == pytest.approx(
        0.30,
    )


def test_router_tracks_failures() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter([provider])

    router.record_failure(provider)

    stats = router.get_stats(provider)

    assert stats.requests == 1
    assert stats.successes == 0
    assert stats.failures == 1
    assert stats.success_rate == 0.0
    assert stats.error_rate == 1.0
    assert stats.consecutive_failures == 1


def test_router_marks_provider_unhealthy_after_repeated_failures() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter([provider])

    router.record_failure(provider)
    router.record_failure(provider)
    router.record_failure(provider)

    stats = router.get_stats(provider)

    assert stats.consecutive_failures == 3
    assert not stats.is_healthy


def test_success_resets_consecutive_failures() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter([provider])

    router.record_failure(provider)
    router.record_failure(provider)

    router.record_success(
        provider,
        latency_seconds=0.2,
    )

    stats = router.get_stats(provider)

    assert stats.consecutive_failures == 0
    assert stats.is_healthy
    assert stats.successes == 1
    assert stats.failures == 2


def test_router_prefers_healthy_provider() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")

    router = ProviderRouter(
        [mistral, groq],
    )

    router.record_failure(mistral)
    router.record_failure(mistral)
    router.record_failure(mistral)

    router.record_success(
        groq,
        latency_seconds=0.5,
    )

    selected = router.select_provider()

    assert selected.name == "groq"


def test_router_rejects_negative_latency() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter([provider])

    with pytest.raises(
        ValueError,
        match="latency must not be negative",
    ):
        router.record_success(
            provider,
            latency_seconds=-0.1,
        )


def test_router_rejects_unknown_provider() -> None:
    provider = FakeProvider("mistral")
    unknown = FakeProvider("unknown")

    router = ProviderRouter([provider])

    with pytest.raises(
        ValueError,
        match="provider is not managed",
    ):
        router.record_success(
            unknown,
            latency_seconds=0.1,
        )


def test_router_explores_each_provider_before_optimizing() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")
    gemini = FakeProvider("gemini")

    router = ProviderRouter(
        [mistral, groq, gemini],
    )

    first = router.select_provider()

    assert first.name == "mistral"

    router.record_success(
        first,
        latency_seconds=0.8,
    )

    second = router.select_provider()

    assert second.name == "groq"

    router.record_success(
        second,
        latency_seconds=0.2,
    )

    third = router.select_provider()

    assert third.name == "gemini"

    router.record_success(
        third,
        latency_seconds=0.5,
    )

    selected = router.select_provider()

    assert selected.name == "groq"


def test_unhealthy_provider_becomes_available_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")

    router = ProviderRouter(
        [mistral, groq],
        recovery_cooldown_seconds=30.0,
    )

    router.record_success(
        mistral,
        latency_seconds=0.1,
    )

    router.record_success(
        groq,
        latency_seconds=0.2,
    )

    router.record_failure(mistral)
    router.record_failure(mistral)
    router.record_failure(mistral)

    assert router.select_provider().name == "groq"

    stats = router.get_stats(mistral)

    assert stats.last_failure_at is not None

    failure_time = stats.last_failure_at

    monkeypatch.setattr(
        "nexus.llm.routing.router.monotonic",
        lambda: failure_time + 31.0,
    )

    scores = router.get_scores()

    mistral_score = next(score for score in scores if score.provider_name == "mistral")

    assert mistral_score.healthy


def test_successful_recovery_resets_provider_health() -> None:
    provider = FakeProvider("mistral")

    router = ProviderRouter(
        [provider],
        recovery_cooldown_seconds=30.0,
    )

    router.record_failure(provider)
    router.record_failure(provider)
    router.record_failure(provider)

    assert not router.get_stats(provider).is_healthy

    router.record_success(
        provider,
        latency_seconds=0.1,
    )

    stats = router.get_stats(provider)

    assert stats.consecutive_failures == 0
    assert stats.is_healthy
    assert stats.successes == 1
    assert stats.failures == 3


def test_router_get_scores_returns_all_providers() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")
    gemini = FakeProvider("gemini")

    router = ProviderRouter(
        [mistral, groq, gemini],
    )

    scores = router.get_scores()

    assert len(scores) == 3
    assert [score.provider_name for score in scores] == [
        "mistral",
        "groq",
        "gemini",
    ]


def test_router_initial_scores_are_neutral() -> None:
    mistral = FakeProvider("mistral")
    groq = FakeProvider("groq")

    router = ProviderRouter(
        [mistral, groq],
    )

    scores = router.get_scores()

    assert all(score.score == 1.0 for score in scores)
    assert all(score.success_rate == 1.0 for score in scores)
    assert all(score.average_latency_seconds == 0.0 for score in scores)
    assert all(score.healthy for score in scores)
