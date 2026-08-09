import asyncio

import pytest

from nexus.core.config import Settings
from nexus.llm.errors import (
    LLMProviderAuthenticationError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
)
from nexus.llm.gateway import LLMGateway
from nexus.llm.models import LLMRequest, LLMResponse
from nexus.llm.providers.fake import FakeLLMProvider


@pytest.mark.asyncio
async def test_gateway_generates_response() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway(provider, Settings())

    response = await gateway.generate(
        LLMRequest(prompt="Hello Nexus"),
    )

    assert response.content == "Generated response for: Hello Nexus"
    assert response.model == "fake-model"


@pytest.mark.asyncio
async def test_gateway_delegates_to_provider() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway(provider, Settings())

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
        SlowLLMProvider(),
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

    gateway = LLMGateway(provider, settings)

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

    gateway = LLMGateway(provider, settings)

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

    gateway = LLMGateway(provider, settings)

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

    gateway = LLMGateway(provider, settings)

    response = await gateway.generate(
        LLMRequest(prompt="retry rate limit"),
    )

    assert response.content == "success after retry"
    assert provider.calls == 2
