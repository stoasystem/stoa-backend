"""Per-unit learning state: what the star map draws a knowledge point as.

The judgement is the one decided in stoasystem/stoa-frontend#9: a unit is
**lit** when every one of its active lessons is completed *and* every exercise
under those lessons has been answered right at least once. Completing the
lessons is not enough on its own - a student can finish a lesson with a wrong
answer, and a unit that lit on lesson completion alone would claim knowledge
the evidence does not support.

**The `state` here is still derived, not persisted.** This judges from the
content as it stands, so adding an active lesson to a unit a student has
already lit - or turning an archived one back on - drops that unit back to
`in_progress` and takes a point off their subject's count. What #71 persists is
the *lighting fact* beside it (`LitFact`): once a unit has lit, `litAt` and
`litAtSource` stay, so the first lighting can be celebrated exactly once even
though the drawn state may move again.

The states are ordered: lit > in_progress > ready > locked. `locked` needs a
prerequisite that is not lit yet; until stoa-backend#56 stores prerequisites,
nothing is locked, which is what #9 point 7 asks for ("no prerequisite edge,
no lock").

The core here is a pure function over facts the caller has already read. That
is deliberate: this service is the shared one (#57) behind the read model
(#59) and anything else that needs the same judgement, and a pure core can be
tested without standing up a table double. Eight defects in this repository
have come from doubles that were more permissive than DynamoDB; the ones that
never need a double cannot join them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.services import curriculum_service, practice_projection_service


class LearningState(StrEnum):
    """The four states a knowledge point is drawn in (#9 point 3)."""

    LIT = "lit"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    LOCKED = "locked"


class LitSource(StrEnum):
    """Where a stored lighting came from (#9 point 3).

    `observed` means this lighting became true while the ledger was already
    open, so it is a real first lighting and may be celebrated. `backfilled`
    means it was already true when the ledger opened: history, not an event.
    """

    OBSERVED = "observed"
    BACKFILLED = "backfilled"


@dataclass(frozen=True, slots=True)
class LitFact:
    """One lighting, as it is kept for this student."""

    unit_id: str
    lit_at: str
    source: LitSource
    acknowledged: bool = False


def resolve_lit_facts(
    *,
    lit_unit_ids: Iterable[str],
    stored: Mapping[str, LitFact],
    ledger_open: bool,
    now: str,
) -> tuple[dict[str, LitFact], tuple[LitFact, ...]]:
    """Every lighting this student owns, and the ones first seen just now. Pure.

    A lighting already recorded keeps the time and the source it was written
    with: #9 says a lighting never goes out, and rewriting it would move the
    moment and bring a celebration back after it was confirmed.

    `ledger_open` is the whole distinction between the two sources. Before the
    ledger exists nothing can be known about when a unit lit, so everything
    already lit is `backfilled`; afterwards a lighting that was not there last
    time is one that happened since.
    """
    facts = dict(stored)
    fresh: list[LitFact] = []
    source = LitSource.OBSERVED if ledger_open else LitSource.BACKFILLED
    for unit_id in lit_unit_ids:
        if not unit_id or unit_id in facts:
            continue
        fact = LitFact(unit_id=unit_id, lit_at=now, source=source)
        facts[unit_id] = fact
        fresh.append(fact)
    return facts, tuple(fresh)


def unacknowledged_lit(
    facts: Mapping[str, LitFact], *, among: Iterable[str] | None = None
) -> tuple[str, ...]:
    """Lightings this student saw happen and has not confirmed yet. Pure.

    Only `observed` ones. A backfilled lighting is never in here, whatever the
    student has or has not confirmed, so an account that arrives with a hundred
    lit knowledge points gets no celebrations rather than a hundred.
    """
    visible = None if among is None else frozenset(among)
    chosen = [
        fact
        for fact in facts.values()
        if fact.source is LitSource.OBSERVED
        and not fact.acknowledged
        and (visible is None or fact.unit_id in visible)
    ]
    return tuple(fact.unit_id for fact in sorted(chosen, key=lambda f: (f.lit_at, f.unit_id)))


@dataclass(frozen=True, slots=True)
class NextLesson:
    lesson_id: str
    title: str


@dataclass(frozen=True, slots=True)
class UnitMastery:
    """One knowledge point, as the star map needs it."""

    unit_id: str
    topic_id: str
    subject_id: str
    state: LearningState
    #: Completed active lessons over active lessons, 0..1. 0 when there are none.
    progress: float
    #: Active exercises not yet answered right. 0 does not imply lit on its own.
    unmet_exercises: int
    lesson_count: int
    lessons_done: int
    next_lesson: NextLesson | None


def _lesson_exercise_ids(
    lessons: Sequence[Mapping[str, Any]],
    exercises_by_lesson: Mapping[str, Sequence[str]],
) -> list[str]:
    found: list[str] = []
    for lesson in lessons:
        found.extend(exercises_by_lesson.get(str(lesson.get("id") or ""), ()))
    return found


def judge_unit(
    *,
    unit: Mapping[str, Any],
    lessons: Sequence[Mapping[str, Any]],
    exercises_by_lesson: Mapping[str, Sequence[str]],
    completed_lesson_ids: frozenset[str],
    exercises_answered_right: frozenset[str],
    unlit_prerequisites: int = 0,
) -> UnitMastery:
    """One unit's state from facts already read. Pure; no I/O.

    `lessons` are the unit's **active** lessons only - the caller filters, the
    same way the student catalog does, so a draft or archived lesson can never
    hold a unit back or light it.
    """
    unit_id = str(unit.get("id") or "")
    lesson_count = len(lessons)
    done = [lesson for lesson in lessons if str(lesson.get("id") or "") in completed_lesson_ids]
    lessons_done = len(done)

    exercise_ids = _lesson_exercise_ids(lessons, exercises_by_lesson)
    unmet = [item for item in exercise_ids if item not in exercises_answered_right]

    every_lesson_done = lesson_count > 0 and lessons_done == lesson_count
    every_exercise_right = not unmet
    progress = (lessons_done / lesson_count) if lesson_count else 0.0

    if every_lesson_done and every_exercise_right:
        state = LearningState.LIT
    elif unlit_prerequisites > 0:
        # A prerequisite that is not lit keeps this one shut, but only while
        # the student has not already started it: taking a lock back after
        # somebody is inside it would strand their progress.
        state = (
            LearningState.IN_PROGRESS
            if lessons_done or len(unmet) < len(exercise_ids)
            else LearningState.LOCKED
        )
    elif lessons_done or len(unmet) < len(exercise_ids):
        state = LearningState.IN_PROGRESS
    else:
        state = LearningState.READY

    remaining = [lesson for lesson in lessons if str(lesson.get("id") or "") not in completed_lesson_ids]
    next_lesson = (
        NextLesson(str(remaining[0].get("id") or ""), str(remaining[0].get("title") or ""))
        if remaining
        else None
    )

    return UnitMastery(
        unit_id=unit_id,
        topic_id=str(unit.get("topicId") or ""),
        subject_id=str(unit.get("subjectId") or ""),
        state=state,
        progress=progress,
        unmet_exercises=len(unmet),
        lesson_count=lesson_count,
        lessons_done=lessons_done,
        next_lesson=next_lesson,
    )


def _completed_lesson_ids(student_id: str, subject_id: str | None) -> frozenset[str]:
    summary = curriculum_service.get_progress_summary(student_id, subject_id=subject_id)
    return frozenset(str(item) for item in summary.get("completedLessonIds") or () if item)


def _exercises_answered_right(student_id: str) -> frozenset[str]:
    """Every exercise this student has answered right at least once.

    Read once for the whole map rather than per unit: the same attempt list
    answers every knowledge point, and a per-unit read would turn one page of
    the star map into a request per knowledge point. Every page of it, too -
    a truncated read puts out stars the student earned, and does so more the
    more they practise.
    """
    return frozenset(practice_repo.all_challenges_answered_right(student_id))


def _active_exercise_ids(lesson_id: str) -> list[str]:
    return [
        str(challenge.get("challenge_id") or challenge.get("id") or "")
        for challenge in practice_repo.get_challenges(lesson_id)
        if practice_projection_service.content_state(challenge) != "archived"
    ]


def unit_states(
    student_id: str,
    *,
    subject_id: str | None = None,
    locale: str = "de",
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, UnitMastery]:
    """Every unit's state for one student, keyed by unit id.

    `catalog` lets a caller that has already built it - the read model does -
    pass it in rather than have it built a second time.
    """
    content = catalog if catalog is not None else curriculum_service.list_catalog(
        subject_id=subject_id, locale=locale
    )
    units = [unit for unit in content.get("units") or () if isinstance(unit, Mapping)]
    lessons = [lesson for lesson in content.get("lessons") or () if isinstance(lesson, Mapping)]

    lessons_by_unit: dict[str, list[Mapping[str, Any]]] = {}
    for lesson in lessons:
        lessons_by_unit.setdefault(str(lesson.get("unitId") or ""), []).append(lesson)

    exercises_by_lesson = {
        str(lesson.get("id") or ""): _active_exercise_ids(str(lesson.get("id") or ""))
        for lesson in lessons
    }

    completed = _completed_lesson_ids(student_id, subject_id)
    answered_right = _exercises_answered_right(student_id)

    return {
        str(unit.get("id") or ""): judge_unit(
            unit=unit,
            lessons=lessons_by_unit.get(str(unit.get("id") or ""), []),
            exercises_by_lesson=exercises_by_lesson,
            completed_lesson_ids=completed,
            exercises_answered_right=answered_right,
        )
        for unit in units
    }


def lit_unit_ids(states: Iterable[UnitMastery]) -> frozenset[str]:
    return frozenset(item.unit_id for item in states if item.state is LearningState.LIT)
