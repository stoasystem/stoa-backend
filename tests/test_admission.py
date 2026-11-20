"""准入: whether a question may be sent, and what its answer is charged (#206).

The charge goes through `_admission`'s meter and usage evidence, on the real
ledger over an in-memory allowance table, with only the model faked (the
in-memory model-call adapter);
admission at the first submission goes through the message route, with the
student's eligibility seeded by `fakes.admission`.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from fakes.admission import seed_plan, seed_week_used
from fakes.ask_question import (
    CONV,
    NOW,
    STUDENT,
    AtomicAllowanceTable,
    CommandResult,
    Disposition,
    _client,
    _command,
    _command_key,
    _messages,
    _generation,
    _patch_allowance_table,
    _send,
)
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.model import FakeModel, Reply, Unsent, install
from stoa.db.repositories import allowance_repo
from stoa.routers import conversations
from stoa.services import ai_service, allowance_service, entitlement_service
from stoa.services import ask_answer, model_call
from stoa.services.model_call.adapter import ProviderError
from stoa.services.ask_question import _admission, _answering
from stoa.services.ask_question._admission import AdmissionError, UsageEvidence
from stoa.services.ask_question_errors import AskQuestionErrorCode


_CONTENT = {
    "answer": "The durable conversation answer",
    "steps": ["First durable step"],
    "hints": ["The same durable hint"],
    "similar_exercises": [],
    "knowledge_points": ["fractions"],
}


def _provider(
    *,
    actual_input_tokens: int = 70,
    actual_output_tokens: int = 25,
    invoke_error: Exception | None = None,
    count_error: Exception | None = None,
) -> FakeModel:
    """The model, counting 90 input tokens and answering once with the usage given."""
    reply: object = invoke_error or Reply(
        input=_CONTENT,
        stop_reason="end_turn",
        usage={"input_tokens": actual_input_tokens, "output_tokens": actual_output_tokens},
    )
    outcomes = [Unsent(count_error)] if count_error is not None else []
    return FakeModel(*outcomes, reply)


def _use(
    monkeypatch: pytest.MonkeyPatch,
    table: AtomicAllowanceTable,
    provider: FakeModel,
) -> None:
    _patch_allowance_table(monkeypatch, table)
    install(provider)


def _ask(admission: _admission.Admission) -> ai_service.AIProviderResult[dict[str, object]]:
    """Ask for an answer under `admission`, as `ask_answer` does."""
    result = model_call.call(
        system="Answer the question.",
        messages=[{"role": "user", "content": "private-message-canary"}],
        tool=ask_answer.answer_tool(star_map=False),
        max_tokens=2048,
        temperature=ask_answer.ANSWER_TEMPERATURE,
        deadline=time.monotonic() + 90,
        admission=admission,
        correlation_id="transport-correlation-that-must-not-own-the-effect",
    )
    return ask_answer.provider_result(result, effect_id=admission.effect_id)


def _answered(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: AtomicAllowanceTable,
    provider: FakeModel,
) -> tuple[dict[str, object], UsageEvidence]:
    """A command whose answer came back, and the evidence of what it cost."""
    _use(monkeypatch, table, provider)
    command = _command()
    result = _ask(_admission.meter(command).admission())
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
    provider = _provider(count_error=ProviderError("ServiceUnavailableException"))
    _use(monkeypatch, table, provider)

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        _ask(_admission.meter(_command()).admission())

    assert captured.value.category == "provider_token_count_unavailable"
    assert captured.value.retryable is True
    assert provider.counted == 1
    assert provider.requests == []
    assert not any(
        item.get("entity_type") == "allowance_effect"
        for item in table.items.values()
    )


def test_allowance_denial_never_invokes_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = _provider()
    _use(monkeypatch, table, provider)
    monkeypatch.setattr(
        allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: allowance_repo.ReservationResult(
            allowance_repo.ReservationDisposition.LIMIT_EXCEEDED
        ),
    )

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        _ask(_admission.meter(_command()).admission())

    assert captured.value.category == "allowance_exhausted"
    assert captured.value.retryable is True
    assert provider.counted == 1
    assert provider.requests == []


def test_an_unrecorded_call_is_never_made(monkeypatch: pytest.MonkeyPatch) -> None:
    table = AtomicAllowanceTable()
    provider = _provider()
    _use(monkeypatch, table, provider)

    with pytest.raises(ai_service.AIInvocationFailure) as lost:
        _ask(_admission.meter(_command()).admission(on_invocation=lambda: False))

    def broken() -> bool:
        raise RuntimeError("store-down")

    with pytest.raises(ai_service.AIInvocationFailure) as unrecorded:
        _ask(_admission.meter(_command()).admission(on_invocation=broken))

    assert (lost.value.category, lost.value.retryable) == ("lease_lost", True)
    assert (unrecorded.value.category, unrecorded.value.retryable) == (
        "invocation_not_recorded",
        True,
    )
    assert provider.requests == []


def test_a_command_whose_allowance_identity_does_not_hold_is_refused() -> None:
    command = {**_command(), "allowance_week_identity": "1999-W01"}

    with pytest.raises(AdmissionError) as captured:
        _admission.meter(command).admission()

    assert captured.value.code is AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE


def test_provider_timeout_after_reserve_remains_reserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    provider = _provider(invoke_error=ProviderError("ReadTimeoutError"))
    _use(monkeypatch, table, provider)

    with pytest.raises(ai_service.AIInvocationFailure) as captured:
        _ask(_admission.meter(_command()).admission())

    assert (captured.value.category, captured.value.retryable) == ("provider_error", True)
    assert _effect(table)["state"] == "reserved"
    assert table.counter()["finalized_input_tokens"] == 0
    assert len(provider.requests) == 1


# ── Refused before the model is called, through the Ask command ──────────────


def test_a_count_the_provider_refuses_fails_the_question_retryably(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#430/#436: a CountTokens body Bedrock refuses (here the stream-only tool
    field left in) is refused by the fake adapter too; the question is not
    sent, fails as `provider_token_count_unavailable`, and may be sent again."""
    monkeypatch.setattr(model_call, "_STREAM_ONLY_TOOL_FIELDS", frozenset())
    client = _client()

    refused = _send(client, "count-refused")

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "provider_token_count_unavailable"
    assert model.counted == 1
    assert model.calls == []
    generation = _generation(client, "count-refused")
    assert generation["status"] == "failed"
    assert generation["failureCategory"] == "provider_token_count_unavailable"
    assert generation["retryable"] is True


def test_a_spent_allowance_at_the_reservation_fails_the_question_retryably(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        allowance_service,
        "reserve_token_allowance",
        lambda **_kwargs: allowance_repo.ReservationResult(
            allowance_repo.ReservationDisposition.LIMIT_EXCEEDED
        ),
    )
    client = _client()

    refused = _send(client, "reserve-refused")

    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"]["code"] == "allowance_exhausted"
    assert model.calls == []
    generation = _generation(client, "reserve-refused")
    assert generation["failureCategory"] == "allowance_exhausted"
    assert generation["retryable"] is True


# ── After it answered ─────────────────────────────────────────────────────────


def test_store_ambiguity_keeps_observed_reservation_without_finalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())

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
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())

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
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())
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
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())
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
    provider = _provider()
    command, evidence = _answered(monkeypatch, table=table, provider=provider)
    _admission.meter(command).observe(evidence)
    response = _response(
        "1. First durable step\n\nThe durable conversation answer"
        "\n\n**Hinweis:** The same durable hint"
    )

    regular = _answering._result_response(_completed(command, response, evidence))
    sse = _answering._result_response(_completed(command, response, evidence))

    assert regular == sse == response
    assert len(provider.requests) == 1
    counter = table.counter()
    assert counter["finalized_input_tokens"] == 70
    assert counter["finalized_output_tokens"] == 25
    assert counter["provider_cost_input_tokens"] == 70
    assert counter["provider_cost_output_tokens"] == 25
    assert len(table.evidence()) == 1


def test_a_cached_reply_is_charged_every_input_token_and_says_how_many_were_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#442: the week is charged the tokens as counted; the cache counts ride along."""
    table = AtomicAllowanceTable()
    provider = FakeModel(
        Reply(
            input=_CONTENT,
            stop_reason="end_turn",
            usage={
                "input_tokens": 10,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 60,
                "output_tokens": 25,
            },
        )
    )
    command, evidence = _answered(monkeypatch, table=table, provider=provider)

    assert (
        evidence.input_tokens,
        evidence.cache_write_input_tokens,
        evidence.cache_read_input_tokens,
    ) == (70, 0, 60)
    stored = evidence.to_json()
    assert stored["provider_input_tokens"] == 70
    assert stored["provider_cache_read_input_tokens"] == 60
    assert "provider_cache_write_input_tokens" not in stored
    assert UsageEvidence.from_json(json.loads(json.dumps(stored))) == evidence
    # A cache count that is no count, or more than was read, is not evidence.
    for malformed in (Decimal("1.5"), True, -1, 71):
        assert UsageEvidence.from_json(
            {**stored, "provider_cache_read_input_tokens": malformed}
        ) is None

    _admission.meter(command).observe(evidence)
    response = _response(
        "1. First durable step\n\nThe durable conversation answer"
        "\n\n**Hinweis:** The same durable hint"
    )
    _answering._result_response(_completed(command, response, evidence))

    counter = table.counter()
    assert counter["finalized_input_tokens"] == 70
    assert counter["provider_cost_input_tokens"] == 70
    [item] = table.evidence()
    assert item["input_tokens"] == 70
    assert item["cache_read_input_tokens"] == 60
    assert "cache_write_input_tokens" not in item
    effect = _effect(table)
    [read] = allowance_repo.list_provider_usage_evidence(
        beneficiary_id=str(effect["beneficiary_id"]),
        week_identity=str(effect["week_identity"]),
        table=table,
    )
    assert (read.input_tokens, read.cache_write_input_tokens, read.cache_read_input_tokens) == (
        70,
        0,
        60,
    )


def test_finalize_timeout_repairs_from_the_same_durable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = AtomicAllowanceTable()
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())
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
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())
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
    command, evidence = _answered(monkeypatch, table=table, provider=_provider())
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
    provider = _provider(invoke_error=ProviderError("ReadTimeoutError"))
    _use(monkeypatch, table, provider)
    real_release = allowance_service.release_unknown_cost_allowance
    monkeypatch.setattr(
        allowance_service,
        "release_unknown_cost_allowance",
        lambda **kwargs: real_release(**kwargs, table=table),
    )
    command = _command()
    with pytest.raises(ai_service.AIInvocationFailure):
        _ask(_admission.meter(command).admission())

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


# ── Admission at the first submission (#241) ─────────────────────────────────


def _usage_rows(table: Any) -> list[dict[str, Any]]:
    """Today's message counter and its per-command marks."""
    return [row for (pk, _sk), row in table.rows.items() if pk.startswith("USAGE#")]


def test_a_question_reads_eligibility_once_and_its_replay_none(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    eligibility = seed_plan(monkeypatch)
    client = _client()

    first = _send(client, "admitted-once")
    assert first.status_code == 200, first.text
    assert eligibility.reads == [STUDENT]

    replay = _send(client, "admitted-once")
    assert replay.status_code == 200, replay.text
    assert eligibility.reads == [STUDENT]
    assert len(model.calls) == 1


def test_a_week_with_nothing_left_refuses_before_anything_is_stored(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance)
    seed_week_used(allowance, STUDENT, at=datetime.now(UTC))

    refused = _send(_client(), "week-spent")

    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"]["code"] == "allowance_exhausted"
    assert model.calls == [] and model.counted == 0
    assert _messages(table, "student") == []
    assert tuple(_command_key(CONV, "week-spent").values()) not in table.rows
    # Today's message was not counted against the daily limit.
    assert _usage_rows(table) == []


def test_a_week_with_room_left_admits_the_question(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance)
    budget = allowance_service.plan_allowance_budget("free_trial", allowance_version=1)
    seed_week_used(
        allowance, STUDENT, at=datetime.now(UTC), input_tokens=budget.input_tokens - 1_000
    )

    answered = _send(_client(), "week-almost-spent")

    assert answered.status_code == 200, answered.text
    assert len(model.calls) == 1


# ── A plan that changes inside a week (#512) ─────────────────────────────────


def _resolved_as(monkeypatch: pytest.MonkeyPatch, plan: str):
    """The student's eligibility as `entitlement_service` resolves it: no allowance version."""
    eligibility = seed_plan(monkeypatch, plan=plan)
    del eligibility.entitlement["allowanceVersion"]
    return eligibility


def _week_counter(allowance: AtomicAllowanceTable) -> dict[str, Any]:
    counter = allowance_repo.get_allowance_counter(
        beneficiary_id=STUDENT,
        week=allowance_service.zurich_week(datetime.now(UTC)),
        table=allowance,
    )
    assert counter is not None
    return counter


def test_a_plan_that_starts_mid_week_is_asked_under_at_once(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance)
    eligibility = _resolved_as(monkeypatch, "free_trial")
    client = _client()
    assert _send(client, "before-the-grant").status_code == 200
    used_before = _week_counter(allowance)["finalized_input_tokens"]

    eligibility.entitlement["effectivePlan"] = "teacher_supported"
    after = _send(client, "after-the-grant")

    assert after.status_code == 200, after.text
    assert len(model.calls) == 2
    counter = _week_counter(allowance)
    paid = allowance_service.plan_allowance_budget("teacher_supported", allowance_version=1)
    assert (counter["plan_id"], counter["budget_input_tokens"]) == (
        "teacher_supported",
        paid.input_tokens,
    )
    # The tokens asked before the change still count, now against the new budget.
    assert counter["finalized_input_tokens"] > used_before > 0


def test_a_plan_that_ends_mid_week_is_asked_under_the_free_budget(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance)
    eligibility = _resolved_as(monkeypatch, "teacher_supported")
    client = _client()
    assert _send(client, "while-granted").status_code == 200

    eligibility.entitlement["effectivePlan"] = "free_trial"
    after = _send(client, "after-the-grant-ended")

    assert after.status_code == 200, after.text
    assert len(model.calls) == 2
    assert _week_counter(allowance)["plan_id"] == "free_trial"


def test_a_plan_that_ends_after_more_than_the_free_week_was_used_leaves_none(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowance = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance)
    eligibility = _resolved_as(monkeypatch, "teacher_supported")
    free = allowance_service.plan_allowance_budget("free_trial", allowance_version=1)
    seed_week_used(
        allowance,
        STUDENT,
        at=datetime.now(UTC),
        plan="teacher_supported",
        input_tokens=free.input_tokens,
    )

    eligibility.entitlement["effectivePlan"] = "free_trial"
    refused = _send(_client(), "free-week-already-spent")

    assert refused.status_code == 429, refused.text
    assert refused.json()["detail"]["code"] == "allowance_exhausted"
    assert model.calls == []


def test_the_admitted_limit_is_the_one_the_claim_enforces(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(monkeypatch, daily_limit=1)
    client = _client()

    assert _send(client, "first-today").status_code == 200
    second = _send(client, "second-today")

    assert second.status_code == 429, second.text
    assert second.json()["detail"]["code"] == "message_daily_limit"


def test_an_unreadable_eligibility_is_unavailable(
    table, model, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        entitlement_service, "resolve_student_entitlement", lambda *_a, **_k: None
    )

    refused = _send(_client(), "eligibility-unreadable")

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "allowance_unavailable"
    assert model.calls == []
