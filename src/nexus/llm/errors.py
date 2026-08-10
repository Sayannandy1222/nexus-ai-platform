class LLMProviderError(Exception):
    """Base exception for LLM provider failures."""


class LLMProviderTimeoutError(LLMProviderError):
    """The provider request timed out."""


class LLMProviderRateLimitError(LLMProviderError):
    """The provider rejected the request because of rate limiting."""


class LLMProviderAuthenticationError(LLMProviderError):
    """The provider rejected the supplied credentials."""


class LLMProviderUnavailableError(LLMProviderError):
    """The provider is temporarily unavailable."""


class LLMProviderResponseError(LLMProviderError):
    """The provider returned an invalid or unexpected response."""
