from nexus.guardrails.contracts import GuardrailAction
from nexus.guardrails.input.request_size import RequestSizeGuardrail


def test_request_within_limit_is_allowed() -> None:
    guardrail = RequestSizeGuardrail(max_characters=10)

    result = guardrail.evaluate("hello")

    assert result.action is GuardrailAction.ALLOW
    assert result.allowed


def test_request_over_limit_is_blocked() -> None:
    guardrail = RequestSizeGuardrail(max_characters=10)

    result = guardrail.evaluate("this request is too large")

    assert result.action is GuardrailAction.BLOCK
    assert not result.allowed
