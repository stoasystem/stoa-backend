"""Answering a question decides when it comes back.

The scheduler is tested on its own; these cover the join between it, storage,
and the questions a student is handed.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from stoa.db.repositories import review_repo
from stoa.services import review_scheduler, review_service

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)

CHALLENGE = {
    "challenge_id": "brueche-l1-c1",
    "lesson_id": "brueche-l1",
    "subject_id": "mathematics",
    "topic_id": "brueche",
    "prompt": "Was ist 1/2 + 1/4?",
    "options": ["3/4", "2/6", "1/6"],
    "correct_answer": "3/4",
    "type": "multiple_choice",
}


class FakeTable:
    """Enough of the table for the repository's non-transactional path."""

    def __init__(self):
        self.items: dict[tuple[str, str], dict] = {}

    def put_item(self, **kwargs):
        item = kwargs["Item"]
        self.items[(item["PK"], item["SK"])] = item

    def get_item(self, **kwargs):
        key = kwargs["Key"]
        found = self.items.get((key["PK"], key["SK"]))
        return {"Item": found} if found else {}

    def query(self, **kwargs):
        return {"Items": list(self.items.values())}


def use_table(monkeypatch) -> FakeTable:
    table = FakeTable()
    monkeypatch.setattr(review_repo, "get_table", lambda: table)
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)
    return table


def test_a_stored_card_survives_the_round_trip(monkeypatch):
    use_table(monkeypatch)
    state = review_scheduler.review(review_scheduler.new_card(now=NOW), review_scheduler.GOOD, now=NOW)

    review_repo.save_card("student-1", "brueche-l1-c1", state)
    restored = review_repo.state_from_item(
        review_repo.get_card("student-1", "brueche-l1-c1"), now=NOW
    )

    assert abs(restored.stability - state.stability) < 0.001
    assert abs(restored.difficulty - state.difficulty) < 0.001
    assert restored.due_at == state.due_at
    assert restored.reps == state.reps


def test_the_schedule_is_stored_as_decimal_not_float(monkeypatch):
    # DynamoDB rejects floats outright, and this codebase has been bitten by it.
    table = use_table(monkeypatch)
    state = review_scheduler.review(review_scheduler.new_card(now=NOW), review_scheduler.GOOD, now=NOW)

    review_repo.save_card("student-1", "brueche-l1-c1", state)

    stored = table.items[("REVIEW#student-1", "CARD#brueche-l1-c1")]
    assert isinstance(stored["stability"], Decimal)
    assert isinstance(stored["difficulty"], Decimal)
    assert not any(isinstance(value, float) for value in stored.values())


def test_a_wrong_answer_puts_the_question_back_in_the_queue(monkeypatch):
    use_table(monkeypatch)

    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=False, answered_at=NOW
    )

    due = review_repo.list_due_cards("student-1", now=NOW + timedelta(hours=1))
    assert [card["challenge_id"] for card in due] == ["brueche-l1-c1"]


def test_a_right_answer_takes_the_question_out_of_the_queue(monkeypatch):
    use_table(monkeypatch)

    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=True, answered_at=NOW
    )

    assert review_repo.list_due_cards("student-1", now=NOW + timedelta(hours=1)) == []
    # ...but not forever.
    later = review_repo.list_due_cards("student-1", now=NOW + timedelta(days=365))
    assert [card["challenge_id"] for card in later] == ["brueche-l1-c1"]


def test_answering_the_same_question_again_moves_its_schedule(monkeypatch):
    use_table(monkeypatch)
    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=True, answered_at=NOW
    )
    first_due = review_repo.get_card("student-1", "brueche-l1-c1")["due_at"]

    review_service.record_answer(
        student_id="student-1",
        challenge=CHALLENGE,
        correct=True,
        answered_at=NOW + timedelta(days=4),
    )

    card = review_repo.get_card("student-1", "brueche-l1-c1")
    assert card["due_at"] > first_due
    assert card["reps"] == 2


def test_the_due_list_hands_back_the_question_to_attempt(monkeypatch):
    use_table(monkeypatch)
    monkeypatch.setattr(
        review_service.practice_repo, "get_challenge", lambda challenge_id: CHALLENGE
    )
    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=False, answered_at=NOW
    )

    result = review_service.due_review(student_id="student-1", now=NOW + timedelta(hours=1))

    assert result["dueCount"] == 1
    card = result["items"][0]
    assert card["prompt"] == "Was ist 1/2 + 1/4?"
    assert card["options"] == ["3/4", "2/6", "1/6"]
    assert "correct_answer" not in card and "correctAnswer" not in card


def test_a_withdrawn_question_is_not_offered_for_review(monkeypatch):
    use_table(monkeypatch)
    monkeypatch.setattr(review_service.practice_repo, "get_challenge", lambda challenge_id: None)
    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=False, answered_at=NOW
    )

    result = review_service.due_review(student_id="student-1", now=NOW + timedelta(hours=1))

    assert result["items"] == []
    assert result["dueCount"] == 0


def test_a_scheduling_failure_does_not_cost_the_student_their_answer(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("dynamo is having a day")

    monkeypatch.setattr(review_repo, "get_card", explode)

    assert (
        review_service.record_answer(
            student_id="student-1", challenge=CHALLENGE, correct=True, answered_at=NOW
        )
        is None
    )


def test_the_summary_counts_what_is_waiting(monkeypatch):
    use_table(monkeypatch)
    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=False, answered_at=NOW
    )
    other = {**CHALLENGE, "challenge_id": "brueche-l1-c2"}
    review_service.record_answer(
        student_id="student-1", challenge=other, correct=True, answered_at=NOW
    )

    summary = review_service.review_summary(student_id="student-1", now=NOW + timedelta(hours=1))

    assert summary["dueCount"] == 1
    assert summary["scheduledCount"] == 2
    assert summary["nextDueAt"] > NOW.isoformat()


def test_a_card_carries_where_the_question_came_from(monkeypatch):
    use_table(monkeypatch)

    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=True, answered_at=NOW
    )

    card = review_repo.get_card("student-1", "brueche-l1-c1")
    assert card["subject_id"] == "mathematics"
    assert card["topic_id"] == "brueche"
    assert card["lesson_id"] == "brueche-l1"


def test_answering_counts_towards_the_streak(monkeypatch):
    """Clearing a review has to keep a streak alive, or there is no reason to."""
    from stoa.db.repositories import practice_repo
    from stoa.services import curriculum_service

    table = use_table(monkeypatch)
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(practice_repo, "_write_generation", lambda *a, **k: 1)

    review_service.record_answer(
        student_id="student-1", challenge=CHALLENGE, correct=True, answered_at=NOW
    )

    days = practice_repo.list_study_days("student-1")
    assert days == ["2026-03-02"]
    # No lesson was completed, which was the only thing that used to count.
    assert curriculum_service.study_streak([], today=NOW.date(), study_days=days) == 1


def test_a_day_is_recorded_once_however_many_questions(monkeypatch):
    from stoa.db.repositories import practice_repo

    table = use_table(monkeypatch)
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(practice_repo, "_write_generation", lambda *a, **k: 1)

    for index in range(3):
        review_service.record_answer(
            student_id="student-1",
            challenge={**CHALLENGE, "challenge_id": f"brueche-l1-c{index}"},
            correct=True,
            answered_at=NOW,
        )

    assert practice_repo.list_study_days("student-1") == ["2026-03-02"]


def test_a_streak_earned_before_this_existed_still_stands(monkeypatch):
    """Lesson completions were the only record; they must keep counting."""
    from datetime import date

    from stoa.services import curriculum_service

    progress = [
        {"status": "completed", "completed_at": "2026-03-01T10:00:00+00:00"},
        {"status": "completed", "completed_at": "2026-02-28T10:00:00+00:00"},
    ]

    streak = curriculum_service.study_streak(
        progress, today=date(2026, 3, 2), study_days=["2026-03-02"]
    )

    assert streak == 3
