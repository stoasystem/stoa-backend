"""The pure rules of both quizzes: what a paper asks, and where it stands.

Nothing here reads or writes. `stoa.services.quiz` keeps the paper row and
carries out what passing and losing do; this module only says which exercises
a new paper asks and, given the paper's order and its answer log, what it asks
next and whether it is over.

The two kinds differ in two rules and nothing else here:

* **lesson quiz** (#92): a wrong answer sends its exercise to the back of the
  queue and costs a heart; the paper is passed once the queue is empty.
* **star quiz** (#165, stoa-frontend#475): every exercise is asked once, in the
  paper's order; the paper is passed once every exercise has been answered.

Both forgive one wrong answer; the second loses the paper.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

IN_PROGRESS = "inProgress"
PASSED = "passed"
FAILED = "failed"

#: Wrong answers a paper forgives; the next one loses it. Both kinds.
MAX_MISTAKES = 1
#: How long an unfinished paper stays answerable. Both kinds.
PAPER_TTL = timedelta(minutes=30)

# ── lesson quiz ─────────────────────────────────────────────────────────────

SKIP_QUIZ = "skip"
TEST_OUT_QUIZ = "testOut"
LESSON_QUIZ_KINDS = (SKIP_QUIZ, TEST_OUT_QUIZ)

LESSON_QUIZ_HEARTS = MAX_MISTAKES + 1
#: Exercises already answered right that a skip quiz adds, at least.
QUIZ_REVIEW_EXTRA = 2
#: The fewest exercises a skip quiz has, when the lesson has that many.
QUIZ_MIN_SIZE = 3
#: Exercises drawn to test out of a lesson from the chapter, at most.
QUIZ_TEST_OUT_SIZE = 5
#: How long a passed lesson quiz's credential stays usable.
CREDENTIAL_TTL = timedelta(minutes=10)

# ── star quiz ───────────────────────────────────────────────────────────────

STAR_QUIZ = "star"
#: How many exercises a star paper asks, when the star has that many.
STAR_MIN_SIZE = 6
STAR_MAX_SIZE = 10
#: How long after a lost star quiz the same star can be taken again.
COOLDOWN = timedelta(hours=24)


def new_token() -> str:
    """A quiz id or a credential: unguessable, and only ever looked up in the owner's partition."""
    return secrets.token_urlsafe(32)


def _rng(rng: random.Random | None) -> random.Random:
    return rng if rng is not None else random.SystemRandom()


def _shuffled(items: Sequence[str], rng: random.Random) -> list[str]:
    drawn = list(items)
    rng.shuffle(drawn)
    return drawn


# ── composing a paper ───────────────────────────────────────────────────────


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


def compose_lesson_quiz(
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


def compose_star_quiz(
    exercises_by_lesson: Sequence[Sequence[str]],
    rng: random.Random | None = None,
) -> list[str]:
    """The star paper: one exercise from every lesson that has one, topped up at random.

    `exercises_by_lesson` is the star's core lessons in course order, each with
    its active exercises. The paper keeps course order, so a student meets the
    point the way the chapter teaches it. A star with more than
    `STAR_MAX_SIZE` lessons asks one from each; every lesson is still
    represented.
    """
    generator = _rng(rng)
    lessons = [list(dict.fromkeys(ids)) for ids in exercises_by_lesson if ids]
    available = sum(len(ids) for ids in lessons)
    size = min(
        available,
        max(len(lessons), min(STAR_MAX_SIZE, max(STAR_MIN_SIZE, len(lessons)))),
    )
    chosen: list[set[str]] = [{generator.choice(ids)} for ids in lessons]
    rest = [
        (index, item)
        for index, ids in enumerate(lessons)
        for item in ids
        if item not in chosen[index]
    ]
    generator.shuffle(rest)
    for index, item in rest[: max(size - len(lessons), 0)]:
        chosen[index].add(item)
    return [item for index, ids in enumerate(lessons) for item in ids if item in chosen[index]]


# ── where a paper stands ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Standing:
    """A paper after the answers in its log, in order."""

    status: str
    mistakes: int
    #: Exercises still to be asked, the one asked now first; empty once over.
    remaining: tuple[str, ...]


def _logged(answers: Sequence[Mapping[str, object]]) -> list[tuple[str, bool]]:
    return [(str(answer.get("exerciseId") or ""), bool(answer.get("correct"))) for answer in answers]


def _decided(mistakes: int, remaining: Sequence[str]) -> Standing:
    if mistakes > MAX_MISTAKES:
        return Standing(FAILED, mistakes, ())
    if not remaining:
        return Standing(PASSED, mistakes, ())
    return Standing(IN_PROGRESS, mistakes, tuple(remaining))


def lesson_standing(
    order: Sequence[str],
    answers: Sequence[Mapping[str, object]],
    dropped: Collection[str] = (),
) -> Standing:
    """Lesson rule: a wrong answer goes to the back of the queue and costs a heart."""
    gone = set(dropped)
    queue = [item for item in order if item not in gone]
    mistakes = 0
    for exercise_id, correct in _logged(answers):
        if exercise_id in queue:
            queue.remove(exercise_id)
        if not correct:
            mistakes += 1
            if mistakes > MAX_MISTAKES:
                return Standing(FAILED, mistakes, ())
            if exercise_id not in gone:
                queue.append(exercise_id)
    return _decided(mistakes, queue)


def star_standing(
    order: Sequence[str],
    answers: Sequence[Mapping[str, object]],
    dropped: Collection[str] = (),
) -> Standing:
    """Star rule: every exercise once, in the paper's order."""
    logged = _logged(answers)
    answered = {exercise_id for exercise_id, _ in logged}
    gone = set(dropped)
    mistakes = sum(1 for _, correct in logged if not correct)
    return _decided(
        mistakes, [item for item in order if item not in answered and item not in gone]
    )


def hearts_left(mistakes: int) -> int:
    return max(LESSON_QUIZ_HEARTS - mistakes, 0)
