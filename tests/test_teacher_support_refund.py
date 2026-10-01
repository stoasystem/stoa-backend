"""#86: giving a teacher-support case back, once, to the week it was taken from.

A case is spent the moment a student asks for a teacher. A request the student
withdraws before any teacher took it - or, later, one that expires (#87) - gives
the case back. The refund is the admission run backwards: the receipt is marked
once, and the counter of the receipt's own week goes down by one under the same
compare-and-set the admission uses, so a refund and an admission racing for one
counter cannot both win.

These run on the shared table double, which evaluates every condition.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fakes.dynamodb import FakeTable
import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import teacher_support_allowance_service as service


NOW = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
STUDENT = "student-refund-1"
FENCE = 6


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    profile = {
        "user_id": STUDENT,
        "role": "student",
        "account_status": "active",
        "version": Decimal("21"),
    }
    monkeypatch.setattr(
        service.user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(profile)
    )
    monkeypatch.setattr(
        service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda *_args, **_kwargs: None,
    )
    built = FakeTable()
    built.seed(
        {"PK": f"USER#{STUDENT}", "SK": "PROFILE", **profile},
        {
            "PK": f"USER#{STUDENT}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": Decimal(FENCE),
        },
    )
    return built


def _commit(table: FakeTable, case_id: str, extra: list[dict[str, Any]] | None = None):
    def commit(operations: tuple[dict[str, Any], ...]) -> bool:
        try:
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(STUDENT, FENCE),
                    *operations,
                    *(extra or []),
                ],
                table=table,
            )
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    return commit


def _admit(table: FakeTable, case_id: str, *, at: datetime = NOW):
    return service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="conversation",
        beneficiary_id=STUDENT,
        observed_at=at,
        persist_case=_commit(table, case_id),
        table=table,
    )


def _refund(table: FakeTable, case_id: str, *, at: datetime = NOW, persist=None):
    def commit(operations: tuple[dict[str, Any], ...]) -> bool:
        try:
            account_deletion_repo.transact(list(operations), table=table)
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    return service.refund_teacher_support_case(
        support_case_id=case_id,
        case_kind="conversation",
        beneficiary_id=STUDENT,
        reason="withdrawn",
        persist_refund=persist or commit,
        observed_at=at,
        table=table,
    )


def _spent(table: FakeTable, *, at: datetime = NOW) -> int:
    projection = service.get_teacher_support_projection(
        beneficiary_id=STUDENT, observed_at=at, table=table
    )
    return int(projection["admittedCases"])


def _receipt(table: FakeTable, case_id: str) -> dict[str, Any]:
    key = service._case_key("conversation", case_id)
    return table.rows[(key["PK"], key["SK"])]


Refund = service.TeacherSupportRefundDisposition


def test_a_refund_gives_the_case_back_and_marks_the_receipt(table: FakeTable) -> None:
    _admit(table, "conv-1")
    _admit(table, "conv-2")
    assert _spent(table) == 2
    result = _refund(table, "conv-1")
    assert result.disposition is Refund.REFUNDED
    assert _spent(table) == 1
    receipt = _receipt(table, "conv-1")
    assert receipt["refund_reason"] == "withdrawn"
    assert receipt["refunded_at"] == NOW.isoformat()
    assert receipt["state_version"] == 2


def test_a_second_refund_gives_nothing_more(table: FakeTable) -> None:
    _admit(table, "conv-1")
    assert _refund(table, "conv-1").disposition is Refund.REFUNDED
    assert _refund(table, "conv-1").disposition is Refund.ALREADY_REFUNDED
    assert _spent(table) == 0


def test_a_case_never_admitted_is_not_refunded(table: FakeTable) -> None:
    _admit(table, "conv-1")
    assert _refund(table, "conv-never").disposition is Refund.NOT_ADMITTED
    assert _spent(table) == 1


def test_another_students_receipt_is_not_refunded(table: FakeTable) -> None:
    _admit(table, "conv-1")
    result = service.refund_teacher_support_case(
        support_case_id="conv-1",
        case_kind="conversation",
        beneficiary_id="someone-else",
        reason="withdrawn",
        persist_refund=lambda operations: True,
        observed_at=NOW,
        table=table,
    )
    assert result.disposition is Refund.IDEMPOTENCY_CONFLICT
    assert _spent(table) == 1


def test_a_refund_after_the_week_turned_goes_back_to_the_week_it_was_taken_from(
    table: FakeTable,
) -> None:
    _admit(table, "conv-old")
    next_week = NOW + timedelta(days=7)
    _admit(table, "conv-new", at=next_week)
    assert _refund(table, "conv-old", at=next_week).disposition is Refund.REFUNDED
    assert _spent(table, at=NOW) == 0
    assert _spent(table, at=next_week) == 1


def test_a_refunded_case_replays_rather_than_being_admitted_again(table: FakeTable) -> None:
    _admit(table, "conv-1")
    _refund(table, "conv-1")
    again = _admit(table, "conv-1")
    assert again.disposition is service.TeacherSupportAdmissionDisposition.REPLAYED
    assert _spent(table) == 0


def test_the_callers_writes_commit_with_the_refund_or_not_at_all(table: FakeTable) -> None:
    _admit(table, "conv-1")
    # The caller's own row move is refused, so the refund must not land either.
    refusing = {
        "ConditionCheck": {
            "Key": {"PK": "CONV#conv-1", "SK": "CONV"},
            "ConditionExpression": "attribute_exists(PK)",
        }
    }

    def commit(operations: tuple[dict[str, Any], ...]) -> bool:
        try:
            account_deletion_repo.transact([*operations, refusing], table=table)
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    result = _refund(table, "conv-1", persist=commit)
    assert result.disposition is Refund.RETRYABLE
    assert _spent(table) == 1
    assert "refunded_at" not in _receipt(table, "conv-1")


@pytest.mark.parametrize("state", ["missing", "refunded"])
def test_the_caller_is_still_given_one_write_to_commit_its_own_rows(
    table: FakeTable, state: str
) -> None:
    # Withdrawing commits the two row moves whatever the receipt says; the
    # refund hands over a check on what it saw instead of a counter change.
    _admit(table, "conv-1")
    if state == "refunded":
        _refund(table, "conv-1")
    seen: list[tuple[dict[str, Any], ...]] = []

    def commit(operations: tuple[dict[str, Any], ...]) -> bool:
        seen.append(operations)
        account_deletion_repo.transact(list(operations), table=table)
        return True

    case_id = "conv-missing" if state == "missing" else "conv-1"
    result = _refund(table, case_id, persist=commit)
    assert result.disposition in {Refund.NOT_ADMITTED, Refund.ALREADY_REFUNDED}
    [operations] = seen
    assert all("ConditionCheck" in operation for operation in operations)
    assert _spent(table) == (0 if state == "refunded" else 1)


def test_a_counter_moved_by_an_admission_is_retried_not_overwritten(
    table: FakeTable,
) -> None:
    _admit(table, "conv-1")
    calls = 0

    def admit_in_between(operations: tuple[dict[str, Any], ...]) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            # Another request is admitted after the refund read the counter.
            _admit(table, "conv-2")
        try:
            account_deletion_repo.transact(list(operations), table=table)
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    result = _refund(table, "conv-1", persist=admit_in_between)
    assert result.disposition is Refund.REFUNDED
    assert calls == 2
    assert _spent(table) == 1


def test_two_refunds_racing_give_back_one_case(table: FakeTable) -> None:
    _admit(table, "conv-1")
    _admit(table, "conv-2")
    calls = 0

    def race(operations: tuple[dict[str, Any], ...]) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert _refund(table, "conv-1").disposition is Refund.REFUNDED
        try:
            account_deletion_repo.transact(list(operations), table=table)
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    result = _refund(table, "conv-1", persist=race)
    assert result.disposition is Refund.ALREADY_REFUNDED
    assert _spent(table) == 1


def test_a_counter_already_at_zero_is_not_taken_below_it(table: FakeTable) -> None:
    _admit(table, "conv-1")
    receipt = _receipt(table, "conv-1")
    counter_key = service._counter_key(
        str(receipt["support_scope_id"]), str(receipt["week_identity"])
    )
    table.rows[(counter_key["PK"], counter_key["SK"])]["admitted_cases"] = Decimal(0)
    assert _refund(table, "conv-1").disposition is Refund.RETRYABLE
    assert "refunded_at" not in _receipt(table, "conv-1")
