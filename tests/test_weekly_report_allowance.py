"""The weekly report is charged to the student's weekly allowance (#557).

As an Ask answer is: the report's model call goes through an admission hook
that reserves it in the week the report is generated in, and what the reply
cost is settled from its usage evidence. A week that cannot hold the call has
no report: no model call, no deterministic report, and a status of its own
that is neither a failure nor anything recovery retries.

The ledger is the real one over an in-memory allowance table; only the model
(the in-memory model-call adapter), the student's eligibility and storing the
report are stood in for.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from fakes.admission import seed_plan, seed_week_used
from fakes.ask_question import _patch_allowance_table
from stoa.jobs import weekly_reports
from stoa.routers import parents
from stoa.services import (
    allowance_service,
    entitlement_service,
    model_call,
    report_recovery_job_service,
    report_recovery_service,
    report_service,
)
from stoa.services.model_call.adapter import ProviderError
from stoa.services.model_call.fake import INPUT_TOKENS, OUTPUT_TOKENS, FakeAdapter, Prose
from test_token_allowances import AtomicAllowanceTable

STUDENT = "student-1"
WEEK = "2026-06-01"

MODEL_REPORT = {
    "summary": "Student made steady progress.",
    "strengths": ["Completed practice."],
    "weakTopics": [],
    "recommendations": ["Do one review session."],
    "teacherNote": None,
}

# Taken before any test points the allowance at a table of its own.
_RELEASE = allowance_service.release_unknown_cost_allowance
_FENCE = report_service.account_deletion_repo.require_active_account_fence


def _payload(parent_id: str = "parent-1", student_id: str = STUDENT) -> dict[str, Any]:
    return {
        "locale": "en",
        "parent": {"id": parent_id, "email": f"{parent_id}@example.com", "name": parent_id},
        "student": {"id": student_id, "name": "Student", "grade": 5},
        "week": {"start": WEEK, "end": "2026-06-07"},
        "metrics": {"questionsAsked": 2, "practiceLessonsCompleted": 1},
        "weakTopics": [],
        "activities": [],
    }


class Stored:
    """`store_and_send_weekly_report`, recording what it was handed."""

    def __init__(self, *, fail: bool = False) -> None:
        self.reports: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.fail = fail

    def __call__(self, payload: dict[str, Any], content: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("artifact store unavailable")
        self.reports.append((payload, content))
        parent_id = payload["parent"]["id"]
        return {
            "report_id": f"weekly-report-{parent_id}-{STUDENT}-{WEEK}",
            "status": "email_sent",
            "email_status": "sent",
        }


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> AtomicAllowanceTable:
    """The student's allowance, on the real ledger, on the free trial's budget."""
    allowance_table = AtomicAllowanceTable()
    _patch_allowance_table(monkeypatch, allowance_table)
    monkeypatch.setattr(
        allowance_service,
        "release_unknown_cost_allowance",
        lambda **kwargs: _RELEASE(**kwargs, table=allowance_table),
    )
    # The student's account fence is the allowance table's.
    monkeypatch.setattr(
        report_service.account_deletion_repo,
        "require_active_account_fence",
        lambda owner, **kwargs: _FENCE(owner, **{"table": allowance_table, **kwargs}),
    )
    seed_plan(monkeypatch, plan="free_trial")
    return allowance_table


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> Stored:
    recorder = Stored()
    monkeypatch.setattr(report_service, "store_and_send_weekly_report", recorder)
    return recorder


def _model(*outcomes: Any) -> FakeAdapter:
    model = FakeAdapter(*outcomes)
    model_call.install(model)
    return model


def _counts(table: AtomicAllowanceTable) -> dict[str, int]:
    counter = table.counter()
    return {
        field: int(counter.get(field, 0))  # type: ignore[call-overload]
        for field in (
            "reserved_input_tokens",
            "reserved_output_tokens",
            "finalized_input_tokens",
            "finalized_output_tokens",
        )
    }


def _charged(input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {
        "reserved_input_tokens": 0,
        "reserved_output_tokens": 0,
        "finalized_input_tokens": input_tokens,
        "finalized_output_tokens": output_tokens,
    }


def _spend_the_week(table: AtomicAllowanceTable) -> None:
    seed_week_used(table, STUDENT, at=datetime.now(UTC))


# ── The report, charged ───────────────────────────────────────────────────────


def test_a_report_is_charged_to_the_students_week(
    table: AtomicAllowanceTable, stored: Stored, caplog: pytest.LogCaptureFixture
) -> None:
    model = _model(MODEL_REPORT)

    with caplog.at_level(logging.INFO, logger=report_service.logger.name):
        report = report_service.generate_and_send_weekly_report(_payload())

    assert report["status"] == "email_sent"
    assert stored.reports == [(_payload(), MODEL_REPORT)]
    # Counted, admitted, then sent once.
    assert model.counted == 1
    assert len(model.calls) == 1
    # What the reply cost, by its usage evidence: not the reservation's ceiling.
    assert _counts(table) == _charged(INPUT_TOKENS, OUTPUT_TOKENS)
    [evidence] = table.evidence()
    assert int(evidence["input_tokens"]) == INPUT_TOKENS  # type: ignore[call-overload]
    assert "cost_class=user_allowance" in caplog.text


def test_the_report_is_charged_in_the_week_it_is_generated_in(
    table: AtomicAllowanceTable, stored: Stored
) -> None:
    """Monday 06:00 in Zurich, for the week before: the new week pays (#557)."""
    _model(MODEL_REPORT)
    generated_at = datetime(2026, 6, 8, 4, 0, tzinfo=UTC)

    report_service.generate_and_send_weekly_report(_payload(), now=generated_at)

    assert table.counter()["week_identity"] == "2026-W24"


def test_a_week_without_room_has_no_report_and_no_model_call(
    table: AtomicAllowanceTable, stored: Stored
) -> None:
    _spend_the_week(table)
    before = _counts(table)
    model = _model(MODEL_REPORT)

    with pytest.raises(report_service.AllowanceExhausted):
        report_service.generate_and_send_weekly_report(_payload())

    # Counted, refused: never sent, and no deterministic report either.
    assert model.counted == 1
    assert model.calls == []
    assert stored.reports == []
    assert _counts(table) == before


def test_each_parents_report_is_charged(table: AtomicAllowanceTable, stored: Stored) -> None:
    _model(MODEL_REPORT, MODEL_REPORT)

    report_service.generate_and_send_weekly_report(_payload("parent-1"))
    report_service.generate_and_send_weekly_report(_payload("parent-2"))

    assert len(stored.reports) == 2
    assert _counts(table) == _charged(2 * INPUT_TOKENS, 2 * OUTPUT_TOKENS)
    assert len(table.evidence()) == 2


@pytest.mark.parametrize(
    "outcome",
    [
        Prose("Here is the report."),
        {**MODEL_REPORT, "summary": "This was generated by Bedrock."},
    ],
    ids=["paid-unusable", "parser-refuses"],
)
def test_a_paid_reply_that_cannot_be_used_still_sends_the_deterministic_report_and_is_charged(
    table: AtomicAllowanceTable, stored: Stored, outcome: Any
) -> None:
    _model(outcome)

    report_service.generate_and_send_weekly_report(_payload())

    [(_payload_sent, content)] = stored.reports
    assert content == report_service.build_deterministic_report_fallback(_payload())
    assert _counts(table) == _charged(INPUT_TOKENS, OUTPUT_TOKENS)


def test_a_call_admitted_but_never_paid_gives_the_reservation_back(
    table: AtomicAllowanceTable, stored: Stored
) -> None:
    _model(ProviderError("ServiceUnavailableException", http_status=503))

    report_service.generate_and_send_weekly_report(_payload())

    [(_payload_sent, content)] = stored.reports
    assert content == report_service.build_deterministic_report_fallback(_payload())
    assert _counts(table) == _charged(0, 0)


def test_a_report_not_stored_gives_the_charge_back(
    table: AtomicAllowanceTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report_service, "store_and_send_weekly_report", Stored(fail=True))
    _model(MODEL_REPORT)

    with pytest.raises(RuntimeError, match="artifact store unavailable"):
        report_service.generate_and_send_weekly_report(_payload())

    assert _counts(table) == _charged(0, 0)
    # The provider was paid all the same, and that is kept.
    assert int(table.counter()["provider_cost_input_tokens"]) == INPUT_TOKENS  # type: ignore[call-overload]


def test_an_allowance_that_cannot_be_read_fails_the_report(
    table: AtomicAllowanceTable, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("table unavailable")

    monkeypatch.setattr(entitlement_service, "resolve_student_entitlement", unreadable)
    model = _model(MODEL_REPORT)

    with pytest.raises(report_service.AllowanceUnavailable):
        report_service.generate_and_send_weekly_report(_payload())

    assert model.calls == []
    assert stored.reports == []


# ── The weekly job and recovery ───────────────────────────────────────────────


@pytest.fixture
def job(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    """The weekly job over one student with two parents; the report status updates it makes."""
    updates: list[tuple[str, str, dict[str, Any]]] = []
    monkeypatch.setattr(
        weekly_reports,
        "eligible_parent_student_pairs",
        lambda: [
            {"parent_id": "parent-1", "student_id": STUDENT},
            {"parent_id": "parent-2", "student_id": STUDENT},
        ],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo, "get_report_for_child_by_week", lambda *_args: None
    )
    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", lambda _claim: True)
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    monkeypatch.setattr(
        weekly_reports.report_service,
        "build_weekly_learning_payload",
        lambda parent_id, student_id, _week: _payload(parent_id, student_id),
    )
    return updates


def test_the_job_charges_both_parents_reports(
    table: AtomicAllowanceTable, stored: Stored, job: list[Any]
) -> None:
    _model(MODEL_REPORT, MODEL_REPORT)

    counts = weekly_reports.run_weekly_report_job({"week_start": WEEK})

    assert counts["generated"] == 2
    assert counts["skipped_allowance"] == 0
    assert _counts(table) == _charged(2 * INPUT_TOKENS, 2 * OUTPUT_TOKENS)


def test_the_job_skips_a_week_without_room_as_its_own_count_not_a_failure(
    table: AtomicAllowanceTable, stored: Stored, job: list[tuple[str, str, dict[str, Any]]]
) -> None:
    _spend_the_week(table)
    model = _model(MODEL_REPORT, MODEL_REPORT)

    counts = weekly_reports.run_weekly_report_job({"week_start": WEEK})

    assert counts["attempted"] == 2
    assert counts["skipped_allowance"] == 2
    assert counts["generated"] == 0
    assert counts["failed"] == 0
    assert model.calls == []
    assert stored.reports == []
    assert [(report_id, status) for report_id, status, _fields in job] == [
        (f"weekly-report-parent-1-{STUDENT}-{WEEK}", "skipped_allowance"),
        (f"weekly-report-parent-2-{STUDENT}-{WEEK}", "skipped_allowance"),
    ]
    assert all("allowance_skipped_at" in fields for _id, _status, fields in job)


def test_the_job_leaves_a_skipped_week_alone_when_run_again(
    monkeypatch: pytest.MonkeyPatch, job: list[Any]
) -> None:
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda *_args: {"status": "skipped_allowance"},
    )

    def never(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("a skipped week is not generated again")

    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", never)

    counts = weekly_reports.run_weekly_report_job({"week_start": WEEK})

    assert counts["skipped_existing"] == 2
    assert counts["failed"] == 0


def test_a_retried_generation_goes_through_the_same_admission(
    table: AtomicAllowanceTable, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spend_the_week(table)
    model = _model(MODEL_REPORT)
    updates: list[tuple[str, str, dict[str, Any]]] = []
    audits: list[dict[str, Any]] = []
    repo = report_recovery_service.report_repo
    monkeypatch.setattr(repo, "try_start_generation_retry", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        repo,
        "update_report_status",
        lambda report_id, status, **fields: updates.append((report_id, status, fields)),
    )
    monkeypatch.setattr(
        repo, "put_report_audit_event", lambda _report_id, event: audits.append(event)
    )
    monkeypatch.setattr(
        report_service,
        "build_weekly_learning_payload",
        lambda parent_id, student_id, _week: _payload(parent_id, student_id),
    )
    report_id = f"weekly-report-parent-1-{STUDENT}-{WEEK}"

    result = report_recovery_service.retry_report_generation(
        {"report_id": report_id, "status": "generation_failed", "student_id": STUDENT},
        parent_id="parent-1",
        student_id=STUDENT,
        week_start=WEEK,
        operator="admin-1",
    )

    assert model.calls == []
    assert stored.reports == []
    assert result.status == "skipped_allowance"
    assert result.operation_result == "skipped"
    [(updated_id, status, fields)] = updates
    assert (updated_id, status) == (report_id, "skipped_allowance")
    assert fields["last_operation_result"] == "skipped"
    assert [event["result"] for event in audits] == ["skipped"]


def test_a_retried_generation_with_room_is_charged(
    table: AtomicAllowanceTable, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    _model(MODEL_REPORT)
    repo = report_recovery_service.report_repo
    monkeypatch.setattr(repo, "try_start_generation_retry", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(repo, "update_report_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(repo, "put_report_audit_event", lambda *_args: None)
    monkeypatch.setattr(
        report_service,
        "build_weekly_learning_payload",
        lambda parent_id, student_id, _week: _payload(parent_id, student_id),
    )

    result = report_recovery_service.retry_report_generation(
        {
            "report_id": f"weekly-report-parent-1-{STUDENT}-{WEEK}",
            "status": "generation_failed",
            "student_id": STUDENT,
        },
        parent_id="parent-1",
        student_id=STUDENT,
        week_start=WEEK,
        operator="admin-1",
    )

    assert result.status == "email_sent"
    assert _counts(table) == _charged(INPUT_TOKENS, OUTPUT_TOKENS)


def test_recovery_does_not_take_a_skipped_week_for_a_failed_one() -> None:
    preview = report_recovery_job_service._target_preview(
        {"report_id": "r-1", "status": "skipped_allowance"},
        job_type=report_recovery_job_service.GENERATION_RETRY_JOB_TYPE,
    )

    assert preview["eligibility"] == "refused"


# ── What the parent sees ──────────────────────────────────────────────────────


def test_the_parent_sees_a_skipped_week_as_a_week_without_a_report() -> None:
    state = parents._report_state_from_item(
        {"report_id": "r-1", "student_id": STUDENT, "status": "skipped_allowance"}
    )

    assert state.status == "missing"
    assert state.report is None


def test_the_latest_report_passes_over_a_skipped_week(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "report_id": "r-new",
            "student_id": STUDENT,
            "week_start": "2026-06-08",
            "status": "skipped_allowance",
        },
        {"report_id": "r-old", "student_id": STUDENT, "week_start": WEEK, "status": "email_sent"},
    ]
    monkeypatch.setattr(
        parents.report_repo, "list_reports_for_parent", lambda *_args, **_kwargs: {"Items": rows}
    )

    latest = parents._latest_report_for_child("parent-1", STUDENT)
    history = parents._report_history_events("parent-1", STUDENT)

    assert latest is not None and latest["report_id"] == "r-old"
    assert [event.id for event in history] == ["r-old"]
