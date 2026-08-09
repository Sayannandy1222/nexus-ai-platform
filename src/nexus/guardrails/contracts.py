from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GuardrailAction(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action is GuardrailAction.ALLOW
