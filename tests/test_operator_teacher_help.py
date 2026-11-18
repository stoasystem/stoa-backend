"""An agent reads how many teacher-help requests a student has left this week."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from test_operator_calls import _audit_rows, _business_rows_added, _call, _rows, _seed_account

from stoa.db.repositories import weekly_counter
from stoa.operator_calls import catalog
from stoa.services import teacher_support_allowance_service as allowance
from stoa.services import usage_period


def _in(days: int) -> str:
    return (usage_period.zurich_today(None) + timedelta(days=days)).isoformat()


def _spend(table, student_id: str, cases: int, *, mode: str = allowance.TEXT) -> None:
    """Put this week's counter of `mode` on the table as admission writes it, at `cases`."""
    source = allowance._resolve_scope(student_id, table=table)
    assert source is not None
    scope = allowance._for_mode(source, mode)
    assert scope is not None
    week = weekly_counter.zurich_week(datetime.now(UTC))
    operation = weekly_counter.write(
        weekly_counter.CASES,
        scope.support_scope_id,
        week,
        None,
        counts={"admitted_cases": cases},
        fields={
            "support_scope": scope.support_scope.value,
            "plan_id": str(scope.plan_id),
            "plan_version": scope.plan_version,
            "allowance_version": scope.allowance_version,
            "grant_id": scope.grant_id,
            "limit": scope.limit,
        },
        at=datetime.now(UTC),
    )
    table.seed(operation["Put"]["Item"])


@pytest.fixture
def student(fake_table):
    _seed_account(
        fake_table, "student-1", "student", "S26-0001", usage_period_ends_at=_in(30), version=1
    )
    return fake_table


def test_it_is_a_read_only_operation_of_the_catalog() -> None:
    spec = catalog.OPERATIONS_BY_NAME["get_teacher_help_allowance"]
    assert spec.effect is catalog.Effect.READ
    assert spec.description.startswith("Read only.")
    assert spec.input_schema()["required"] == ["accountNumber"]


def test_a_student_who_used_none_has_the_whole_week(student) -> None:
    before = _rows(student)
    answer = _call("get_teacher_help_allowance", {"accountNumber": "s26-0001"})
    result = answer["result"]

    assert result["accountNumber"] == "S26-0001"
    assert result["weeklyCases"] == allowance.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES
    assert result["usedCases"] == 0
    assert result["remainingCases"] == allowance.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES
    assert result["weekIdentity"] == weekly_counter.zurich_week(datetime.now(UTC)).identity
    assert result["resetsAt"]
    assert result["assignedWeeklyCases"] == {
        "weeklyCases": allowance.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES,
        "weeklyClassroomCases": allowance.ASSIGNED_WEEKLY_CLASSROOM_CASES,
        "source": "default",
    }
    assert result["classroom"] == {
        "weeklyCases": allowance.ASSIGNED_WEEKLY_CLASSROOM_CASES,
        "usedCases": 0,
        "remainingCases": allowance.ASSIGNED_WEEKLY_CLASSROOM_CASES,
        "canRequestNow": True,
        "blockedReasons": [],
    }
    assert result["usagePeriod"]["state"] == "active"
    assert result["canRequestNow"] is True
    assert result["blockedReasons"] == []
    # It reads: nothing but the audit row is written.
    assert not _business_rows_added(student, before)
    row = _audit_rows(student)[-1]
    assert row["action"] == "get_teacher_help_allowance"


def test_it_counts_what_this_week_spent(student) -> None:
    _spend(student, "student-1", 3)
    result = _call("get_teacher_help_allowance", {"accountNumber": "S26-0001"})["result"]
    assert result["usedCases"] == 3
    assert result["remainingCases"] == allowance.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES - 3
    assert result["canRequestNow"] is True


def test_a_spent_week_says_why_a_request_would_be_refused(student) -> None:
    _spend(student, "student-1", allowance.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES)
    result = _call("get_teacher_help_allowance", {"accountNumber": "S26-0001"})["result"]
    assert result["remainingCases"] == 0
    assert result["canRequestNow"] is False
    assert result["blockedReasons"] == ["teacher_support_allowance_exhausted"]


def test_spent_classrooms_are_counted_apart_from_text_answers(student) -> None:
    _spend(student, "student-1", allowance.ASSIGNED_WEEKLY_CLASSROOM_CASES, mode=allowance.CLASSROOM)
    result = _call("get_teacher_help_allowance", {"accountNumber": "S26-0001"})["result"]
    assert result["usedCases"] == 0
    assert result["canRequestNow"] is True
    assert result["classroom"]["usedCases"] == allowance.ASSIGNED_WEEKLY_CLASSROOM_CASES
    assert result["classroom"]["remainingCases"] == 0
    assert result["classroom"]["canRequestNow"] is False
    assert result["classroom"]["blockedReasons"] == ["teacher_support_allowance_exhausted"]


def test_an_ended_usage_period_is_named_beside_the_count(fake_table) -> None:
    _seed_account(
        fake_table, "student-1", "student", "S26-0001", usage_period_ends_at=_in(-3), version=1
    )
    result = _call("get_teacher_help_allowance", {"accountNumber": "S26-0001"})["result"]
    assert result["usagePeriod"]["state"] == "expired"
    assert result["canRequestNow"] is False
    assert "usage_period_ended" in result["blockedReasons"]


def test_only_a_student_has_teacher_help_to_read(fake_table) -> None:
    _seed_account(fake_table, "parent-1", "parent", "P26-0001")
    answer = _call("get_teacher_help_allowance", {"accountNumber": "P26-0001"})
    assert answer["ok"] is False
    assert answer["error"]["code"] == "account_not_a_student"


def test_an_unknown_number_is_not_found(fake_table) -> None:
    answer = _call("get_teacher_help_allowance", {"accountNumber": "S26-9999"})
    assert answer["ok"] is False
    assert answer["error"]["code"] == "account_not_found"
