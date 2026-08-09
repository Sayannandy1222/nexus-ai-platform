from __future__ import annotations

from nexus.core.config import Settings
from nexus.llm.errors import LLMProviderError
from nexus.llm.protocol import LLMProvider
from nexus.llm.providers.mistral import MistralLLMProvider


def build_llm_providers(settings: Settings) -> list[LLMProvider]:
    """
    Build the configured LLM provider chain.

    Providers are ordered by preference. The LLM gateway uses this
    order for retry and fallback behavior.
    """

    provider_names = [
        name.strip().lower() for name in settings.llm_provider.split(",") if name.strip()
    ]

    if not provider_names:
        raise ValueError("at least one LLM provider must be configured")

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
                ),
            )

        elif provider_name == "fake":
            from nexus.llm.providers.fake import FakeLLMProvider

            providers.append(FakeLLMProvider())

        else:
            raise ValueError(
                f"unsupported LLM provider: {provider_name}",
            )

    return providers
