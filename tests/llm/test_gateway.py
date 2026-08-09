import pytest

from nexus.llm.gateway import LLMGateway
from nexus.llm.models import LLMRequest
from nexus.llm.providers.fake import FakeLLMProvider


@pytest.mark.asyncio
async def test_gateway_generates_response() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway(provider)

    response = await gateway.generate(
        LLMRequest(prompt="Hello Nexus"),
    )

    assert response.content == "Generated response for: Hello Nexus"
    assert response.model == "fake-model"


@pytest.mark.asyncio
async def test_gateway_delegates_to_provider() -> None:
    provider = FakeLLMProvider()
    gateway = LLMGateway(provider)

    await gateway.generate(
        LLMRequest(prompt="first"),
    )

    await gateway.generate(
        LLMRequest(prompt="second"),
    )

    assert provider.calls == 2
