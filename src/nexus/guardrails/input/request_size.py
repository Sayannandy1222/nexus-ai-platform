from __future__ import annotations

from nexus.guardrails.contracts import GuardrailAction, GuardrailResult


class RequestSizeGuardrail:
    def __init__(self, max_characters: int = 50_000) -> None:
        if max_characters <= 0:
            raise ValueError("max_characters must be positive")

        self._max_characters = max_characters

    def evaluate(self, text: str) -> GuardrailResult:
        if len(text) > self._max_characters:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                reason="request exceeds maximum allowed size",
            )

        return GuardrailResult(action=GuardrailAction.ALLOW)
