from __future__ import annotations

import httpx
import pytest

from nexus.llm.errors import (
    LLMProviderAuthenticationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from nexus.llm.models import LLMRequest
from nexus.llm.providers.groq import GroqLLMProvider


def make_response(
    status_code: int,
    json_data: object,
) -> httpx.Response:
    request = httpx.Request(
        "POST",
        GroqLLMProvider.BASE_URL,
    )

    return httpx.Response(
        status_code,
        json=json_data,
        request=request,
    )


@pytest.mark.asyncio
async def test_groq_provider_generates_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": "Hello from Groq",
                    },
                },
            ],
        },
    )

    async def fake_post(
        self: httpx.AsyncClient,
        *args: object,
        **kwargs: object,
    ) -> httpx.Response:
        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    provider = GroqLLMProvider(
        api_key="test-key",
    )

    result = await provider.generate(
        LLMRequest(prompt="Hello"),
    )

    assert result.content == "Hello from Groq"
    assert result.model == "llama-3.3-70b-versatile"
    assert provider.name == "groq"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (401, LLMProviderAuthenticationError),
        (403, LLMProviderAuthenticationError),
        (429, LLMProviderRateLimitError),
        (500, LLMProviderUnavailableError),
        (502, LLMProviderUnavailableError),
        (503, LLMProviderUnavailableError),
        (504, LLMProviderUnavailableError),
    ],
)
async def test_groq_provider_translates_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    exception: type[Exception],
) -> None:
    response = make_response(
        status_code,
        {"error": "test error"},
    )

    async def fake_post(
        self: httpx.AsyncClient,
        *args: object,
        **kwargs: object,
    ) -> httpx.Response:
        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    provider = GroqLLMProvider(
        api_key="test-key",
    )

    with pytest.raises(exception):
        await provider.generate(
            LLMRequest(prompt="Hello"),
        )


@pytest.mark.asyncio
async def test_groq_provider_translates_generic_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response(
        400,
        {"error": "bad request"},
    )

    async def fake_post(
        self: httpx.AsyncClient,
        *args: object,
        **kwargs: object,
    ) -> httpx.Response:
        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    provider = GroqLLMProvider(
        api_key="test-key",
    )

    with pytest.raises(
        LLMProviderError,
        match="HTTP 400",
    ):
        await provider.generate(
            LLMRequest(prompt="Hello"),
        )


@pytest.mark.asyncio
async def test_groq_provider_rejects_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request(
        "POST",
        GroqLLMProvider.BASE_URL,
    )

    response = httpx.Response(
        200,
        content=b"not-json",
        request=request,
    )

    async def fake_post(
        self: httpx.AsyncClient,
        *args: object,
        **kwargs: object,
    ) -> httpx.Response:
        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    provider = GroqLLMProvider(
        api_key="test-key",
    )

    with pytest.raises(
        LLMProviderResponseError,
        match="invalid JSON",
    ):
        await provider.generate(
            LLMRequest(prompt="Hello"),
        )


@pytest.mark.asyncio
async def test_groq_provider_rejects_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = make_response(
        200,
        {
            "choices": [],
        },
    )

    async def fake_post(
        self: httpx.AsyncClient,
        *args: object,
        **kwargs: object,
    ) -> httpx.Response:
        return response

    monkeypatch.setattr(
        httpx.AsyncClient,
        "post",
        fake_post,
    )

    provider = GroqLLMProvider(
        api_key="test-key",
    )

    with pytest.raises(
        LLMProviderResponseError,
        match="no choices",
    ):
        await provider.generate(
            LLMRequest(prompt="Hello"),
        )
