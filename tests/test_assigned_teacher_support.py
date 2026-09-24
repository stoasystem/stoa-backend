"""Teacher support a student has by being a student here, with no parent in it.

Until this existed, the allowance came from one place: a parent's purchase.
Payments are frozen and STOA assigns accounts rather than selling them, so no
grant could be created and asking for a teacher was refused for every student on
the platform - the refusal told them to go and buy it. Measured in production on
2026-09-24: `POST /teacher-help/request` answered 403 for the only student
account there was.

The figure is seven cases a Zurich week, and an administrator can raise it.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from stoa.services import teacher_support_allowance_service as service

from test_teacher_support_allowances import AtomicSupportTable, _case_committer


NOW = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
STUDENT = "student-assigned-1"


def _profile(**overrides: object) -> dict[str, object]:
    return {
        "user_id": STUDENT,
        "role": "student",
        "account_status": "active",
        # The table returns every number as Decimal, and the fixtures that store
        # `int` are how four defects stayed invisible in this codebase.
        "version": Decimal("21"),
        **overrides,
    }


@pytest.fixture
def student(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    row = _profile()
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(row)
    )
    monkeypatch.setattr(
        service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    return row


def _admit(table: AtomicSupportTable, case_id: str, *, student_id: str = STUDENT):
    return service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="question",
        beneficiary_id=student_id,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id=case_id, beneficiary_id=student_id
        ),
        table=table,
    )


def _raise_to(table: AtomicSupportTable, cases: int, *, version: int = 1) -> None:
    table.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{STUDENT}",
        "SK": service.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "teacher_support_assigned_allowance",
        "schema_version": service.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
        "weekly_cases": Decimal(cases),
        "state_version": Decimal(version),
    }


def test_a_student_with_no_parent_gets_seven_cases_a_week(student) -> None:
    table = AtomicSupportTable()

    admitted = [_admit(table, f"q-{index}") for index in range(7)]

    assert [result.disposition.value for result in admitted] == ["admitted"] * 7
    assert admitted[-1].admission.post_admission_count == 7
    assert admitted[-1].admission.limit == 7


def test_the_eighth_case_in_the_same_week_is_refused(student) -> None:
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")

    eighth = _admit(table, "q-8")

    assert eighth.disposition.value == "limit_exceeded"


def test_an_administrator_can_raise_the_figure(student) -> None:
    table = AtomicSupportTable()
    _raise_to(table, 9)

    admitted = [_admit(table, f"q-{index}") for index in range(9)]

    assert [result.disposition.value for result in admitted] == ["admitted"] * 9
    assert admitted[-1].admission.limit == 9
    assert _admit(table, "q-10").disposition.value == "limit_exceeded"


def test_raising_the_figure_mid_week_keeps_what_the_week_already_spent(student) -> None:
    """The counter carries the old figure, and it must not read as damage.

    The stored limit used to be compared for equality, so the moment an
    administrator raised it the week's own counter became "malformed" - a
    dependency failure, retried until the caller gave up, which reaches the
    student as a 503 for something somebody did to help them.
    """
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")
    assert _admit(table, "q-8").disposition.value == "limit_exceeded"

    _raise_to(table, 10)

    eighth = _admit(table, "q-8b")
    assert eighth.disposition.value == "admitted"
    # Seven were already spent this week; raising the cap does not refund them.
    assert eighth.admission.post_admission_count == 8
    assert eighth.admission.limit == 10


def test_lowering_the_figure_below_what_was_spent_refuses_rather_than_fails(
    student,
) -> None:
    """Negative control for the same widening: it must refuse, not report damage."""
    table = AtomicSupportTable()
    for index in range(7):
        _admit(table, f"q-{index}")

    _raise_to(table, 3, version=2)

    assert _admit(table, "q-after").disposition.value == "limit_exceeded"


def test_a_paid_grant_still_wins_where_one_exists(monkeypatch) -> None:
    """The assigned figure is a floor, not a replacement.

    A family that bought the wider budget keeps it, and the scope spent against
    is still the grant's - otherwise the counters would part company.
    """
    table = AtomicSupportTable()
    paid = object()
    monkeypatch.setattr(service, "_resolve_paid_scope", lambda *_a, **_k: paid)

    assert service._resolve_scope(STUDENT, table=table) is paid


def test_an_account_that_is_not_an_active_student_gets_nothing(
    monkeypatch, student
) -> None:
    for field, value in (("role", "parent"), ("account_status", "suspended")):
        row = _profile(**{field: value})
        monkeypatch.setattr(
            service.user_repo, "get_user", lambda _uid, r=row, **_kw: deepcopy(r)
        )
        assert service._resolve_assigned_scope(STUDENT, table=AtomicSupportTable()) is None


def test_the_fence_is_the_student_and_nothing_else(student) -> None:
    """What an assigned admission conditions on, read off the transaction.

    The fake table does not evaluate a ConditionCheck, so the conditions are
    read here directly. There must be no parent, no grant row and no
    relationship in them - and no account fence either, because the case
    repository contributes the student's and one transaction cannot target the
    same row twice.
    """
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-fence",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-fence", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    # What this service contributed, not what the case repository added around
    # it: the student's account fence is the repository's, and asserting on the
    # whole transaction would be asserting on somebody else's operation.
    checks = [op["ConditionCheck"] for op in calls[0] if "ConditionCheck" in op]
    keys = {(str(check["Key"]["PK"]), str(check["Key"]["SK"])) for check in checks}

    assert keys == {
        (f"USER#{STUDENT}", "PROFILE"),
        (f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK),
    }
    # And the fence is not among them, or the transaction would target one row
    # twice and be refused outright.
    assert (f"USER#{STUDENT}", "ACCOUNT_FENCE") not in keys
    profile_check = next(
        check for check in checks if check["Key"]["SK"] == "PROFILE"
    )
    assert ":parent_id" not in profile_check["ExpressionAttributeValues"]
    assert profile_check["ExpressionAttributeValues"][":version"] == 21


def test_a_raised_figure_is_fenced_on_the_row_it_was_read_from(student) -> None:
    """Negative control: the figure spent against has to still be in force."""
    table = AtomicSupportTable()
    _raise_to(table, 9, version=4)
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-raised",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-raised", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    check = next(
        op["ConditionCheck"]
        for op in calls[0]
        if "ConditionCheck" in op
        and op["ConditionCheck"]["Key"]["SK"] == service.ASSIGNED_ALLOWANCE_SK
    )
    assert check["ExpressionAttributeValues"] == {":version": 4, ":cases": 9}


def test_with_no_raised_row_the_absence_itself_is_fenced(student) -> None:
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-default",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-default", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    check = next(
        op["ConditionCheck"]
        for op in calls[0]
        if "ConditionCheck" in op
        and op["ConditionCheck"]["Key"]["SK"] == service.ASSIGNED_ALLOWANCE_SK
    )
    assert check["ConditionExpression"] == "attribute_not_exists(PK)"


def test_a_stored_figure_out_of_range_falls_back_to_seven(student) -> None:
    """A bad write must not become an open budget or a locked-out student."""
    table = AtomicSupportTable()
    for stored in (Decimal("-1"), Decimal(service.ASSIGNED_WEEKLY_CASES_MAXIMUM + 1)):
        assert service.assigned_weekly_cases({"weekly_cases": stored}) == 7
    assert service.assigned_weekly_cases({"weekly_cases": Decimal("0")}) == 0
    assert service.assigned_weekly_cases(None) == 7
    del table


def test_a_malformed_raised_row_is_a_dependency_failure_not_a_free_pass(
    student,
) -> None:
    """Negative control: an unreadable row must not silently mean seven."""
    table = AtomicSupportTable()
    table.items[(f"USER#{STUDENT}", service.ASSIGNED_ALLOWANCE_SK)] = {
        "PK": f"USER#{STUDENT}",
        "SK": service.ASSIGNED_ALLOWANCE_SK,
        "entity_type": "something_else",
    }

    assert _admit(table, "q-malformed").disposition.value == "retryable"


def test_two_students_do_not_share_a_week(student, monkeypatch) -> None:
    """Per beneficiary, so one student's week cannot spend another's."""
    table = AtomicSupportTable()
    first = service._resolve_assigned_scope(STUDENT, table=table)
    other_row = _profile(user_id="student-assigned-2")
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda _uid, **_kw: deepcopy(other_row)
    )
    second = service._resolve_assigned_scope("student-assigned-2", table=table)

    assert first.support_scope_id != second.support_scope_id


def test_the_counter_write_is_a_compare_and_set(student) -> None:
    """Two admissions racing are separated by the store, not by the read.

    A first attempt at this drove two threads through the fake with a barrier.
    It reported both admitted - and the trace said why: the barrier counts reads
    of the week counter, this path reads one row more than the paid path it was
    built for, and the threads came apart on the barrier rather than on the
    counter. It was measuring the harness.

    What can be read here is the operation that goes to the store: the counter
    is written against the exact version it was read at, so a second admission
    that read the same version is refused by the store. The paid path's own
    concurrency test covers the same code with a fake that matches its reads.
    """
    table = AtomicSupportTable()
    for index in range(3):
        _admit(table, f"q-{index}")

    calls: list[tuple[dict[str, Any], ...]] = []
    service.admit_teacher_support_case(
        support_case_id="q-cas",
        case_kind="question",
        beneficiary_id=STUDENT,
        observed_at=NOW,
        persist_case=_case_committer(
            table, kind="question", case_id="q-cas", beneficiary_id=STUDENT, calls=calls
        ),
        table=table,
    )

    counter_put = next(
        op["Put"]
        for op in calls[0]
        if "Put" in op and str(op["Put"]["Item"]["SK"]).startswith("WEEK#")
    )
    values = counter_put.get("ExpressionAttributeValues", {})
    assert ":expected_state_version" in values, "the counter is written unconditionally"
    # Three were already spent, so it was read at version 3 and writes version 4.
    assert values[":expected_state_version"] == 3
    assert counter_put["Item"]["state_version"] == 4
    assert counter_put["Item"]["admitted_cases"] == 4
