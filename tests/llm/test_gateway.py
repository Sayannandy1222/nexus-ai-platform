import asyncio

import pytest

from nexus.core.config import Settings
from nexus.llm.errors import (
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from nexus.llm.gateway import LLMGateway
from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.providers.fake import FakeLLMProvider


def test_gateway_requires_provider() -> None:
    with pytest.raises(
        ValueError,
        match="at least one LLM provider",
    ):
        LLMGateway([], Settings())


@pytest.mark.asyncio
async def test_gateway_generates_response() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway([provider], Settings())

    response = await gateway.generate(
        LLMRequest(prompt="Hello Nexus"),
    )

    assert response.content == "Generated response for: Hello Nexus"
    assert response.model == "fake-model"


@pytest.mark.asyncio
async def test_gateway_delegates_to_provider() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway([provider], Settings())

    await gateway.generate(LLMRequest(prompt="first"))
    await gateway.generate(LLMRequest(prompt="second"))

    assert provider.calls == 2


class SlowLLMProvider:
    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        await asyncio.sleep(0.1)

        return LLMResponse(
            content="slow response",
            model="slow-model",
        )


@pytest.mark.asyncio
async def test_gateway_times_out_slow_provider() -> None:
    settings = Settings(
        llm_request_timeout_seconds=0.01,
        llm_max_retries=0,
    )

    gateway = LLMGateway(
        [SlowLLMProvider()],
        settings,
    )

    with pytest.raises(
        LLMProviderTimeoutError,
        match="timed out",
    ):
        await gateway.generate(
            LLMRequest(prompt="slow request"),
        )


class FlakyLLMProvider:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        self.calls += 1

        if self.calls <= self.failures:
            raise LLMProviderUnavailableError(
                "temporary provider failure",
            )

        return LLMResponse(
            content="recovered",
            model="test-model",
        )


@pytest.mark.asyncio
async def test_gateway_retries_transient_failure() -> None:
    provider = FlakyLLMProvider(failures=2)

    settings = Settings(
        llm_max_retries=2,
        llm_retry_base_delay_seconds=0.001,
        llm_retry_max_delay_seconds=0.002,
    )

    gateway = LLMGateway([provider], settings)

    response = await gateway.generate(
        LLMRequest(prompt="retry me"),
    )

    assert response.content == "recovered"
    assert provider.calls == 3


@pytest.mark.asyncio
async def test_gateway_stops_after_max_retries() -> None:
    provider = FlakyLLMProvider(failures=10)

    settings = Settings(
        llm_max_retries=2,
        llm_retry_base_delay_seconds=0.001,
        llm_retry_max_delay_seconds=0.002,
    )

    gateway = LLMGateway([provider], settings)

    with pytest.raises(
        LLMProviderUnavailableError,
        match="temporary provider failure",
    ):
        await gateway.generate(
            LLMRequest(prompt="always fails"),
        )

    assert provider.calls == 3


@pytest.mark.asyncio
async def test_gateway_does_not_retry_authentication_failure() -> None:
    class AuthFailingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            self.calls += 1

            raise LLMProviderAuthenticationError(
                "invalid credentials",
            )

    provider = AuthFailingProvider()

    settings = Settings(
        llm_max_retries=2,
        llm_retry_base_delay_seconds=0.001,
        llm_retry_max_delay_seconds=0.002,
    )

    gateway = LLMGateway([provider], settings)

    with pytest.raises(
        LLMProviderAuthenticationError,
        match="invalid credentials",
    ):
        await gateway.generate(
            LLMRequest(prompt="do not retry"),
        )

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_gateway_retries_rate_limit_error() -> None:
    class RateLimitedProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            self.calls += 1

            if self.calls == 1:
                raise LLMProviderRateLimitError(
                    "rate limited",
                )

            return LLMResponse(
                content="success after retry",
                model="test-model",
            )

    provider = RateLimitedProvider()

    settings = Settings(
        llm_max_retries=1,
        llm_retry_base_delay_seconds=0.001,
        llm_retry_max_delay_seconds=0.002,
    )

    gateway = LLMGateway([provider], settings)

    response = await gateway.generate(
        LLMRequest(prompt="retry rate limit"),
    )

    assert response.content == "success after retry"
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_gateway_falls_back_to_second_provider() -> None:
    class FailingProvider:
        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            raise LLMProviderUnavailableError(
                "primary unavailable",
            )

    primary = FailingProvider()
    secondary = FakeLLMProvider()

    settings = Settings(
        llm_max_retries=0,
        llm_retry_base_delay_seconds=0.001,
        llm_retry_max_delay_seconds=0.002,
    )

    gateway = LLMGateway(
        [primary, secondary],
        settings,
    )

    response = await gateway.generate(
        LLMRequest(prompt="fallback test"),
    )

    assert response.content == "Generated response for: fallback test"
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_gateway_fails_when_all_providers_fail() -> None:
    class FailingProvider:
        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            raise LLMProviderUnavailableError(
                "provider unavailable",
            )

    gateway = LLMGateway(
        [
            FailingProvider(),
            FailingProvider(),
        ],
        Settings(
            llm_max_retries=0,
            llm_retry_base_delay_seconds=0.001,
            llm_retry_max_delay_seconds=0.002,
        ),
    )

    with pytest.raises(
        LLMProviderUnavailableError,
        match="provider unavailable",
    ):
        await gateway.generate(
            LLMRequest(prompt="all providers fail"),
        )


@pytest.mark.asyncio
async def test_gateway_does_not_fallback_on_authentication_error() -> None:
    class AuthFailingProvider:
        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            raise LLMProviderAuthenticationError(
                "invalid credentials",
            )

    secondary = FakeLLMProvider()

    gateway = LLMGateway(
        [
            AuthFailingProvider(),
            secondary,
        ],
        Settings(
            llm_max_retries=0,
            llm_retry_base_delay_seconds=0.001,
            llm_retry_max_delay_seconds=0.002,
        ),
    )

    with pytest.raises(
        LLMProviderAuthenticationError,
        match="invalid credentials",
    ):
        await gateway.generate(
            LLMRequest(prompt="authentication failure"),
        )

    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_gateway_does_not_fallback_on_generic_provider_error() -> None:
    class GenericFailingProvider:
        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            raise LLMProviderError(
                "invalid provider request",
            )

    secondary = FakeLLMProvider()

    gateway = LLMGateway(
        [
            GenericFailingProvider(),
            secondary,
        ],
        Settings(
            llm_max_retries=0,
            llm_retry_base_delay_seconds=0.001,
            llm_retry_max_delay_seconds=0.002,
        ),
    )

    with pytest.raises(
        LLMProviderError,
        match="invalid provider request",
    ):
        await gateway.generate(
            LLMRequest(prompt="generic failure"),
        )

    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_gateway_records_successful_latency_in_router() -> None:
    class NamedProvider:
        name = "fast"

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            await asyncio.sleep(0.001)

            return LLMResponse(
                content="success",
                model="fast-model",
            )

    provider = NamedProvider()

    gateway = LLMGateway(
        [provider],
        Settings(
            llm_max_retries=0,
        ),
    )

    await gateway.generate(
        LLMRequest(prompt="measure latency"),
    )

    stats = gateway._router.get_stats(provider)

    assert stats.requests == 1
    assert stats.successes == 1
    assert stats.failures == 0
    assert stats.average_latency_seconds > 0
    assert stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_gateway_router_explores_all_providers() -> None:
    class NamedProvider:
        def __init__(
            self,
            provider_name: str,
        ) -> None:
            self.name = provider_name
            self.calls = 0

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            self.calls += 1

            return LLMResponse(
                content=f"response from {self.name}",
                model=f"{self.name}-model",
            )

    mistral = NamedProvider("mistral")
    groq = NamedProvider("groq")
    gemini = NamedProvider("gemini")

    gateway = LLMGateway(
        [mistral, groq, gemini],
        Settings(
            llm_max_retries=0,
        ),
    )

    first = await gateway.generate(
        LLMRequest(prompt="request 1"),
    )

    second = await gateway.generate(
        LLMRequest(prompt="request 2"),
    )

    third = await gateway.generate(
        LLMRequest(prompt="request 3"),
    )

    assert first.model == "mistral-model"
    assert second.model == "groq-model"
    assert third.model == "gemini-model"

    assert mistral.calls == 1
    assert groq.calls == 1
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_gateway_router_prefers_faster_provider_after_exploration() -> None:
    class TimedProvider:
        def __init__(
            self,
            provider_name: str,
            delay_seconds: float,
        ) -> None:
            self.name = provider_name
            self.delay_seconds = delay_seconds
            self.calls = 0

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            self.calls += 1

            await asyncio.sleep(
                self.delay_seconds,
            )

            return LLMResponse(
                content=f"response from {self.name}",
                model=f"{self.name}-model",
            )

    slow = TimedProvider(
        "mistral",
        0.02,
    )

    fast = TimedProvider(
        "groq",
        0.001,
    )

    gateway = LLMGateway(
        [slow, fast],
        Settings(
            llm_max_retries=0,
        ),
    )

    # Exploration phase.
    first = await gateway.generate(
        LLMRequest(prompt="explore slow"),
    )

    second = await gateway.generate(
        LLMRequest(prompt="explore fast"),
    )

    assert first.model == "mistral-model"
    assert second.model == "groq-model"

    # Optimization phase.
    optimized = await gateway.generate(
        LLMRequest(prompt="choose best"),
    )

    assert optimized.model == "groq-model"

    assert slow.calls == 1
    assert fast.calls == 2


@pytest.mark.asyncio
async def test_gateway_failure_updates_router_health() -> None:
    class FailingProvider:
        name = "mistral"

        async def generate(
            self,
            request: LLMRequest,
        ) -> LLMResponse:
            raise LLMProviderUnavailableError(
                "provider unavailable",
            )

    provider = FailingProvider()

    gateway = LLMGateway(
        [provider],
        Settings(
            llm_max_retries=0,
        ),
    )

    for _ in range(3):
        with pytest.raises(
            LLMProviderUnavailableError,
            match="provider unavailable",
        ):
            await gateway.generate(
                LLMRequest(prompt="failure"),
            )

    stats = gateway._router.get_stats(provider)

    assert stats.requests == 3
    assert stats.successes == 0
    assert stats.failures == 3
    assert stats.consecutive_failures == 3
    assert not stats.is_healthy
