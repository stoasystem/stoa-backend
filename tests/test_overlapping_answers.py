"""Two answers of one student at the same moment both keep what they lead to (#628).

Every private write of a student checks the same account fence row, and every
answer of one Zurich day writes the same study-day row. When two answers
overlap, DynamoDB cancels one transaction with `TransactionConflict` on the
fence row - and, when both write the day, on the study-day row too. In the
run of 2026-11-20 that cost answers their receipt (a 503, #563), their review
card and usage event (fence busy), and their study day (fence and day busy:
`[TransactionConflict, TransactionConflict]`).

A cancelled transaction wrote nothing, so these doubles cancel the first
attempt at each one the way an overlapping answer does, then let the same
transaction through. Every answer must end with its receipt, its study day,
its review card and its usage event written.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pytest

from fakes.dynamodb import FakeTable, as_stored, transaction_canceled
from stoa.db import table as db_table
from stoa.db.repositories import practice_repo
from stoa.rule_violation import correlation_scope
from stoa.services import answer_recording, review_service

STUDENT = "student-1"
NOW = datetime(2026, 11, 20, 22, 30, tzinfo=timezone.utc)
DAY_KEY = (f"ACTIVITY#{STUDENT}", "DAY#2026-11-20")

EXERCISES: list[dict[str, Any]] = [
    {
        "challenge_id": f"exercise-{index}",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "brueche",
        "unit_id": "brueche-u1",
        "type": "text_input",
        "prompt": f"Berechne {index} + 1.",
        "correct_answer": str(index + 1),
        "explanation": "Eins dazu.",
    }
    for index in (1, 2)
]


def _key(operation: dict[str, Any]) -> tuple[str, str]:
    ((_, body),) = operation.items()
    key = body.get("Key") or body["Item"]
    return key["PK"]["S"], key["SK"]["S"]


class _Overlapped(FakeTable):
    """Cancels the first attempt at each transaction as an overlapping answer would.

    The fence row is always busy; the study-day row is busy too when the
    transaction writes it, since the overlapping answer writes the same day.
    """

    def __init__(self) -> None:
        super().__init__()
        self.seed_active_account(STUDENT)
        self._cancelled: set[str] = set()

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        attempt = repr(TransactItems)
        if attempt not in self._cancelled:
            self._cancelled.add(attempt)
            raise transaction_canceled(
                [
                    "TransactionConflict"
                    if _key(operation)[1] == "ACCOUNT_FENCE"
                    or _key(operation)[1].startswith("DAY#")
                    else "None"
                    for operation in TransactItems
                ]
            )
        return super().transact_write_items(TransactItems=TransactItems)


class _DayWrittenMeanwhile(FakeTable):
    """The overlapping answer writes today's study day just before this one does."""

    def __init__(self) -> None:
        super().__init__()
        self.seed_active_account(STUDENT)
        self._raced = False

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        if not self._raced and any(_key(operation) == DAY_KEY for operation in TransactItems):
            self._raced = True
            self.rows[DAY_KEY] = as_stored(
                {
                    "PK": DAY_KEY[0],
                    "SK": DAY_KEY[1],
                    "entity_type": "study_day",
                    "student_id": STUDENT,
                    "user_id": STUDENT,
                    "owner_id": STUDENT,
                    "account_fence_generation": 1,
                    "day": "2026-11-20",
                    "last_kind": "lesson",
                    "last_seen_at": "2026-11-20T22:29:59+00:00",
                }
            )
        return super().transact_write_items(TransactItems=TransactItems)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(db_table, "_sleep", lambda _seconds: None)


@pytest.fixture
def exercises(monkeypatch):
    by_id = {exercise["challenge_id"]: exercise for exercise in EXERCISES}
    monkeypatch.setattr(practice_repo, "get_challenge", lambda challenge_id: by_id.get(challenge_id))
    monkeypatch.setattr(practice_repo, "get_challenges", lambda _lesson_id: list(EXERCISES))
    return EXERCISES


def _lost(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING and record.name != "stoa.db.table"
    ]


def _rows(table: FakeTable, entity_type: str) -> list[dict[str, Any]]:
    return [row for row in table.rows.values() if row.get("entity_type") == entity_type]


def test_two_overlapping_answers_each_keep_every_write(exercises, caplog):
    table = _Overlapped()
    db_table.install(table)
    caplog.set_level(logging.WARNING)

    for exercise in exercises:
        answer_recording.answer_practice(STUDENT, exercise, exercise["correct_answer"], locale="de")

    assert len([
        row for (pk, sk), row in table.rows.items()
        if pk == f"ATTEMPTS#{STUDENT}" and sk.startswith("ATTEMPT#")
    ]) == 2
    assert len(_rows(table, "study_day")) == 1
    assert {row["SK"] for row in _rows(table, "review_card")} == {
        "CARD#exercise-1",
        "CARD#exercise-2",
    }
    assert len(_rows(table, "usage_ledger_event")) == 2
    # Each cancelled attempt is still logged as refused; no write is logged as lost.
    assert _lost(caplog) == []


def test_an_answer_whose_day_was_written_by_another_still_records_it(caplog):
    table = _DayWrittenMeanwhile()
    db_table.install(table)
    caplog.set_level(logging.WARNING)

    review_service.record_answer(
        student_id=STUDENT, challenge=EXERCISES[0], correct=True, answered_at=NOW
    )

    assert _lost(caplog) == []
    day = table.rows[DAY_KEY]
    assert day["last_kind"] == "practice"
    assert day["last_seen_at"] == NOW.isoformat()
    assert day["owner_id"] == STUDENT


def test_a_day_row_another_account_owns_is_left_alone(caplog):
    """The write that needs no read still never takes over another account's row."""
    table = FakeTable()
    table.seed_active_account(STUDENT)
    table.rows[DAY_KEY] = as_stored(
        {"PK": DAY_KEY[0], "SK": DAY_KEY[1], "owner_id": "someone-else", "day": "2026-11-20"}
    )
    db_table.install(table)

    with pytest.raises(db_table.WriteRefused):
        practice_repo.record_study_day(STUDENT, "2026-11-20", at=NOW.isoformat())

    assert table.rows[DAY_KEY]["owner_id"] == "someone-else"


class _FenceAlwaysBusy(FakeTable):
    def __init__(self) -> None:
        super().__init__()
        self.seed_active_account(STUDENT)

    def transact_write_items(self, *, TransactItems):  # noqa: N803
        raise transaction_canceled(
            ["TransactionConflict", *["None"] * (len(TransactItems) - 1)]
        )


def test_an_answer_refused_for_good_leaves_its_reason_and_the_id_the_student_saw(
    exercises, caplog
):
    """The 503's correlation id is in the log line that says why (#628)."""
    db_table.install(_FenceAlwaysBusy())
    caplog.set_level(logging.WARNING)

    with correlation_scope("corr-628"), pytest.raises(answer_recording.ReceiptUnavailable):
        answer_recording.answer_practice(STUDENT, exercises[0], "2", locale="de")

    (line,) = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Practice attempt persistence failed")
    ]
    assert "error=WriteRefused" in line
    assert "reasons=TransactionCanceledException" in line
    assert "correlation_id=corr-628" in line
