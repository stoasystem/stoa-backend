"""准入: a question's answer charged to the student's weekly allowance (#206).

Everything goes through `_admission`'s meter and usage evidence, on the real
ledger over an in-memory allowance table, with only the Bedrock runtime faked.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from decimal import Decimal

import pytest

from fakes.ask_question import (
    NOW,
    AtomicAllowanceTable,
    CommandResult,
    Disposition,
    _command,
    _patch_allowance_table,
    _ResponseBody,
)
from stoa.db.repositories import allowance_repo
from stoa.routers import conversations
from stoa.services import ai_service, allowance_service
from stoa.services.ask_question import _admission, _answering
from stoa.services.ask_question._admission import AdmissionError, UsageEvidence
from stoa.services.ask_question.errors import AskQuestionErrorCode


class MockBedrockProvider:
    """CountTokens plus InvokeModel fake; no network/provider access."""

    def __init__(
        self,
        *,
        input_tokens: object = 90,
        actual_input_tokens: int = 70,
        actual_output_tokens: int = 25,
        invoke_error: Exception | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.actual_input_tokens = actual_input_tokens
        self.actual_output_tokens = actual_output_tokens
        self.invoke_error = invoke_error
        self.count_calls: list[dict[str, object]] = []
        self.invoke_calls: list[dict[str, object]] = []

    def count_tokens(self, **kwargs: object) -> dict[str, object]:
        self.count_calls.append(copy.deepcopy(kwargs))
        return {
            "inputTokens": self.input_tokens,
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "count-request-1",
            },
        }

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.invoke_calls.append(copy.deepcopy(kwargs))
        if self.invoke_error is not None:
            raise self.invoke_error
        content = {
            "answer": "The durable conversation answer",
            "steps": ["First durable step"],
            "hints": ["The same durable hint"],
            "similar_exercises": [],
            "knowledge_points": ["fractions"],
        }
        return {
            "body": _ResponseBody(
                {
                    "id": "provider-message-1",
                    "model": "anthropic.claude-sonnet-4-6",
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": self.actual_input_tokens,
                        "output_tokens": self.actual_output_tokens,
                    },
                    "content": [{"text": json.dumps(content)}],
                }
            ),
            "ResponseMetadata": {
                "HTTPStatusCode": 200,
                "RequestId": "invoke-request-1",
            },
        }


def _use(
    monkeypatch: pytest.MonkeyPatch,
    table: AtomicAllowanceTable,
    provider: MockBedrockProvider,
) -> None:
    _patch_allowance_table(monkeypatch, table)
    monkeypatch.setattr(ai_service.boto3, "client", lambda *_a, **_k: provider)


def _ask(metered: _admission.MeteredModel) -> ai_service.AIProviderResult[dict[str, object]]:
    return ai_service.invoke_answer(
        "Answer the question.",
        [{"role": "user", "content": "private-message-canary"}],
        input_size=1,
        correlation_id="transport-correlation-that-must-not-own-the-effect",
        effect_id=metered.effect_id,
        client=metered,
        observed_at=NOW,
    )


def _answered(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: AtomicAllowanceTable,
    provider: MockBedrockProvider,
) -> tuple[dict[str, object], UsageEvidence]:
    """A command whose answer came back, and the evidence of what it cost."""
    _use(monkeypatch, table, provider)
    command = _command()
    result = _ask(_admission.meter(command).model())
    evidence = UsageEvidence.from_provider(
        result, effect_id=str(command["allowance_effect_id"])
    )
    return command, evidence


def _effect(table: AtomicAllowanceTable) -> dict[str, object]:
    return next(
        item
        for item in table.items.values()
        if item.get("entity_type") == "allowance_effect"
    )


def _response(content: str = "answer") -> conversations.SendMessageResponse:
    return conversations.SendMessageResponse(
        studentMessage=conversations.ChatMessage(
            id="student-message-1",
            conversationId="conversation-1",
            role="student",
            content="private-message-canary",
            createdAt=NOW.isoformat(),
        ),
        assistantMessage=conversations.ChatMessage(
            id="assistant-message-1",
            conversationId="conversation-1",
            role="assistant",
            content=content,
            createdAt=NOW.isoformat(),
        ),
    )


def _completed(
    command: dict[str, object],
    response: conversations.SendMessageResponse,
    evidence: UsageEvidence,
) -> CommandResult:
    return CommandResult(
        Disposition.COMPLETED,
        command={
            **command,
            "status": "completed",
            "student_message_id": "student-message-1",
            "result_json": _answering._message_result_json(response, evidence),
        },
    )


# ── Before the model is called ────────────────────────────────────────────────


def test_count_failure_never_reserves_or_invokes(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider(input_tokens="not-an-exact-count")
    _use(monkeypatch, table, provider)

    with pytest.raises(AdmissionError) as captured:
        _ask(_admission.meter(_command()).model())

    assert captured.value.code is AskQuestionErrorCode.PROVIDER_TOKEN_COUNT_UNAVAILABLE
    assert captured.value.status_code == 503
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []
    assert not any(
        item.get("entity_type") == "allowance_effect"
        for item in table.items.values()
    )


def test_allowance_denial_never_invokes_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    _use(monkeypatch, table, provider)
    monkeypatch.setattr(
        allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: allowance_repo.ReservationResult(
            allowance_repo.ReservationDisposition.LIMIT_EXCEEDED
        ),
    )

    with pytest.raises(AdmissionError) as captured:
        _ask(_admission.meter(_command()).model())

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_EXHAUSTED
    assert captured.value.status_code == 429
    assert len(provider.count_calls) == 1
    assert provider.invoke_calls == []


def test_a_command_whose_allowance_identity_does_not_hold_is_refused() -> None:
    command = {**_command(), "allowance_week_identity": "1999-W01"}

    with pytest.raises(AdmissionError) as captured:
        _admission.meter(command).model()

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE


def test_provider_timeout_after_reserve_remains_reserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider(invoke_error=TimeoutError("timeout-canary"))
    _use(monkeypatch, table, provider)

    with pytest.raises(TimeoutError):
        _ask(_admission.meter(_command()).model())

    assert _effect(table)["state"] == "reserved"
    assert table.counter()["finalized_input_tokens"] == 0
    assert len(provider.invoke_calls) == 1


# ── After it answered ─────────────────────────────────────────────────────────


def test_store_ambiguity_keeps_observed_reservation_without_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())

    _admission.meter(command).observe(evidence)

    assert _effect(table)["state"] == "observed"
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 90
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70


def test_evidence_is_stored_in_the_shape_written_before_it_had_a_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())

    stored = evidence.to_json()

    assert set(stored) == {
        "allowance_effect_id",
        "provider_usage_evidence_id",
        "allowance_finalization_status",
        "provider_request_id_digest",
        "provider_model_id_digest",
        "provider_input_tokens",
        "provider_output_tokens",
    }
    assert stored["allowance_effect_id"] == command["allowance_effect_id"]
    assert stored["allowance_finalization_status"] == "durable_result_boundary"
    assert UsageEvidence.from_json(json.loads(json.dumps(stored))) == evidence


def test_stored_token_counts_are_observed_as_the_table_returns_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evidence reads whole numbers, not only `int` ones."""
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())
    stored = {
        **evidence.to_json(),
        "provider_input_tokens": Decimal(evidence.input_tokens),
        "provider_output_tokens": Decimal(evidence.output_tokens),
    }

    read = UsageEvidence.from_json(stored)
    assert read is not None
    _admission.meter(command).observe(read)
    assert table.counter()["provider_cost_input_tokens"] == 70

    # Negative control: reading the stored shape is not reading anything.
    for malformed in (Decimal("70.5"), True, "70", None):
        assert UsageEvidence.from_json({**stored, "provider_input_tokens": malformed}) is None
    assert UsageEvidence.from_json({**stored, "allowance_effect_id": "not-a-digest"}) is None
    assert UsageEvidence.from_json(None) is None


def test_a_failure_without_evidence_gives_none() -> None:
    failure = ai_service.AIInvocationFailure("deadline_exceeded")
    assert UsageEvidence.from_failure(failure, effect_id="a" * 64) is None


def test_evidence_of_another_effect_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())
    other = UsageEvidence.from_json({**evidence.to_json(), "allowance_effect_id": "b" * 64})
    assert other is not None

    with pytest.raises(AdmissionError) as captured:
        _admission.meter(command).observe(other)

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE
    assert table.evidence() == []


def test_regular_and_sse_replay_finalize_one_exact_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider()
    command, evidence = _answered(monkeypatch, table=table, provider=provider)
    _admission.meter(command).observe(evidence)
    response = _response(
        "1. First durable step\n\nThe durable conversation answer"
        "\n\n**Hinweis:** The same durable hint"
    )

    regular = _answering._result_response(_completed(command, response, evidence))
    sse = _answering._result_response(_completed(command, response, evidence))

    assert regular == sse == response
    assert len(provider.invoke_calls) == 1
    counter = table.counter()
    assert counter["finalized_input_tokens"] == 70
    assert counter["finalized_output_tokens"] == 25
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 25
    assert len(table.evidence()) == 1


def test_finalize_timeout_repairs_from_the_same_durable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())
    _admission.meter(command).observe(evidence)
    response = _response()
    real_finalize = allowance_service.finalize_token_allowance
    calls = 0

    def retry_once(
        *,
        beneficiary_id: str,
        effect_id: str,
        technical_validation_passed: bool,
        safety_check_passed: bool,
        durable_result_stored: bool,
        stable_replay_readable: bool,
        finalized_at: datetime | None = None,
        table: object | None = None,
    ) -> allowance_repo.FinalizationResult:
        nonlocal calls
        del table
        calls += 1
        if calls == 1:
            return allowance_repo.FinalizationResult(
                allowance_repo.FinalizationDisposition.RETRYABLE
            )
        return real_finalize(
            beneficiary_id=beneficiary_id,
            effect_id=effect_id,
            technical_validation_passed=technical_validation_passed,
            safety_check_passed=safety_check_passed,
            durable_result_stored=durable_result_stored,
            stable_replay_readable=stable_replay_readable,
            finalized_at=finalized_at,
        )

    monkeypatch.setattr(allowance_service, "finalize_token_allowance", retry_once)

    with pytest.raises(AdmissionError) as captured:
        _answering._result_response(_completed(command, response, evidence))
    replay = _answering._result_response(_completed(command, response, evidence))

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE
    assert replay == response
    assert table.counter()["finalized_input_tokens"] == 70
    assert table.counter()["finalized_output_tokens"] == 25


def test_terminal_validation_restores_user_and_retains_provider_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())
    allowance = _admission.meter(command)

    allowance.observe(evidence)
    allowance.restore(evidence)

    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0
    assert counter["finalized_input_tokens"] == 0
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 25
    assert len(table.evidence()) == 1


def test_durable_payload_is_private_and_content_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=MockBedrockProvider())
    response = _response("private-answer-canary")
    public = _answering._completed_command_response(
        _completed(command, response, evidence).command or {}
    )

    assert public == response
    assert "allowance_effect_id" not in public.model_dump_json()
    assert "provider_usage_evidence_id" not in public.model_dump_json()
    evidence_json = json.dumps(table.evidence(), default=str)
    assert "private-message-canary" not in evidence_json
    assert "private-answer-canary" not in evidence_json


# ── The sweep: cost not known ─────────────────────────────────────────────────


def test_release_returns_a_reservation_whose_cost_is_not_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = MockBedrockProvider(invoke_error=TimeoutError("timeout-canary"))
    _use(monkeypatch, table, provider)
    real_release = allowance_service.release_unknown_cost_allowance
    monkeypatch.setattr(
        allowance_service,
        "release_unknown_cost_allowance",
        lambda **kwargs: real_release(**kwargs, table=table),
    )
    command = _command()
    with pytest.raises(TimeoutError):
        _ask(_admission.meter(command).model())

    assert _admission.meter(command).release() is True
    # Settled already: a second run releases nothing.
    assert _admission.meter(command).release() is False
    counter = table.counter()
    assert counter["reserved_input_tokens"] == 0
    assert counter["reserved_output_tokens"] == 0


def test_release_of_a_command_with_nothing_charged_does_nothing() -> None:
    command = {
        key: value
        for key, value in _command().items()
        if key not in _admission.ALLOWANCE_IDENTITY_FIELDS
    }

    assert _admission.meter(command).release() is False


def test_a_ledger_that_cannot_release_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        allowance_service,
        "release_unknown_cost_allowance",
        lambda **_kwargs: allowance_repo.ReleaseResult(
            allowance_repo.ReleaseDisposition.RETRYABLE
        ),
    )

    with pytest.raises(AdmissionError) as captured:
        _admission.meter(_command()).release()

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE
    assert captured.value.internal_detail == "release:retryable"


# ── The week ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("observed_at", "identity"),
    [
        # Sunday night in Zurich is still the week that began on Monday.
        ("2026-03-29T21:59:59+00:00", "2026-W13"),
        # Midnight in Zurich starts the next one, an hour before UTC's.
        ("2026-03-29T22:00:00+00:00", "2026-W14"),
        # The ISO year, not the calendar one.
        ("2027-01-01T12:00:00+00:00", "2026-W53"),
    ],
)
def test_week_identity_is_the_zurich_iso_week(observed_at: str, identity: str) -> None:
    assert allowance_service.week_identity(datetime.fromisoformat(observed_at)) == identity


def test_a_command_is_charged_in_the_week_it_was_asked() -> None:
    command = _command()
    assert command["allowance_week_identity"] == allowance_service.week_identity(NOW)
