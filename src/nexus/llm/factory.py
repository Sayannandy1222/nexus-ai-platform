from __future__ import annotations

from nexus.core.config import Settings
from nexus.llm.errors import LLMProviderError
from nexus.llm.http.client import HTTPClientPool
from nexus.llm.protocol import LLMProvider
from nexus.llm.providers.gemini import GeminiLLMProvider
from nexus.llm.providers.groq import GroqLLMProvider
from nexus.llm.providers.mistral import MistralLLMProvider


def build_llm_providers(
    settings: Settings,
    http_client: HTTPClientPool | None = None,
) -> list[LLMProvider]:
    """
    Build the configured LLM provider chain.

    Provider order determines fallback order.

    Example:

        LLM_PROVIDER=mistral,groq,gemini

    creates:

        Mistral -> Groq -> Gemini

    The shared HTTP client is injected into every provider so
    connections can be reused across requests.
    """

    provider_names = [
        name.strip().lower() for name in settings.llm_provider.split(",") if name.strip()
    ]

    if not provider_names:
        raise ValueError(
            "at least one LLM provider must be configured",
        )

    providers: list[LLMProvider] = []

    for provider_name in provider_names:
        if provider_name == "mistral":
            if not settings.mistral_api_key:
                raise LLMProviderError(
                    "Mistral provider selected but MISTRAL_API_KEY is not configured",
                )

            providers.append(
                MistralLLMProvider(
                    api_key=settings.mistral_api_key,
                    model=settings.mistral_model,
                    http_client=http_client,
                ),
            )

        elif provider_name == "groq":
            if not settings.groq_api_key:
                raise LLMProviderError(
                    "Groq provider selected but GROQ_API_KEY is not configured",
                )

            providers.append(
                GroqLLMProvider(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    http_client=http_client,
                ),
            )

        elif provider_name == "gemini":
            if not settings.gemini_api_key:
                raise LLMProviderError(
                    "Gemini provider selected but GEMINI_API_KEY is not configured",
                )

            providers.append(
                GeminiLLMProvider(
                    api_key=settings.gemini_api_key,
                    model=settings.gemini_model,
                    http_client=http_client,
                ),
            )

        elif provider_name == "fake":
            from nexus.llm.providers.fake import FakeLLMProvider

            providers.append(
                FakeLLMProvider(),
            )

        else:
            raise ValueError(
                f"unsupported LLM provider: {provider_name}",
            )

    return providers
