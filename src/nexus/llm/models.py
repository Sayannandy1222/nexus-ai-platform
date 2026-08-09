from dataclasses import dataclass


@dataclass(frozen=True)
class LLMRequest:
    prompt: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
