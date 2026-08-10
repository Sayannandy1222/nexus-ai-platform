from __future__ import annotations

from nexus.core.config import Settings
from nexus.llm.factory import build_llm_providers
from nexus.llm.http.client import HTTPClientPool
from nexus.llm.providers.gemini import GeminiLLMProvider
from nexus.llm.providers.groq import GroqLLMProvider
from nexus.llm.providers.mistral import MistralLLMProvider


def test_factory_injects_shared_http_client() -> None:
    settings = Settings(
        llm_provider="mistral,groq,gemini",
        mistral_api_key="mistral-test-key",
        groq_api_key="groq-test-key",
        gemini_api_key="gemini-test-key",
    )

    http_client = HTTPClientPool()

    providers = build_llm_providers(
        settings,
        http_client=http_client,
    )

    try:
        assert len(providers) == 3

        assert isinstance(providers[0], MistralLLMProvider)
        assert isinstance(providers[1], GroqLLMProvider)
        assert isinstance(providers[2], GeminiLLMProvider)

        assert providers[0]._http_client is http_client
        assert providers[1]._http_client is http_client
        assert providers[2]._http_client is http_client

    finally:
        import asyncio

        asyncio.run(http_client.close())
