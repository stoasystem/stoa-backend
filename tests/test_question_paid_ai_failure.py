"""A paid-for but unusable AI answer on the question route is a known result (#21, E14).

Since the conversation route learned to fail a cut-off or broken answer, the
question route received the same failure - carrying the provider's usage - and
treated it like a timeout: the effect went to `provider_outcome_unknown` and
the student's reservation stayed held. But the outcome is not unknown: the
provider answered, was paid, and the answer cannot be used. So the cost is
recorded from the failure's usage, the reservation is restored, and the effect
goes terminal as `provider_rejected`; replaying the command does not call the
model again. A failure without usage (a timeout) is still unknown.
"""

from __future__ import annotations

import copy
import json

import pytest

from test_phase475_question_effect_recovery import (
    EffectRecoveryTable,
    _client,
    _effect,
    _request,
)
from test_question_token_finalization import (
    MockBedrockProvider,
    _ResponseBody,
    _allowance_effect,
    _patch_allowance_runtime,
)
from test_token_allowances import AtomicAllowanceTable


_TRUNCATED = '{"steps":["Subtract four","Divide by tw'


class _UnusableAnswerProvider(MockBedrockProvider):
    """Answers once per call with a reply the service must refuse."""

    def __init__(self, *, text: str, stop_reason: str) -> None:
        super().__init__()
        self.text = text
        self.stop_reason = stop_reason

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": self.stop_reason,
                    "usage": {
                        "input_tokens": self.actual_input_tokens,
                        "output_tokens": self.actual_output_tokens,
                    },
                    "content": [{"text": self.text}],
                }
            ),
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "invoke-request-1"},
        }


_UNUSABLE = [
    pytest.param(_TRUNCATED, "max_tokens", id="max_tokens"),
    pytest.param(_TRUNCATED, "end_turn", id="broken_json"),
]


def _arrange(monkeypatch, provider):
    question_table = EffectRecoveryTable()
    allowance_table = AtomicAllowanceTable()
    _patch_allowance_runtime(
        monkeypatch,
        question_table=question_table,
        allowance_table=allowance_table,
        provider=provider,
    )
    return question_table, allowance_table


def _assert_known_paid_failure(question_table, allowance_table, provider) -> None:
    effect = _effect(question_table, "ai")
    assert effect["status"] in {"terminal_rejected", "terminal_proven"}
    assert effect["terminal_failure_code"] == "provider_rejected"
    assert _allowance_effect(allowance_table)["state"] == "restored"
    counter = allowance_table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 80
    assert counter["provider_cost_output_tokens"] == 30
    assert len(allowance_table.evidence()) == 1
    assert len(provider.invoke_calls) == 1


@pytest.mark.parametrize(("text", "stop_reason"), _UNUSABLE)
def test_an_unusable_paid_answer_is_terminal_and_restored(
    monkeypatch, text: str, stop_reason: str
) -> None:
    provider = _UnusableAnswerProvider(text=text, stop_reason=stop_reason)
    question_table, allowance_table = _arrange(monkeypatch, provider)

    response = _client().post("/questions", json=_request())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "question_submission_terminal_failed"
    _assert_known_paid_failure(question_table, allowance_table, provider)

    replay = _client().post("/questions", json=_request())
    assert replay.status_code == 409
    assert len(provider.invoke_calls) == 1


@pytest.mark.parametrize(("text", "stop_reason"), _UNUSABLE)
def test_an_unusable_paid_answer_on_the_recovery_path_is_terminal_and_restored(
    monkeypatch, text: str, stop_reason: str
) -> None:
    """The replay that recreates a lost intent takes the same decision."""
    provider = _UnusableAnswerProvider(text=text, stop_reason=stop_reason)
    question_table, allowance_table = _arrange(monkeypatch, provider)
    question_table.fail_intent_before_commit = 1

    first = _client().post("/questions", json=_request())
    assert first.status_code == 201 and first.json()["status"] == "pending"
    assert provider.invoke_calls == []

    second = _client().post("/questions", json=_request())

    assert second.status_code == 409
    _assert_known_paid_failure(question_table, allowance_table, provider)
    third = _client().post("/questions", json=_request())
    assert third.status_code == 409
    assert len(provider.invoke_calls) == 1


def test_a_failure_without_usage_is_still_an_unknown_outcome(monkeypatch) -> None:
    """Control: a timeout carries no usage, so nobody knows what the provider did."""
    provider = MockBedrockProvider(invoke_error=TimeoutError("timeout-canary"))
    question_table, allowance_table = _arrange(monkeypatch, provider)

    response = _client().post("/questions", json=_request())

    assert response.status_code == 201
    assert _effect(question_table, "ai")["status"] == "provider_outcome_unknown"
    assert _allowance_effect(allowance_table)["state"] == "reserved"
    assert allowance_table.evidence() == []


def test_a_complete_answer_still_succeeds(monkeypatch) -> None:
    provider = MockBedrockProvider()
    question_table, _allowance_table = _arrange(monkeypatch, provider)

    response = _client().post("/questions", json=_request())

    assert response.status_code == 201
    assert response.json()["status"] == "ai_answered"
    assert json.dumps(response.json()["ai_response"])
    assert _effect(question_table, "ai")["status"] == "completed"
