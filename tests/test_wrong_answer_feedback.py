"""What a student is told after a wrong answer, by subject and by mistake (#565).

Every wrong answer used to get "Prüfe deinen Rechenweg" - in English vocabulary,
reading and physics concept questions, which have no working to check. Now an
exercise that brings no feedback of its own gets, in this order: the line of
the error-cause rule that explains the answer (the sign, a close number, a
fraction not reduced), else the calculation line when its key holds a digit,
else a line that fits any subject. A distractor's misconception is written
about the student for a teacher, so it stays off the student's feedback.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.services import (
    answer_recording,
    error_causes,
    message_catalog,
    practice_projection_service,
)
from test_answer_recording import _Writes
from test_error_causes import CHOICE, DENOMINATORS

TYPED: dict[str, Any] = {
    "challenge_id": "exercise-7",
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "brueche",
    "unit_id": "brueche-u1",
    "type": "text_input",
    "prompt": "Berechne 48/72 und kürze vollständig.",
    "correct_answer": "2/3",
    "explanation": "48/72 = 2/3.",
}
VOCABULARY: dict[str, Any] = {
    "challenge_id": "exercise-8",
    "lesson_id": "lesson-2",
    "subject_id": "english",
    "topic_id": "fruit",
    "unit_id": "fruit-u1",
    "type": "text_input",
    "prompt": "Translate: der Apfel",
    "correct_answer": "the apple",
    "explanation": "Apfel = apple.",
}
CONCEPT: dict[str, Any] = {
    "challenge_id": "exercise-9",
    "lesson_id": "lesson-3",
    "subject_id": "physics",
    "topic_id": "kraefte",
    "unit_id": "kraefte-u1",
    "type": "multiple_choice",
    "prompt": "Was passiert mit der Gewichtskraft auf dem Mond?",
    "options": ["Sie wird kleiner.", "Sie bleibt gleich.", "Sie wird grösser."],
    "correct_answer": "Sie wird kleiner.",
    "explanation": "Der Mond zieht schwächer an.",
}
UNREDUCED = error_causes.rule_cause(error_causes.RULE_UNREDUCED)
CALCULATION_WORDS = ("Rechenweg", "working", "raisonnement", "procedimento")


def _feedback(key: str, locale: str = "de") -> str:
    return message_catalog.text(key, locale)


# ── the rule for a fraction not reduced ──────────────────────────────────────


@pytest.mark.parametrize(
    ("answer", "keys"),
    [
        ("48/72", ["2/3"]),
        ("4/6", ["2/3"]),
        ("4 / 6", ["2/3"]),
        ("x = 4/6", ["x = 2/3"]),
        ("-4/6", ["-2/3"]),
        ("x = -10/4", ["x = -5/2"]),
        ("6/2", ["3"]),
        ("2/4", ["0.5", "1/2"]),
    ],
)
def test_the_key_value_as_a_fraction_not_reduced(answer: str, keys: list[str]) -> None:
    assert error_causes.rule_of(answer, keys) == error_causes.RULE_UNREDUCED
    assert error_causes.infer(answer, keys) == UNREDUCED


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        # Another value.
        ("4/6", "3/4"),
        ("-4/6", "2/3"),
        # The key itself is not reduced: the author wants that form.
        ("8/12", "4/6"),
        # A decimal key asks for a decimal, not for a reduced fraction.
        ("2/4", "0.5"),
        # Not the same text around the fraction.
        ("4/6", "x = 2/3"),
        ("4/6 m", "2/3"),
        # Reduced already, only written differently: nothing to reduce.
        ("2/3", "4/6"),
        # Several numbers, a mixed number, no fraction, a zero denominator.
        ("4/6; 2/3", "2/3"),
        ("1 2/4", "1 1/2"),
        ("vier Sechstel", "2/3"),
        ("4/0", "2/3"),
    ],
)
def test_anything_else_is_not_a_fraction_left_unreduced(answer: str, key: str) -> None:
    assert error_causes.rule_of(answer, [key]) is None


def test_a_choice_exercise_has_no_typed_rule() -> None:
    choice = {**TYPED, "type": "multiple_choice", "options": ["2/3", "4/6", "1/3"]}

    assert error_causes.typed_rule(choice, choice, "4/6") is None
    assert error_causes.typed_rule(TYPED, TYPED, "4/6") == error_causes.RULE_UNREDUCED


# ── the catalog ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rule", error_causes.RULES)
def test_every_rule_has_a_line_for_the_student_in_every_locale(rule: str) -> None:
    lines = message_catalog.TEXT[f"practice.feedback.{rule}"]

    assert set(lines) == set(error_causes.LOCALES)
    assert all(text.strip() for text in lines.values())
    # The student's line is not the teacher's sentence about the student.
    assert lines["de"] != error_causes.rule_cause(rule)["misconception"]["de"]


@pytest.mark.parametrize("locale", error_causes.LOCALES)
def test_the_line_for_any_subject_names_no_calculation(locale: str) -> None:
    line = _feedback("practice.feedback.incorrect", locale)

    assert not any(word in line for word in CALCULATION_WORDS)
    assert line != _feedback("practice.feedback.incorrect_calculation", locale)


# ── what a wrong answer is told ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exercise", "answer", "key"),
    [
        (TYPED, "48/72", "practice.feedback.unreduced"),
        (
            {**TYPED, "prompt": "Löse 3x + 12 = -3.", "correct_answer": "x = -5"},
            "x = 5",
            "practice.feedback.sign",
        ),
        (
            {**TYPED, "type": "numeric", "prompt": "Berechne 7 · 8.", "correct_answer": "56"},
            "57",
            "practice.feedback.close",
        ),
        (TYPED, "1/3", "practice.feedback.incorrect_calculation"),
        (VOCABULARY, "the pear", "practice.feedback.incorrect"),
        (CONCEPT, "Sie bleibt gleich.", "practice.feedback.incorrect"),
    ],
    ids=["unreduced", "sign", "close", "far off", "vocabulary", "physics concept"],
)
@pytest.mark.parametrize("locale", ["de", "en"])
def test_a_wrong_answer_is_told_what_fits_it(
    monkeypatch: pytest.MonkeyPatch,
    exercise: dict[str, Any],
    answer: str,
    key: str,
    locale: str,
) -> None:
    recorded = _Writes(monkeypatch, [exercise])

    judgement = answer_recording.judge(exercise, answer, locale=locale)
    result = answer_recording.answer_practice("student-1", exercise, answer, locale=locale)

    expected = _feedback(key, locale)
    assert judgement.feedback == expected
    assert result.feedback == expected
    [receipt] = recorded.by_kind["receipt"]
    assert receipt["feedback"] == receipt["incorrect_feedback"] == expected


@pytest.mark.parametrize("exercise", [VOCABULARY, CONCEPT], ids=["vocabulary", "physics concept"])
def test_no_calculation_words_outside_calculations(
    monkeypatch: pytest.MonkeyPatch, exercise: dict[str, Any]
) -> None:
    _Writes(monkeypatch, [exercise])

    for locale in error_causes.LOCALES:
        feedback = answer_recording.judge(exercise, "wrong", locale=locale).feedback
        assert not any(word in feedback for word in CALCULATION_WORDS)


def test_a_fraction_not_reduced_records_its_cause_for_the_teacher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _Writes(monkeypatch, [TYPED])

    answer_recording.answer_practice("student-1", TYPED, "48/72", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["error_cause"] == UNREDUCED


def test_the_exercise_own_wrong_feedback_still_wins_over_a_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exercise = {**TYPED, "incorrect_feedback": "Teile Zähler und Nenner durch 24."}
    recorded = _Writes(monkeypatch, [exercise])

    result = answer_recording.answer_practice("student-1", exercise, "48/72", locale="de")

    assert result.feedback == "Teile Zähler und Nenner durch 24."
    # The cause is recorded all the same.
    assert recorded.by_kind["receipt"][0]["error_cause"] == UNREDUCED


def test_a_tagged_distractor_keeps_its_misconception_off_the_student_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _Writes(monkeypatch, [CHOICE])

    result = answer_recording.answer_practice("student-1", CHOICE, "2/10", locale="de")

    assert result.feedback == _feedback("practice.feedback.incorrect_calculation")
    assert DENOMINATORS["de"] not in result.feedback
    assert recorded.by_kind["receipt"][0]["error_cause"]["misconception"]["de"] == DENOMINATORS["de"]


def test_a_right_answer_is_still_told_it_is_right(monkeypatch: pytest.MonkeyPatch) -> None:
    _Writes(monkeypatch, [VOCABULARY])

    judgement = answer_recording.judge(VOCABULARY, "The apple", locale="en")

    assert judgement.correct
    assert judgement.feedback == _feedback("practice.feedback.correct", "en")


def test_the_privileged_preview_shows_the_default_for_the_kind_of_answer() -> None:
    concept = practice_projection_service.build_privileged_answer(CONCEPT)
    calculation = practice_projection_service.build_privileged_answer(TYPED)

    assert concept.incorrect_feedback == _feedback("practice.feedback.incorrect")
    assert calculation.incorrect_feedback == _feedback("practice.feedback.incorrect_calculation")
