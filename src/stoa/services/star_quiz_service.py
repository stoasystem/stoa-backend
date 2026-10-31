"""The star quiz: one paper that lights a whole knowledge point (#165).

Decided in stoa-frontend#475: a knowledge point is lit when every core lesson
is completed and every exercise under them has been answered right, **or**
when the student passes this quiz. It is for a student who already knows the
point, so the map catches up with what they can do.

- Every star not lit yet can be taken, in progress or not, with its
  prerequisites lit or not. Passing lights this star and nothing else.
- The paper draws at least one exercise from every core lesson that has one,
  6 to 10 in all (fewer only when the star has fewer), each asked once.
  A second wrong answer loses it.
- Lost: the same star can be taken again 24 hours later. A lost quiz is as if
  it had not been taken - no evidence, no review card.
- Passed: the lighting is recorded with the source `quiz`, and every answer of
  the paper is scheduled for review exactly as an ordinary answer would be,
  right or wrong. The lessons stay as they are.

The lesson quiz (`lesson_quiz_service`) is a different thing and is unchanged.
This module holds the rules; the route reads and writes the rows.
"""

from __future__ import annotations

import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

#: Wrong answers a star quiz forgives; the next one loses it.
MAX_MISTAKES = 1
#: How many exercises a paper asks, when the star has that many.
MIN_SIZE = 6
MAX_SIZE = 10
#: How long after a lost quiz the same star can be taken again.
COOLDOWN = timedelta(hours=24)
#: How long one paper stays open.
SESSION_TTL = timedelta(minutes=30)

IN_PROGRESS = "inProgress"
PASSED = "passed"
FAILED = "failed"


def new_quiz_id() -> str:
    return secrets.token_urlsafe(24)


def compose(
    exercises_by_lesson: Sequence[Sequence[str]],
    rng: random.Random | None = None,
) -> list[str]:
    """The paper: one exercise from every lesson that has one, topped up at random.

    `exercises_by_lesson` is the star's core lessons in course order, each with
    its active exercises. The paper keeps course order, so a student meets the
    point the way the chapter teaches it. A star with more than `MAX_SIZE`
    lessons asks one from each; every lesson is still represented.
    """
    generator = rng if rng is not None else random.SystemRandom()
    lessons = [list(dict.fromkeys(ids)) for ids in exercises_by_lesson if ids]
    available = sum(len(ids) for ids in lessons)
    size = min(available, max(len(lessons), min(MAX_SIZE, max(MIN_SIZE, len(lessons)))))
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


@dataclass(frozen=True, slots=True)
class Outcome:
    status: str
    mistakes: int
    #: Exercises still to be asked, in order; empty once the paper is over.
    remaining: tuple[str, ...]


def after_answer(*, paper: Sequence[str], answers: Sequence[bool]) -> Outcome:
    """Where a paper stands once `answers` have been given, in order. Pure."""
    mistakes = sum(1 for correct in answers if not correct)
    remaining = tuple(paper[len(answers):])
    if mistakes > MAX_MISTAKES:
        return Outcome(FAILED, mistakes, ())
    if not remaining:
        return Outcome(PASSED, mistakes, ())
    return Outcome(IN_PROGRESS, mistakes, remaining)


def retry_at(lost_at: datetime) -> datetime:
    return lost_at + COOLDOWN


def cooling_down(retry: str | None, now: datetime) -> bool:
    """Whether a star lost at some point still cannot be taken at `now`."""
    if not retry:
        return False
    try:
        moment = datetime.fromisoformat(retry)
    except ValueError:
        return False
    return now < moment


def retry_times(rows: Sequence[Mapping[str, object]], now: datetime) -> dict[str, str]:
    """Per unit, when a lost star can be taken again; only the ones not yet open."""
    return {
        str(row.get("unit_id") or ""): str(row.get("retry_at") or "")
        for row in rows
        if row.get("unit_id") and cooling_down(str(row.get("retry_at") or ""), now)
    }
