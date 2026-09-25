"""A cut-off or broken structured answer is a recoverable failure, not a reply (#21).

When the model stops at `max_tokens`, or returns JSON that does not close, the
text used to be kept as the answer and persisted with `status="sent"`. These
tests hold the two checks that stop that, on both invocation paths, and hold
that the failure still carries the provider's usage evidence so the student's
reserved allowance can be released.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from stoa.routers import conversations
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import ai_service
from test_conversation_token_finalization import (
    NOW,
    _command,
    _patch_allowance_table,
    _ResponseBody,
)
from test_conversations import _actor
from test_token_allowances import AtomicAllowanceTable


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The message route enriches the prompt from table reads; keep them out."""


_COMPLETE = json.dumps(
    {
        "steps": ["Schritt eins", "Schritt zwei"],
        "answer": "Die vollständige Antwort",
        "hints": ["Ein Hinweis"],
        "similar_exercises": [],
        "knowledge_points": ["Brüche"],
        "suggest_teacher": False,
    },
    ensure_ascii=False,
)
_TRUNCATED = '{"steps":["Schritt eins","Schritt zwei"],"answer":"Die vollständige Ant'
_TRUNCATED_FENCED = "```json\n" + _TRUNCATED


class _Provider:
    """CountTokens plus both InvokeModel shapes, replying with fixed text."""

    def __init__(self, *, text: str, stop_reason: str) -> None:
        self.text = text
        self.stop_reason = stop_reason
        self.invoke_calls: list[dict[str, object]] = []

    def count_tokens(self, **_kwargs: object) -> dict[str, object]:
        return {
            "inputTokens": 90,
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "count-request-1"},
        }

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": self.stop_reason,
                    "usage": {"input_tokens": 70, "output_tokens": 2048},
                    "content": [{"text": self.text}],
                }
            ),
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "invoke-request-1"},
        }

    def invoke_model_with_response_stream(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        events: list[dict[str, Any]] = [
            {
                "type": "message_start",
                "message": {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "usage": {"input_tokens": 70},
                },
            },
            *(
                {"type": "content_block_delta", "delta": {"text": self.text[i : i + 16]}}
                for i in range(0, len(self.text), 16)
            ),
            {
                "type": "message_delta",
                "delta": {"stop_reason": self.stop_reason},
                "usage": {"output_tokens": 2048},
            },
        ]
        return {
            "body": [{"chunk": {"bytes": json.dumps(event).encode()}} for event in events],
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "invoke-request-1"},
        }


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str,
    stop_reason: str,
    streamed: bool,
) -> tuple[AtomicAllowanceTable, dict[str, object], Any]:
    """Run get_ai_answer through the real allowance client; return the outcome."""
    table = AtomicAllowanceTable()
    provider = _Provider(text=text, stop_reason=stop_reason)
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(ai_service.boto3, "client", lambda *_a, **_k: provider)
    command = _command()
    client = conversations._ConversationAllowanceBedrockClient(command)
    kwargs: dict[str, Any] = {
        "content": "Wie kürze ich Brüche?",
        "subject": "math",
        "grade": "Grade 6",
        "effect_id": client.allowance_effect_id,
        "client": client,
        "observed_at": NOW,
    }
    if streamed:
        kwargs["on_step"] = lambda _index, _step: None
    try:
        outcome: Any = ai_service.get_ai_answer(**kwargs)
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


def test_a_complete_object_followed_by_stray_text_is_still_read() -> None:
    """Control: the parser's existing rescue for trailing text still applies."""
    parsed = ai_service._parse_ai_response(_COMPLETE + "\n\nViel Erfolg!")
    assert parsed["answer"] == "Die vollständige Antwort"


def test_the_raw_text_fallback_does_not_readmit_a_json_object() -> None:
    """Valid JSON with neither steps nor answer is not shown to the student raw."""
    raw = json.dumps({"steps": [], "answer": "", "hints": ["x"]})
    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        ai_service._validate_output(ai_service._parse_ai_response(raw), raw)
    assert captured.value.category == "malformed_response"


def test_prose_without_json_is_still_kept_as_the_answer() -> None:
    """Control: the raw-text fallback exists for replies that were never JSON."""
    prose = "Kürze Zähler und Nenner durch denselben Teiler."
    parsed = ai_service._validate_output(ai_service._parse_ai_response(prose), prose)
    assert parsed["answer"] == prose


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
    metadata = conversations._message_allowance_metadata_from_failure(
        outcome, allowance_effect_id=str(command["allowance_effect_id"])
    )
    assert metadata is not None
    assert conversations._observe_message_provider_usage(
        beneficiary_id="student-1", metadata=metadata
    )
    assert conversations._restore_message_allowance(
        beneficiary_id="student-1", metadata=metadata
    )

    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 2048
    assert len(table.evidence()) == 1


def test_a_failure_without_evidence_gives_no_metadata() -> None:
    failure = ai_service.AIInvocationFailure("deadline_exceeded")
    assert (
        conversations._message_allowance_metadata_from_failure(
            failure, allowance_effect_id="a" * 64
        )
        is None
    )


def _run_message_command(
    monkeypatch: pytest.MonkeyPatch, *, text: str, stop_reason: str
) -> tuple[AtomicAllowanceTable, dict[str, Any], Any]:
    """Drive the streaming message route with the real AI service and allowance."""
    table = AtomicAllowanceTable()
    provider = _Provider(text=text, stop_reason=stop_reason)
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(ai_service.boto3, "client", lambda *_a, **_k: provider)
    body = conversations.SendMessageRequest.model_validate(
        {"content": "Wie kürze ich Brüche?", "idempotencyKey": "truncation-key"}
    )
    state: dict[str, Any] = {"completed": []}

    def claim(**kwargs: Any) -> tuple[bool, int]:
        state["command"] = dict(kwargs["command"])
        return True, 1

    def complete(**kwargs: Any) -> bool:
        state["completed"].append(kwargs)
        return True

    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 8)
    monkeypatch.setattr(conversations, "_get_messages", lambda *_: [])
    monkeypatch.setattr(conversations, "_student_locale", lambda *_: "de")
    monkeypatch.setattr(
        conversations, "_publish_generation_step", lambda *_a, **_k: lambda _i, _s: None
    )
    monkeypatch.setattr(
        conversations.attachment_service,
        "prepare_message_attachments",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        conversations.attachment_service, "bind_message_attachments", lambda **_k: []
    )
    monkeypatch.setattr(
        conversations.attachment_repo, "claim_message_command_and_quota", claim
    )
    monkeypatch.setattr(
        conversations.attachment_repo, "claim_message_ai_lease", lambda **_k: (True, 1)
    )
    monkeypatch.setattr(
        conversations.attachment_repo, "renew_message_ai_lease", lambda **_k: True
    )
    monkeypatch.setattr(
        conversations.attachment_repo, "record_provider_invocation", lambda **_k: True
    )
    monkeypatch.setattr(conversations.attachment_repo, "complete_message_command", complete)
    try:
        outcome: Any = conversations._execute_message_command(
            conv_id="conv-1",
            student_id="student-1",
            subject="math",
            grade="Grade 6",
            body=body,
            command_context={
                "actor": _actor(),
                "fingerprint": conversations.message_request_fingerprint(body),
                "existing": None,
            },
        )
    except Exception as exc:
        outcome = exc
    return table, state, outcome


def test_a_truncated_streamed_answer_is_not_sent_and_its_reservation_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table, state, outcome = _run_message_command(
        monkeypatch, text=_TRUNCATED, stop_reason="max_tokens"
    )

    assert isinstance(outcome, AttachmentDecisionError)
    assert outcome.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert state["completed"] == []
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_output_tokens"] == 2048
    assert len(table.evidence()) == 1


def test_a_complete_streamed_answer_is_still_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table, state, outcome = _run_message_command(
        monkeypatch, text=_COMPLETE, stop_reason="end_turn"
    )

    assert isinstance(outcome, conversations.SendMessageResponse), outcome
    assert outcome.assistantMessage.status == "sent"
    assert "Die vollständige Antwort" in outcome.assistantMessage.content
    assert len(state["completed"]) == 1
