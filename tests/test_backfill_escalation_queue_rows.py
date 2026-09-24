"""The repair for escalations made before the teacher-queue row existed."""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable, as_stored

from scripts import backfill_escalation_queue_rows as backfill


STUDENT = "student-1"
REQUEST = "req-1"


def _table() -> FakeTable:
    table = FakeTable()
    table.seed_active_account(STUDENT)
    table.rows[("CONV#conv-1", "CONV")] = as_stored(
        {
            "PK": "CONV#conv-1",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": "conv-1",
            "student_id": STUDENT,
            "owner_id": STUDENT,
            "subject": "mathematics",
            "grade": "Sek1",
            "escalated": True,
            "escalation_status": "pending",
            "escalation_request_id": REQUEST,
            "escalation_message": "please help",
            "escalated_at": "2026-09-24T02:12:30+00:00",
        }
    )
    return table


def _conversation(table: FakeTable) -> dict[str, Any]:
    return dict(table.rows[("CONV#conv-1", "CONV")])


def test_reporting_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _table()
    before = dict(table.rows)

    outcome = backfill.repair(table, _conversation(table), apply=False)

    assert outcome.startswith("would write")
    assert table.rows == before


def test_applying_writes_the_row_the_teacher_queue_reads() -> None:
    from stoa.routers import teachers

    table = _table()

    backfill.repair(table, _conversation(table), apply=True)

    row = table.rows[(f"QUESTION#{REQUEST}", "META")]
    assert row["status"] == "escalated"
    assert row["student_id"] == STUDENT
    assert row["conversation_id"] == "conv-1"
    assert row["source"] == "conversation_escalation"
    # The row the repair writes has to satisfy the query that reads the queue,
    # not merely look like one.
    teachers.get_table = lambda: table
    page = teachers._list_escalated_questions()
    assert [item["question_id"] for item in page.items] == [REQUEST]


def test_running_it_twice_writes_once() -> None:
    table = _table()
    backfill.repair(table, _conversation(table), apply=True)
    written = dict(table.rows[(f"QUESTION#{REQUEST}", "META")])

    assert backfill.missing_queue_row(table, REQUEST) is False
    # And the write itself refuses rather than overwriting, whatever the caller
    # believed: a repair that clobbered a live case would lose the teacher on it.
    with pytest.raises(Exception):
        backfill.repair(table, _conversation(table), apply=True)
    assert dict(table.rows[(f"QUESTION#{REQUEST}", "META")]) == written


def test_an_escalation_on_a_closed_account_is_refused_not_repaired() -> None:
    table = _table()
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")] = as_stored(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "ACCOUNT_FENCE",
            "status": "deleted",
            "generation": 1,
        }
    )

    with pytest.raises(Exception):
        backfill.repair(table, _conversation(table), apply=True)
    assert (f"QUESTION#{REQUEST}", "META") not in table.rows


def test_an_incomplete_escalation_is_skipped_not_guessed_at() -> None:
    table = _table()
    conversation = {**_conversation(table), "escalation_request_id": ""}

    assert backfill.repair(table, conversation, apply=True) == "skipped: incomplete escalation"
    assert not [key for key in table.rows if key[0].startswith("QUESTION#")]


def test_an_account_closed_between_the_read_and_the_write_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fence is in the transaction, not only in the check before it.

    Reading the generation and then writing are two steps. Without the fence
    travelling with the write, an account closed in between gets a fresh
    escalated question written against it, and deletion has already been
    reported as complete.
    """
    table = _table()
    original = backfill.account_deletion_repo.require_active_account_fence

    def close_the_account_after_reading(user_id: str, *args: Any, **kwargs: Any):
        fence = original(user_id, *args, **kwargs)
        table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")] = as_stored(
            {
                "PK": f"USER#{STUDENT}",
                "SK": "ACCOUNT_FENCE",
                "status": "deleted",
                "generation": 1,
            }
        )
        return fence

    monkeypatch.setattr(
        backfill.account_deletion_repo,
        "require_active_account_fence",
        close_the_account_after_reading,
    )

    with pytest.raises(Exception):
        backfill.repair(table, _conversation(table), apply=True)
    assert (f"QUESTION#{REQUEST}", "META") not in table.rows
