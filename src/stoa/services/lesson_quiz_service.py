"""The short quiz that completes a lesson without answering every exercise.

The rules start from the frontend's (`stoa-frontend/src/features/chapter/quiz.ts`),
but this is the authority: the backend draws the exercises, judges every answer
and signs the credential `complete_lesson` accepts (#92). Nothing a quiz answer
does counts as "answered right" for lighting a knowledge point (#9) - passing a
quiz completes the lesson and nothing more.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from stoa.services import curriculum_service, knowledge_mastery_service

#: Wrong answers a quiz forgives; the next one loses it.
QUIZ_MAX_MISTAKES = 1
QUIZ_HEARTS = QUIZ_MAX_MISTAKES + 1
#: Exercises already answered right that a skip quiz adds, at least.
QUIZ_REVIEW_EXTRA = 2
#: The fewest exercises a skip quiz has, when the lesson has that many.
QUIZ_MIN_SIZE = 3
#: Exercises drawn to test out of a lesson from the chapter, at most.
QUIZ_TEST_OUT_SIZE = 5

#: How long an unfinished quiz stays answerable.
QUIZ_SESSION_TTL_SECONDS = 30 * 60
#: How long a passed quiz's credential stays usable.
QUIZ_CREDENTIAL_TTL_SECONDS = 10 * 60

SKIP_QUIZ = "skip"
TEST_OUT_QUIZ = "testOut"
QUIZ_KINDS = (SKIP_QUIZ, TEST_OUT_QUIZ)

IN_PROGRESS = "inProgress"
PASSED = "passed"
FAILED = "failed"


def _shuffled(items: Sequence[str], rng: random.Random) -> list[str]:
    drawn = list(items)
    rng.shuffle(drawn)
    return drawn


def _rng(rng: random.Random | None) -> random.Random:
    return rng if rng is not None else random.SystemRandom()


def compose_skip_quiz(
    skipped: Sequence[str],
    correct: Sequence[str],
    rng: random.Random | None = None,
) -> list[str]:
    """Every exercise still unanswered, topped up with review ones."""
    generator = _rng(rng)
    extra = min(len(correct), max(QUIZ_REVIEW_EXTRA, QUIZ_MIN_SIZE - len(skipped)))
    review = _shuffled(correct, generator)[:extra]
    return _shuffled([*skipped, *review], generator)


def compose_test_out_quiz(
    exercise_ids: Sequence[str],
    rng: random.Random | None = None,
) -> list[str]:
    """At most QUIZ_TEST_OUT_SIZE of the lesson's exercises, drawn at random."""
    return _shuffled(exercise_ids, _rng(rng))[:QUIZ_TEST_OUT_SIZE]


def compose_quiz(
    kind: str,
    *,
    exercise_ids: Sequence[str],
    answered_right: Collection[str],
    rng: random.Random | None = None,
) -> list[str]:
    if kind == TEST_OUT_QUIZ:
        return compose_test_out_quiz(exercise_ids, rng)
    skipped = [item for item in exercise_ids if item not in answered_right]
    correct = [item for item in exercise_ids if item in answered_right]
    return compose_skip_quiz(skipped, correct, rng)


def quiz_lost(mistakes: int) -> bool:
    return mistakes > QUIZ_MAX_MISTAKES


def hearts_left(mistakes: int) -> int:
    return max(QUIZ_HEARTS - mistakes, 0)


def judge_answer(submitted: Any, correct_answer: Any) -> bool:
    """Compare an answer the way the ordinary practice route does."""

    def normalized(value: Any) -> str:
        if isinstance(value, list):
            return "|".join(str(item).strip().lower() for item in value)
        return str(value).strip().lower()

    return normalized(submitted) == normalized(correct_answer)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def lesson_is_locked(student_id: str, lesson: Mapping[str, Any]) -> bool:
    """Whether the lesson sits in a knowledge point the student may not open yet.

    The judgement is `knowledge_mastery_service.unit_states`, which is the one
    place prerequisites are counted (#56). A lesson outside any unit, or a unit
    the catalog does not carry, is not locked: there is no stated relation to
    lock it, and the exercise gate still applies either way.

    A unit with no stated prerequisite can never be locked, so that case is
    settled from the prerequisite graph alone rather than by building the whole
    star map - which reads every lesson's exercises and every attempt - on each
    completion.
    """
    unit_id = str(lesson.get("unit_id") or "")
    if not unit_id:
        return False
    subject_id = str(lesson.get("subject_id") or "")
    if not curriculum_service.get_prerequisites(subject_id).get(unit_id):
        return False
    states = knowledge_mastery_service.unit_states(student_id, subject_id=subject_id or None)
    judged = states.get(unit_id)
    return judged is not None and judged.state is knowledge_mastery_service.LearningState.LOCKED
