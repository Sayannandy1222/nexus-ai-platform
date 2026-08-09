from dataclasses import dataclass


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    model: str | None = None
    max_tokens: int = 512
    temperature: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
