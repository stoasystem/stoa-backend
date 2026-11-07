"""What a student is told after an answer when the exercise brings no feedback.

Exercises that came through the curriculum workflow had no feedback fields - the
authoring conversion dropped them - and the answer route fell back to English:
"Correct." under a German exercise, in a German-language app. The default then
became German for every reader; it is now the catalog's, in the reader's
language (#128), and authors can write feedback per exercise.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable
from stoa.db.repositories import practice_repo
from stoa.routers import practice
from stoa.services import (
    answer_recording,
    curriculum_analytics_service,
    message_catalog,
    practice_projection_service,
)
from test_curriculum_publish_projection import (
    LESSON_ID,
    _exercise,
    _payload,
    _publish,
    install_seeded_table,
)


def _answer(
    monkeypatch: pytest.MonkeyPatch, challenge: dict[str, Any], answer: str
) -> dict[str, Any]:
    recorded: list[dict[str, Any]] = []
    repo = curriculum_analytics_service.curriculum_analytics_repo
    monkeypatch.setattr(repo, "record_student_signal", lambda item, **_kwargs: None)
    monkeypatch.setattr(repo, "increment_metric", lambda item: None)
    monkeypatch.setattr(answer_recording, "record_practice_usage", lambda **_kwargs: None)
    monkeypatch.setattr(
        practice.practice_repo, "get_challenge", lambda challenge_id: dict(challenge)
    )
    monkeypatch.setattr(
        practice.practice_repo, "get_challenges", lambda lesson_id: [dict(challenge)]
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "put_attempt",
        lambda *args, **kwargs: (
            recorded.append(kwargs)
            or {
                "attempt_id": "attempt-1",
                "student_id": args[0],
                "challenge_id": args[1],
                "student_answer": args[2],
                "correct": args[3],
                **kwargs,
            }
        ),
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    response = TestClient(app).post(
        f"/practice/challenges/{challenge['challenge_id']}/answer", json={"answer": answer}
    )
    assert response.status_code == 200
    return recorded[0]


CHALLENGE = {
    "challenge_id": "exercise-1",
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "brueche",
    "prompt": "Berechne $\\frac{1}{4} + \\frac{3}{4}$.",
    "correct_answer": "1",
    "explanation": "$\\frac{4}{4} = 1$.",
}


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("1", message_catalog.text("practice.feedback.correct", "de")),
        ("2", message_catalog.text("practice.feedback.incorrect", "de")),
    ],
)
def test_an_exercise_without_feedback_answers_in_german(
    monkeypatch: pytest.MonkeyPatch, answer: str, expected: str
) -> None:
    attempt = _answer(monkeypatch, CHALLENGE, answer)

    assert attempt["feedback"] == expected
    assert "Correct" not in attempt["correct_feedback"]
    assert "Review" not in attempt["incorrect_feedback"]


def test_the_exercise_own_feedback_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt = _answer(monkeypatch, {**CHALLENGE, "correct_feedback": "Genau, 4/4 = 1."}, "1")

    assert attempt["feedback"] == "Genau, 4/4 = 1."


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def test_authored_feedback_reaches_the_runtime_row_and_blank_feedback_does_not(
    table: FakeTable,
) -> None:
    _publish(
        _payload(
            _exercise(1, correctFeedback=" Genau, 4/4 = 1. ", incorrectFeedback="  "),
            _exercise(3),
        )
    )

    first = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    second = practice_repo.get_challenge(f"{LESSON_ID}-q03")
    assert first is not None and second is not None
    assert first["correct_feedback"] == "Genau, 4/4 = 1."
    assert "incorrect_feedback" not in first
    assert practice_projection_service.answer_feedback(first, "de") == (
        "Genau, 4/4 = 1.",
        message_catalog.text("practice.feedback.incorrect", "de"),
    )
    assert "correct_feedback" not in second


def test_a_translated_feedback_reaches_the_runtime_row(table: FakeTable) -> None:
    _publish(
        _payload(
            _exercise(
                1,
                correctFeedback="Genau, 4/4 = 1.",
                translations={
                    "fr": {
                        "prompt": "Calcule 1/4 + 3/4.",
                        "correctAnswer": "1",
                        "correctFeedback": " Exactement, 4/4 = 1. ",
                        "incorrectFeedback": "Additionne les numérateurs.",
                    }
                },
            ),
            _exercise(3),
        )
    )

    stored = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert stored is not None
    assert stored["translations"]["fr"]["correct_feedback"] == "Exactement, 4/4 = 1."
    assert stored["translations"]["fr"]["incorrect_feedback"] == "Additionne les numérateurs."


def test_the_privileged_preview_keeps_the_stored_language() -> None:
    preview = practice_projection_service.build_privileged_answer(
        {**CHALLENGE, "translations": {"fr": {"prompt": "Calcule.", "correct_feedback": "Exact."}}}
    )

    assert preview.correct_feedback == message_catalog.text("practice.feedback.correct", "de")
    assert preview.incorrect_feedback == message_catalog.text("practice.feedback.incorrect", "de")
