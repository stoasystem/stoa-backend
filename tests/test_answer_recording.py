"""Judge one answer and record what it leads to, per mode (`answer_recording`, #213).

Each mode writes its own set of things and nothing else: practice writes the
receipt, the analytics signal, the review card and the usage event; a quiz
answer writes only its usage event; passing a star quiz writes only review
cards. The feedback comes from the exercise as the reader sees it, in the
reader's language where it has none of its own (#128).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from stoa.db.repositories import practice_repo
from stoa.services import (
    answer_recording,
    curriculum_analytics_service,
    message_catalog,
    review_service,
    usage_ledger_service,
)

EXERCISE: dict[str, Any] = {
    "challenge_id": "exercise-1",
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "brueche",
    "unit_id": "brueche-u1",
    "type": "text_input",
    "prompt": "Berechne 1/4 + 3/4.",
    "correct_answer": "1",
    "explanation": "4/4 = 1.",
}


class _Writes:
    """Every write a judged answer can lead to, by kind."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, exercises: list[dict[str, Any]]) -> None:
        self.by_kind: dict[str, list[dict[str, Any]]] = {
            "receipt": [],
            "analytics": [],
            "review": [],
            "usage": [],
        }
        by_id = {exercise["challenge_id"]: exercise for exercise in exercises}
        monkeypatch.setattr(practice_repo, "get_challenge", lambda challenge_id: by_id.get(challenge_id))
        monkeypatch.setattr(practice_repo, "get_challenges", lambda _lesson_id: list(exercises))
        monkeypatch.setattr(practice_repo, "put_attempt", self._put_attempt)
        monkeypatch.setattr(
            curriculum_analytics_service,
            "record_practice_attempt",
            lambda **kwargs: self.by_kind["analytics"].append(kwargs),
        )
        monkeypatch.setattr(
            review_service, "record_answer", lambda **kwargs: self.by_kind["review"].append(kwargs)
        )
        # The event the module asks for; whether the ledger takes it is the ledger's.
        monkeypatch.setattr(
            answer_recording,
            "record_practice_usage",
            lambda **kwargs: self.by_kind["usage"].append(kwargs),
        )

    def _put_attempt(self, student_id, challenge_id, submitted_answer, correct, **fields):
        receipt = {
            "attempt_id": "attempt-1",
            "student_id": student_id,
            "challenge_id": challenge_id,
            "student_answer": submitted_answer,
            "submitted_answer": submitted_answer,
            "correct": correct,
            **fields,
        }
        self.by_kind["receipt"].append(receipt)
        return receipt

    def kinds(self) -> set[str]:
        return {kind for kind, writes in self.by_kind.items() if writes}


def _practice(answer: str) -> None:
    answer_recording.answer_practice("student-1", EXERCISE, answer, locale="de")


def _quiz_answer(answer: str) -> None:
    judgement = answer_recording.judge(EXERCISE, answer, locale="de")
    answer_recording.record_quiz_answer(
        "student-1", judgement, resource_id="quiz-1:1", metadata={"quizId": "quiz-1"}
    )


def _star_quiz_pass(answer: str) -> None:
    answer_recording.record_star_quiz_pass(
        "student-1",
        [
            {
                "exerciseId": "exercise-1",
                "correct": answer == "1",
                "answeredAt": "2026-11-07T10:00:00+00:00",
            },
            # Gone since the paper was drawn: skipped, not an error.
            {"exerciseId": "gone", "correct": True, "answeredAt": "2026-11-07T10:01:00+00:00"},
        ],
    )


@pytest.mark.parametrize(
    ("mode", "writes"),
    [
        (_practice, {"receipt", "analytics", "review", "usage"}),
        (_quiz_answer, {"usage"}),
        (_star_quiz_pass, {"review"}),
    ],
    ids=["practice", "quiz answer", "star quiz pass"],
)
@pytest.mark.parametrize("answer", ["1", "2"], ids=["right", "wrong"])
def test_each_mode_writes_its_own_things_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, mode, writes: set[str], answer: str
) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE])

    mode(answer)

    assert recorded.kinds() == writes
    for review in recorded.by_kind["review"]:
        assert review["student_id"] == "student-1"
        assert review["challenge"]["challenge_id"] == "exercise-1"
        assert review["correct"] is (answer == "1")


def test_practice_records_one_receipt_signal_card_and_event(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE, {**EXERCISE, "challenge_id": "exercise-2"}])

    result = answer_recording.answer_practice("student-1", EXERCISE, "2", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["correct"] is False
    assert receipt["student_answer"] == "2"
    assert receipt["lesson_id"] == "lesson-1"
    assert receipt["unit_id"] == "brueche-u1"
    assert receipt["next_challenge_id"] == "exercise-2"
    assert receipt["challenge_version"] == f"sha256:{receipt['challenge_content_hash']}"
    assert receipt["feedback"] == receipt["incorrect_feedback"]
    assert result.correct is False and result.standard_answer == "1"
    [signal] = recorded.by_kind["analytics"]
    assert signal == {"student_id": "student-1", "challenge": EXERCISE, "correct": False}
    [card] = recorded.by_kind["review"]
    assert card["answered_at"] == datetime.fromisoformat(receipt["created_at"])
    [event] = recorded.by_kind["usage"]
    assert event["action"] == usage_ledger_service.PRACTICE_ANSWER_ACTION
    assert event["metadata"] == {"status": "submitted"}


def test_a_quiz_answer_event_carries_the_quiz_and_the_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE])

    judgement = answer_recording.judge(EXERCISE, "1", locale="de")
    answer_recording.record_quiz_answer(
        "student-1", judgement, resource_id="quiz-1:3", metadata={"quizId": "quiz-1", "status": "passed"}
    )

    [event] = recorded.by_kind["usage"]
    assert event["action"] == usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION
    assert event["metadata"] == {"quizId": "quiz-1", "status": "passed", "correct": True}
    assert event["account_fence_generation"] is None


def test_the_star_quiz_pass_schedules_each_answer_at_its_moment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE])

    _star_quiz_pass("2")

    [card] = recorded.by_kind["review"]
    assert card["correct"] is False
    assert card["answered_at"] == datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "mode", [_practice, _quiz_answer], ids=["practice", "quiz answer"]
)
@pytest.mark.parametrize("answer", [{"x": "1"}, [["1"]], ["1"] * 51])
def test_an_answer_that_cannot_be_one_is_refused_before_anything_is_written(
    monkeypatch: pytest.MonkeyPatch, mode, answer: object
) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE])

    with pytest.raises(answer_recording.AnswerInvalid):
        mode(answer)

    assert recorded.kinds() == set()


def test_a_receipt_that_cannot_be_written_leaves_no_other_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [EXERCISE])

    def fail(*_args, **_kwargs):
        raise RuntimeError("table unavailable")

    monkeypatch.setattr(practice_repo, "put_attempt", fail)

    with pytest.raises(answer_recording.ReceiptUnavailable):
        _practice("1")

    assert recorded.kinds() == set()


# ── feedback in the reader's language (#128) ───────────────────────────────

FRENCH = {
    "prompt": "Calcule 1/4 + 3/4.",
    "correct_answer": "1",
    "correct_feedback": "Exactement, 4/4 = 1.",
    "incorrect_feedback": "Additionne les numérateurs.",
}


@pytest.mark.parametrize(
    ("exercise", "answer", "expected"),
    [
        (
            {
                **EXERCISE,
                "correct_feedback": "Genau, 4/4 = 1.",
                "incorrect_feedback": "Zähler addieren.",
                "translations": {"fr": FRENCH},
            },
            "1",
            "Exactement, 4/4 = 1.",
        ),
        (
            {
                **EXERCISE,
                "correct_feedback": "Genau, 4/4 = 1.",
                "incorrect_feedback": "Zähler addieren.",
                "translations": {"fr": FRENCH},
            },
            "2",
            "Additionne les numérateurs.",
        ),
        (
            {**EXERCISE, "correct_feedback": "Genau, 4/4 = 1.", "incorrect_feedback": "Zähler addieren."},
            "2",
            "Zähler addieren.",
        ),
        (EXERCISE, "1", message_catalog.text("practice.feedback.correct", "fr")),
        (EXERCISE, "2", message_catalog.text("practice.feedback.incorrect", "fr")),
    ],
    ids=[
        "translated feedback, right",
        "translated feedback, wrong",
        "untranslated feedback is the original",
        "no feedback: the French default, right",
        "no feedback: the French default, wrong",
    ],
)
def test_a_french_reader_gets_feedback_in_french_where_there_is_any(
    monkeypatch: pytest.MonkeyPatch, exercise: dict[str, Any], answer: str, expected: str
) -> None:
    recorded = _Writes(monkeypatch, [exercise])

    judgement = answer_recording.judge(exercise, answer, locale="fr")
    result = answer_recording.answer_practice("student-1", exercise, answer, locale="fr")

    assert judgement.feedback == expected
    assert result.feedback == expected
    assert recorded.by_kind["receipt"][0]["feedback"] == expected


def test_the_french_defaults_are_not_the_german_ones() -> None:
    assert message_catalog.text("practice.feedback.correct", "fr") != "Richtig!"
    assert message_catalog.text("practice.feedback.correct", "de") == "Richtig!"


def test_judging_and_feedback_read_the_same_localized_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    exercise = {**EXERCISE, "translations": {"fr": FRENCH}}
    _Writes(monkeypatch, [exercise])

    judgement = answer_recording.judge(exercise, "1", locale="fr")

    assert judgement.correct
    assert judgement.shown["prompt"] == "Calcule 1/4 + 3/4."
    assert judgement.feedback == judgement.shown["correct_feedback"]
    # The stored row is never changed.
    assert exercise["prompt"] == "Berechne 1/4 + 3/4."
    assert "correct_feedback" not in exercise
