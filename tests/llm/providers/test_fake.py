import pytest

from nexus.llm.models import LLMRequest
from nexus.llm.providers.fake import FakeLLMProvider


@pytest.mark.asyncio
async def test_fake_provider_generates_response() -> None:
    provider = FakeLLMProvider()

    response = await provider.generate(
        LLMRequest(prompt="Hello"),
    )

    assert response.content == "Generated response for: Hello"
    assert response.model == "fake-model"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_fake_provider_tracks_multiple_calls() -> None:
    provider = FakeLLMProvider()

    await provider.generate(LLMRequest(prompt="first"))
    await provider.generate(LLMRequest(prompt="second"))

    assert provider.calls == 2
