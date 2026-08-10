from __future__ import annotations

import httpx
import pytest

from nexus.llm.http.client import HTTPClientPool
from nexus.llm.models import LLMRequest
from nexus.llm.providers.gemini import GeminiLLMProvider
from nexus.llm.providers.groq import GroqLLMProvider
from nexus.llm.providers.mistral import MistralLLMProvider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_class", "api_key"),
    [
        (MistralLLMProvider, "mistral-test-key"),
        (GroqLLMProvider, "groq-test-key"),
        (GeminiLLMProvider, "gemini-test-key"),
    ],
)
async def test_provider_uses_shared_http_client(
    provider_class: type,
    api_key: str,
) -> None:
    pool = HTTPClientPool()

    provider = provider_class(
        api_key=api_key,
        http_client=pool,
    )

    try:
        assert provider._http_client is pool

        await pool.start()

        assert provider._http_client.client is pool.client

    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_shared_pool_can_be_used_by_multiple_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = HTTPClientPool()

    mistral = MistralLLMProvider(
        api_key="mistral-test-key",
        http_client=pool,
    )

    groq = GroqLLMProvider(
        api_key="groq-test-key",
        http_client=pool,
    )

    gemini = GeminiLLMProvider(
        api_key="gemini-test-key",
        http_client=pool,
    )

    calls: list[str] = []

    async def fake_post(
        self: httpx.AsyncClient,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        calls.append(url)

        if "mistral.ai" in url:
            data = {
                "choices": [
                    {
                        "message": {
                            "content": "mistral response",
                        },
                    },
                ],
            }

        elif "groq.com" in url:
            data = {
                "choices": [
                    {
                        "message": {
                            "content": "groq response",
                        },
                    },
                ],
            }

        else:
            data = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "gemini response",
                                },
                            ],
                        },
                    },
                ],
            }

        return httpx.Response(
            200,
            json=data,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    try:
        await pool.start()

        mistral_response = await mistral.generate(
            LLMRequest(prompt="hello"),
        )

        groq_response = await groq.generate(
            LLMRequest(prompt="hello"),
        )

        gemini_response = await gemini.generate(
            LLMRequest(prompt="hello"),
        )

        assert mistral_response.content == "mistral response"
        assert groq_response.content == "groq response"
        assert gemini_response.content == "gemini response"

        assert len(calls) == 3

    finally:
        await pool.close()
