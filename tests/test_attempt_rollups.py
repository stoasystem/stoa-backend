"""The answer rollups the star map reads instead of every answer (card 135).

A judged answer moves its lesson's rollup row in its own transaction; a
self-reported one does not. The star map trusts the rollups only under their
marker, and the facts it takes from them are the ones it took from every
answer. The backfill adds what the answers before the release say, and a
second run finds nothing to write.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable, transaction_canceled
from scripts import backfill_attempt_rollups as backfill
from stoa.db import table as db_table
from stoa.db.repositories import practice_repo, review_repo
from stoa.services import answer_recording, student_evidence

STUDENT = "student-135"
PK = f"ATTEMPTS#{STUDENT}"

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


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(db_table, "_sleep", lambda _seconds: None)


@pytest.fixture
def table(fake_table: FakeTable) -> FakeTable:
    fake_table.seed_active_account(STUDENT)
    return fake_table


def _rollup(table: FakeTable, lesson: str = "lesson-1", unit: str = "brueche-u1") -> dict[str, Any] | None:
    key = practice_repo.attempt_rollup_key(STUDENT, lesson, unit)
    return table.rows.get((key["PK"], key["SK"]))


def _put(correct: bool, exercise: str = "exercise-1", **options: Any) -> dict[str, Any]:
    return practice_repo.put_attempt(
        STUDENT,
        exercise,
        "2",
        correct,
        lesson_id=options.pop("lesson_id", "lesson-1"),
        unit_id=options.pop("unit_id", "brueche-u1"),
        **options,
    )


# -- the write ------------------------------------------------------------------------------


def test_a_judged_answer_moves_its_rollup_in_the_same_transaction(table):
    _put(False, created_at="2026-11-20T10:00:00+00:00")
    _put(True, created_at="2026-11-20T10:01:00+00:00")
    _put(True, "exercise-2", asked_ai=True, created_at="2026-11-20T10:02:00+00:00")

    row = _rollup(table)
    assert row is not None
    assert row["entity_type"] == "practice_attempt_rollup"
    assert row["right_alone"] == {"exercise-1"}
    assert row["right_asked"] == {"exercise-2"}
    assert row["last_judged_at"] == "2026-11-20T10:02:00+00:00"
    assert (row["student_id"], row["user_id"], row["owner_id"]) == (STUDENT,) * 3
    assert row["account_fence_generation"] == 1
    (transaction, *_rest) = [
        request["operations"]
        for operation, request in table.requests
        if operation == "transact_write_items"
    ]
    keys = [next(iter(op.values())).get("Key") or next(iter(op.values()))["Item"] for op in transaction]
    assert {"PK": PK, "SK": "ROLLUP#L#lesson-1#U#brueche-u1"} in [
        {"PK": key["PK"], "SK": key["SK"]} for key in keys
    ]


def test_an_answer_without_lesson_or_star_has_a_rollup_all_the_same(table):
    _put(True, lesson_id="", unit_id="")

    row = table.rows[(PK, "ROLLUP#L#-#U#-")]
    assert (row["lesson_id"], row["unit_id"]) == ("", "")
    assert row["right_alone"] == {"exercise-1"}


def test_a_self_reported_answer_moves_no_rollup(table):
    practice_repo.record_attempt(
        STUDENT, "exercise-1", True, lesson_id="lesson-1", self_reported=True
    )
    _put(True, self_reported=True)

    assert not [key for key in table.rows if key[0] == PK and key[1].startswith("ROLLUP#")]
    assert len([key for key in table.rows if key[0] == PK]) == 2


def test_an_answer_refused_for_its_own_key_adds_nothing_to_the_rollup(table):
    _put(False, attempt_id="same", created_at="2026-11-20T10:00:00+00:00")
    before = dict(_rollup(table) or {})

    with pytest.raises(db_table.WriteRefused):
        _put(True, "exercise-2", attempt_id="same", created_at="2026-11-20T11:00:00+00:00")

    assert _rollup(table) == before
    assert "right_alone" not in before


class _RollupBusyOnce(FakeTable):
    """The other answer of the lesson holds the rollup row: each transaction's first try fails."""

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
                    if next(iter(operation.values())).get("Key", {}).get("SK", {}).get("S", "").startswith("ROLLUP#")
                    else "None"
                    for operation in TransactItems
                ]
            )
        return super().transact_write_items(TransactItems=TransactItems)


def test_two_answers_of_one_lesson_meeting_on_its_rollup_both_get_their_receipt(monkeypatch):
    """A conflict on the rollup row is sent again, not a 503 (the cost of #563, #628)."""
    table = _RollupBusyOnce()
    db_table.install(table)
    by_id = {exercise["challenge_id"]: exercise for exercise in EXERCISES}
    monkeypatch.setattr(practice_repo, "get_challenge", lambda challenge_id: by_id.get(challenge_id))
    monkeypatch.setattr(practice_repo, "get_challenges", lambda _lesson_id: list(EXERCISES))

    for exercise in EXERCISES:
        answer_recording.answer_practice(STUDENT, exercise, exercise["correct_answer"], locale="de")

    assert len([key for key in table.rows if key[0] == PK and key[1].startswith("ATTEMPT#")]) == 2
    assert _rollup(table)["right_alone"] == {"exercise-1", "exercise-2"}


# -- the read -------------------------------------------------------------------------------

ATTEMPTS: list[dict[str, Any]] = [
    {"challenge_id": "c1", "lesson_id": "l1", "unit_id": "u1", "correct": True,
     "created_at": "2026-01-02T09:00:00+00:00"},
    {"challenge_id": "c2", "lesson_id": "l1", "unit_id": "u1", "correct": True, "asked_ai": True,
     "created_at": "2026-01-03T09:00:00+00:00"},
    {"challenge_id": "c2", "lesson_id": "l1", "unit_id": "u1", "correct": True,
     "created_at": "2026-01-01T09:00:00+00:00"},
    {"challenge_id": "c3", "lesson_id": "l2", "unit_id": "", "correct": True, "asked_ai": True,
     "created_at": "2026-01-04T09:00:00+00:00"},
    {"challenge_id": "c4", "lesson_id": "l2", "unit_id": "u2", "correct": False,
     "created_at": "2026-01-06T09:00:00+00:00"},
    {"challenge_id": "c5", "lesson_id": "l2", "unit_id": "u2", "correct": True, "self_reported": True,
     "created_at": "2026-01-07T09:00:00+00:00"},
    {"exercise_id": "c6", "lesson_id": "l3", "unit_id": "u3", "correct": True,
     "created_at": "2026-01-05T09:00:00+00:00"},
]
CATALOG = {
    "subjects": [],
    "topics": [],
    "units": [{"id": unit} for unit in ("u1", "u2", "u3")],
    "lessons": [{"id": "l1", "unitId": "u1"}, {"id": "l2", "unitId": "u2"}, {"id": "l3", "unitId": "u3"}],
}


def _facts(evidence: student_evidence.StudentEvidence) -> tuple[Any, ...]:
    return (
        evidence.answered_right,
        evidence.right_answers_by_unit,
        evidence.last_activity_by_unit,
    )


def _evidence(**partitions: Any) -> student_evidence.StudentEvidence:
    value = fake_evidence.evidence(STUDENT, catalog=CATALOG, attempts=ATTEMPTS)
    value.source.partitions.update(partitions)
    return value


def test_the_rollups_say_what_every_answer_says():
    from_answers = _evidence()
    from_rollups = _evidence().read_all(("attempt_rollups",))

    assert _facts(from_rollups) == _facts(from_answers)
    assert from_rollups.answered_right == {"c1", "c2", "c3", "c6"}
    assert from_rollups.right_answers_by_unit["u1"] == student_evidence.RightAnswers(2, 0)
    assert from_rollups.right_answers_by_unit["u2"] == student_evidence.RightAnswers(0, 1)
    assert from_rollups.last_activity_by_unit["u2"] == "2026-01-06T09:00:00+00:00"
    assert "attempts" not in from_rollups.source.reads
    assert "attempt_facts" not in from_rollups.source.reads


def test_rollups_without_their_marker_are_not_trusted():
    """Rollups that miss an answer, as before the backfill: the answers are read instead."""
    stale = fake_evidence.rollup_rows(STUDENT, ATTEMPTS[:1], complete=False)
    evidence = _evidence(attempt_rollups=stale).read_all(("attempt_rollups",))

    assert _facts(evidence) == _facts(_evidence())
    assert [read for read in evidence.source.reads if read.startswith("attempt")] == [
        "attempt_rollups",
        "attempt_facts",
    ]
    # They do not agree with the answers, so no marker is written either.
    assert evidence.source.marked == []


def test_a_marker_of_another_version_is_no_marker():
    stale = fake_evidence.rollup_rows(STUDENT, ATTEMPTS[:1], complete=True)
    for row in stale:
        if row["SK"] == practice_repo.ATTEMPT_ROLLUP_STATE_SK:
            row["rollup_version"] = practice_repo.ATTEMPT_ROLLUP_VERSION + 1
    evidence = _evidence(attempt_rollups=stale).read_all(("attempt_rollups",))

    assert evidence.answered_right == {"c1", "c2", "c3", "c6"}


def test_rollups_that_agree_are_marked_by_the_read():
    agreeing = fake_evidence.rollup_rows(STUDENT, ATTEMPTS, complete=False)
    evidence = _evidence(attempt_rollups=agreeing).read_all(("attempt_rollups",))

    assert evidence.answered_right == {"c1", "c2", "c3", "c6"}
    assert evidence.source.marked == [STUDENT]


def test_answers_read_whole_are_preferred_to_the_rollups():
    """A page that read every answer (the mistakes) takes the facts from them."""
    evidence = _evidence()
    evidence.read_all(("attempts", "attempt_rollups"))

    assert _facts(evidence) == _facts(_evidence())


def test_the_due_counts_come_from_the_due_times_alone():
    evidence = fake_evidence.evidence(
        STUDENT, catalog=CATALOG, review_due={"u1": 2, "u2": 1}
    )

    assert evidence.review_due_by_unit == {"u1": 2, "u2": 1}
    assert evidence.source.reads == ["review_due"]


# -- the projections reach the table --------------------------------------------------------


def test_the_lighter_reads_ask_the_table_for_their_fields_only(table):
    """The fake table returns whole rows whatever is asked; what is asked is pinned here."""
    practice_repo.list_attempt_facts(STUDENT)
    review_repo.list_card_dues(STUDENT)

    facts, dues = (request for operation, request in table.requests if operation == "query")
    assert sorted(facts["ExpressionAttributeNames"].values()) == sorted(practice_repo.ATTEMPT_FACT_FIELDS)
    assert facts["ProjectionExpression"].split(", ") == list(facts["ExpressionAttributeNames"])
    assert facts["ConsistentRead"] is True
    assert "prompt" not in facts["ExpressionAttributeNames"].values()
    assert sorted(dues["ExpressionAttributeNames"].values()) == ["PK", "SK", "due_at", "lesson_id"]
    assert dues["ProjectionExpression"].split(", ") == list(dues["ExpressionAttributeNames"])


# -- the backfill ---------------------------------------------------------------------------


def _profile(table: FakeTable, user_id: str, role: str = "student") -> None:
    table.seed_active_account(user_id)
    table.seed(
        {
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "user_id": user_id,
            "role": role,
            "listing": "account_profile",
            "listed_at": "2026-01-01T00:00:00+00:00",
        }
    )


def _seed_old_answers(table: FakeTable) -> None:
    """Answers saved before the release: no rollup moved with them."""
    for index, attempt in enumerate(ATTEMPTS):
        table.seed({"PK": PK, "SK": f"ATTEMPT#old-{index}", "student_id": STUDENT, **attempt})


def test_the_backfill_reports_writes_and_then_finds_nothing(table, capsys):
    _profile(table, STUDENT)
    _profile(table, "nobody-answered")
    _profile(table, "a-teacher", role="teacher")
    _seed_old_answers(table)
    # One answer after the release, with a later moment than any old one.
    _put(True, "c9", lesson_id="l1", unit_id="u1", created_at="2026-02-01T09:00:00+00:00")
    rows_before = dict(table.rows)

    assert backfill.run(table, apply_writes=False) == 0
    dry = capsys.readouterr().out
    assert "accounts: 2" in dry
    assert "marker missing: 2" in dry
    assert "[DRY RUN]" in dry
    assert table.rows == rows_before

    assert backfill.run(table, apply_writes=True) == 0
    capsys.readouterr()
    u1 = table.rows[(PK, "ROLLUP#L#l1#U#u1")]
    assert u1["right_alone"] == {"c1", "c2", "c9"}
    assert u1["right_asked"] == {"c2"}
    # The later moment the live answer set is not moved back.
    assert u1["last_judged_at"] == "2026-02-01T09:00:00+00:00"
    assert table.rows[(PK, "ROLLUP#L#l2#U#-")]["right_asked"] == {"c3"}
    assert "right_alone" not in table.rows[(PK, "ROLLUP#L#l2#U#u2")]
    assert table.rows[(PK, practice_repo.ATTEMPT_ROLLUP_STATE_SK)]["rollup_version"] == 1
    assert ("ATTEMPTS#nobody-answered", practice_repo.ATTEMPT_ROLLUP_STATE_SK) in table.rows

    evidence = student_evidence.StudentEvidence(
        STUDENT, content=fake_evidence.content(catalog=CATALOG)
    ).read_all(("attempt_rollups",))
    whole = student_evidence.StudentEvidence(STUDENT, content=fake_evidence.content(catalog=CATALOG))
    assert _facts(evidence) == _facts(whole)

    assert backfill.run(table, apply_writes=False) == 0
    again = capsys.readouterr().out
    assert "accounts: 2 | in agreement: 2" in again
    assert "First accounts that differ" not in again


def test_the_backfill_leaves_an_account_being_deleted(table, capsys):
    _profile(table, STUDENT)
    _seed_old_answers(table)
    fence = dict(table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")])
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")] = {**fence, "status": "deleting"}

    backfill.run(table, apply_writes=True)

    assert "account not writable, skipped: 1" in capsys.readouterr().out
    assert not [key for key in table.rows if key[0] == PK and key[1].startswith("ROLLUP#")]
