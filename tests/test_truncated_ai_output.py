"""A cut-off or broken structured answer is a recoverable failure, not a reply (#21).

When the model stops at `max_tokens`, or returns JSON that does not close, the
text used to be kept as the answer and persisted with `status="sent"`. These
tests hold the two checks that stop that, on both invocation paths, and hold
that the failure still carries the provider's usage evidence so the student's
reserved allowance can be released. The JSON is now the input of the forced
tool call (#412); the fakes stream it as `input_json_delta` pieces.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fakes.ask_question import (
    NOW,
    _COMPLETE,
    _command,
    _command_row,
    _messages,
    _patch_allowance_table,
    _Provider,
    _run_message_command,
)
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from stoa import aws
from stoa.aws import Kind
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.services import ai_service, ask_answer, ask_question
from stoa.services.ask_question import _admission
from stoa.services.ask_question._admission import UsageEvidence
from stoa.services.ask_question_errors import AskQuestionErrorCode
from fakes.ask_question import AtomicAllowanceTable


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The message route enriches the prompt from table reads; keep them out."""


_TRUNCATED = '{"steps":["Schritt eins","Schritt zwei"],"answer":"Die vollstÃ¤ndige Ant'
_TRUNCATED_FENCED = "```json\n" + _TRUNCATED


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str,
    stop_reason: str,
    streamed: bool,
) -> tuple[AtomicAllowanceTable, dict[str, object], Any]:
    """Ask the model through the real allowance client; return the outcome."""
    table = AtomicAllowanceTable()
    provider = _Provider(text=text, stop_reason=stop_reason)
    _patch_allowance_table(monkeypatch, table)
    aws.install({Kind.BEDROCK_RUNTIME: provider})
    command = _command()
    client = _admission.meter(command).model()
    kwargs: dict[str, Any] = {
        "system_prompt": "Answer the question.",
        "messages": [{"role": "user", "content": "Wie kürze ich Brüche?"}],
        "input_size": 21,
        "effect_id": client.effect_id,
        "client": client,
        "observed_at": NOW,
        "tool": ask_answer.answer_tool(star_map=False),
    }
    if streamed:
        kwargs["on_step"] = lambda _index, _step: None
    try:
        outcome: Any = ai_service.invoke_answer(**kwargs)
    except ai_service.AIInvocationFailure as failure:
        outcome = failure
    return table, command, outcome


def _effect_state(table: AtomicAllowanceTable) -> str:
    effect = next(
        item for item in table.items.values() if item.get("entity_type") == "allowance_effect"
    )
    return str(effect["state"])


# ── Check one: a max_tokens stop is refused before the text is parsed ────────

@pytest.mark.parametrize("streamed", [True, False], ids=["stream", "buffered"])
def test_a_max_tokens_stop_with_broken_json_is_an_incomplete_output_failure(
    monkeypatch: pytest.MonkeyPatch, streamed: bool
) -> None:
    table, command, outcome = _invoke(
        monkeypatch, text=_TRUNCATED, stop_reason="max_tokens", streamed=streamed
    )

    assert isinstance(outcome, ai_service.AIInvocationFailure)
    assert outcome.category == "incomplete_output"
    assert outcome.usage is not None
    assert outcome.usage.input_tokens == 70
    assert outcome.usage.output_tokens == 2048
    assert outcome.usage.effect_id == command["allowance_effect_id"]
    assert _effect_state(table) == "reserved"


@pytest.mark.parametrize("streamed", [True, False], ids=["stream", "buffered"])
def test_a_max_tokens_stop_is_refused_even_when_the_json_happens_to_close(
    monkeypatch: pytest.MonkeyPatch, streamed: bool
) -> None:
    _table, _command, outcome = _invoke(
        monkeypatch, text=_COMPLETE, stop_reason="max_tokens", streamed=streamed
    )

    assert isinstance(outcome, ai_service.AIInvocationFailure)
    assert outcome.category == "incomplete_output"
    assert outcome.usage is not None


# ── Check two: JSON that does not close is never kept as the answer ─────────

@pytest.mark.parametrize("text", [_TRUNCATED, _TRUNCATED_FENCED], ids=["bare", "fenced"])
@pytest.mark.parametrize("streamed", [True, False], ids=["stream", "buffered"])
def test_broken_json_on_a_normal_stop_is_a_malformed_response(
    monkeypatch: pytest.MonkeyPatch, streamed: bool, text: str
) -> None:
    _table, _command, outcome = _invoke(
        monkeypatch, text=text, stop_reason="end_turn", streamed=streamed
    )

    assert isinstance(outcome, ai_service.AIInvocationFailure)
    assert outcome.category == "malformed_response"
    assert outcome.usage is not None
    assert outcome.usage.output_tokens == 2048


def test_the_parser_no_longer_turns_broken_json_into_the_answer() -> None:
    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service._parse_ai_response(_TRUNCATED)
    assert captured.value.category == "malformed_response"


def test_a_complete_object_followed_by_stray_text_is_refused() -> None:
    """The tool input is the API's to write (#412): nothing around it is cut away."""
    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service._parse_ai_response(_COMPLETE + "\n\nViel Erfolg!")
    assert captured.value.category == "malformed_response"


def test_the_raw_text_fallback_does_not_readmit_a_json_object() -> None:
    """Valid JSON with neither steps nor answer is not shown to the student raw."""
    raw = json.dumps({"steps": [], "answer": "", "hints": ["x"]})
    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service._validate_output(ai_service._parse_ai_response(raw), raw)
    assert captured.value.category == "malformed_response"


def test_prose_is_no_longer_kept_as_the_answer() -> None:
    """The answer is the tool's input (#412); text that is not one is refused."""
    prose = "Kürze Zähler und Nenner durch denselben Teiler."
    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service._parse_ai_response(prose)
    assert captured.value.category == "malformed_response"


# ── Controls: a complete answer on a normal stop still succeeds ──────────────

@pytest.mark.parametrize("streamed", [True, False], ids=["stream", "buffered"])
def test_a_complete_answer_still_succeeds(
    monkeypatch: pytest.MonkeyPatch, streamed: bool
) -> None:
    _table, _command, outcome = _invoke(
        monkeypatch, text=_COMPLETE, stop_reason="end_turn", streamed=streamed
    )

    assert isinstance(outcome, ai_service.AIProviderResult)
    assert outcome.content["answer"] == "Die vollständige Antwort"
    assert outcome.stop_reason == "end_turn"


# ── The recovery path releases the reservation and keeps the evidence ───────

def test_the_evidence_on_a_failure_lets_the_reservation_be_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buffered: what the conversation recovery path does with the failure."""
    table, command, outcome = _invoke(
        monkeypatch, text=_TRUNCATED, stop_reason="max_tokens", streamed=False
    )
    evidence = UsageEvidence.from_failure(
        outcome, effect_id=str(command["allowance_effect_id"])
    )
    assert evidence is not None
    allowance = _admission.meter(command)
    allowance.observe(evidence)
    allowance.restore(evidence)

    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 2048
    assert len(table.evidence()) == 1


def test_a_truncated_streamed_answer_is_not_sent_and_its_reservation_is_released(
    table, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance, outcome = _run_message_command(
        monkeypatch, text=_TRUNCATED, stop_reason="max_tokens"
    )

    assert isinstance(outcome, AttachmentDecisionError)
    # Paid for and unusable, the message failed for good; no upload was in it (#412).
    assert outcome.code is AskQuestionErrorCode.MESSAGE_FAILED
    assert _command_row(table, "truncation-key")["status"] == "failed"
    assert _messages(table, "assistant") == []
    counter = allowance.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_output_tokens"] == 2048
    assert len(allowance.evidence()) == 1


def test_a_complete_streamed_answer_is_still_sent(
    table, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allowance, outcome = _run_message_command(
        monkeypatch, text=_COMPLETE, stop_reason="end_turn"
    )

    assert isinstance(outcome, ask_question.Answered), outcome
    assert outcome.assistantMessage.status == "sent"
    assert "Die vollständige Antwort" in outcome.assistantMessage.content
    assert _command_row(table, "truncation-key")["status"] == "completed"
