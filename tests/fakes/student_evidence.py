"""A student's evidence built from facts, for tests that judge rather than read (#214).

`evidence(...)` takes the facts a test is about - lessons finished, exercises
answered right, stars lit by quiz, study days, due cards - and turns them into
the rows the five student partitions would hold. The real
`student_evidence.StudentEvidence` then derives every fact from those rows the
way it does in production, so a test that says `answered_right={"c1"}` is
judged by the same rule a student is. Nothing here reaches a table: a lesson the
catalog holds and `exercises` does not name has no exercises.

`install(monkeypatch, *values)` makes `student_evidence.for_student` hand these
values to the code under test, by student id. A student none of them names gets
an empty evidence over the first value's content, so a second student in a test
reads as somebody who has done nothing rather than as a table read.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from stoa.db.repositories import practice_repo
from stoa.services import knowledge_mastery_service, student_evidence

#: When a fact made from an id alone happened, unless the test says.
DEFAULT_MOMENT = "2026-01-05T09:00:00+00:00"


class FactSource:
    """Rows for the five partitions, counted as they are read."""

    def __init__(self, partitions: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self.partitions = {name: [dict(row) for row in rows] for name, rows in partitions.items()}
        self.reads: list[str] = []

    def _read(self, name: str) -> list[dict[str, Any]]:
        self.reads.append(name)
        return [dict(row) for row in self.partitions.get(name, ())]

    def progress(self, student_id: str) -> list[dict[str, Any]]:
        return self._read("progress")

    def attempts(self, student_id: str) -> list[dict[str, Any]]:
        return self._read("attempts")

    def activity(self, student_id: str) -> list[dict[str, Any]]:
        return self._read("activity")

    def star_quiz_outcomes(self, student_id: str) -> list[dict[str, Any]]:
        return self._read("star_quiz_outcomes")

    def review_cards(self, student_id: str) -> list[dict[str, Any]]:
        return self._read("review_cards")


class FailingSource(FactSource):
    """Every read of the named partitions raises, as an unreachable table would."""

    def __init__(self, partitions: Mapping[str, Sequence[Mapping[str, Any]]], failing: Iterable[str]) -> None:
        super().__init__(partitions)
        self.failing = frozenset(failing)

    def _read(self, name: str) -> list[dict[str, Any]]:
        if name in self.failing:
            self.reads.append(name)
            raise RuntimeError(f"{name} unavailable")
        return super()._read(name)


def empty_catalog() -> dict[str, Any]:
    return {"subjects": [], "topics": [], "units": [], "lessons": []}


def _entries(exercises: Sequence[Any]) -> list[dict[str, Any]]:
    out = []
    for item in exercises:
        if isinstance(item, Mapping):
            out.append({"id": str(item["id"]), "skills": list(item.get("skills") or ()),
                        "knowledge_point": item.get("knowledge_point")})
        else:
            out.append({"id": str(item), "skills": [], "knowledge_point": None})
    return out


def content(
    *,
    catalog: Mapping[str, Any] | None = None,
    exercises: Mapping[str, Sequence[Any]] | None = None,
    locale: str = "de",
) -> student_evidence.Content:
    """The catalog and an index holding every one of its lessons.

    `exercises` names each lesson's exercises, as ids or as `{"id", "skills",
    "knowledge_point"}`; a lesson it leaves out has none.
    """
    catalog = dict(catalog) if catalog is not None else empty_catalog()
    indexed: dict[str, list[dict[str, Any]]] = {
        str(lesson.get("id") or ""): []
        for lesson in catalog.get("lessons") or ()
        if isinstance(lesson, Mapping)
    }
    for lesson_id, items in (exercises or {}).items():
        indexed[lesson_id] = _entries(items)
    return student_evidence.Content(locale=locale, catalog=catalog, indexed=indexed)


def _lesson_rows(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(lesson.get("id") or ""): lesson
        for lesson in catalog.get("lessons") or ()
        if isinstance(lesson, Mapping)
    }


def evidence(
    student_id: str = "student-1",
    *,
    catalog: Mapping[str, Any] | None = None,
    exercises: Mapping[str, Sequence[Any]] | None = None,
    locale: str = "de",
    completed: Iterable[str] = (),
    progress: Iterable[Mapping[str, Any]] = (),
    answered_right: Iterable[str] = (),
    attempts: Iterable[Mapping[str, Any]] = (),
    study_days: Iterable[str] = (),
    lit: Iterable[knowledge_mastery_service.LitFact | Mapping[str, Any]] = (),
    ledger_open: bool = False,
    star_quiz_passed: Iterable[str] = (),
    star_quiz_retry_at: Mapping[str, str] | None = None,
    review_due: Mapping[str, int] | None = None,
    cards: Iterable[Mapping[str, Any]] = (),
    now: datetime | None = None,
    failing: Iterable[str] = (),
) -> student_evidence.StudentEvidence:
    """One student's evidence from facts.

    `completed` are lesson ids finished at `DEFAULT_MOMENT`; `progress` adds
    progress rows as stored. `answered_right` are exercise ids answered right
    once; `attempts` adds attempt rows as stored (a wrong one is a mistake).
    `review_due` is a number of due cards per unit, on that unit's first lesson;
    `cards` adds card rows as stored. `failing` names partitions whose read
    raises (`progress`, `attempts`, `activity`, `star_quiz_outcomes`,
    `review_cards`).
    """
    moment = now or datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    built = content(catalog=catalog, exercises=exercises, locale=locale)
    lessons = _lesson_rows(built.catalog)

    progress_rows = [
        {
            "lesson_id": lesson_id,
            "unit_id": str(lessons.get(lesson_id, {}).get("unitId") or ""),
            "subject_id": str(lessons.get(lesson_id, {}).get("subjectId") or ""),
            "status": "completed",
            "completed_at": DEFAULT_MOMENT,
        }
        for lesson_id in completed
    ] + [dict(row) for row in progress]

    attempt_rows = [
        {
            "attempt_id": f"right-{index}",
            "challenge_id": exercise_id,
            "correct": True,
            "created_at": DEFAULT_MOMENT,
        }
        for index, exercise_id in enumerate(answered_right)
    ] + [dict(row) for row in attempts]

    activity_rows: list[dict[str, Any]] = [
        {"SK": f"{practice_repo.STUDY_DAY_PREFIX}{day}", "entity_type": "study_day", "day": day}
        for day in study_days
    ]
    if ledger_open:
        activity_rows.append({"SK": practice_repo.LIT_LEDGER_SK, "entity_type": "lit_ledger"})
    for fact in lit:
        if isinstance(fact, knowledge_mastery_service.LitFact):
            row = {
                "unit_id": fact.unit_id,
                "lit_at": fact.lit_at,
                "lit_at_source": fact.source.value,
                **({"acknowledged_at": fact.lit_at} if fact.acknowledged else {}),
            }
        else:
            row = dict(fact)
        activity_rows.append(
            {"SK": f"{practice_repo.LIT_UNIT_PREFIX}{row['unit_id']}", "entity_type": "lit_unit", **row}
        )

    outcome_rows: list[dict[str, Any]] = [
        {
            "SK": f"{practice_repo.STAR_QUIZ_PASS_PREFIX}{unit_id}",
            "entity_type": practice_repo.STAR_QUIZ_PASS_ENTITY,
            "unit_id": unit_id,
        }
        for unit_id in star_quiz_passed
    ] + [
        {
            "SK": f"{practice_repo.STAR_QUIZ_COOLDOWN_PREFIX}{unit_id}#q",
            "unit_id": unit_id,
            "retry_at": retry_at,
        }
        for unit_id, retry_at in (star_quiz_retry_at or {}).items()
    ]

    first_lesson: dict[str, str] = {}
    for lesson_id, lesson in lessons.items():
        first_lesson.setdefault(str(lesson.get("unitId") or ""), lesson_id)
    due_at = (moment - timedelta(days=1)).isoformat()
    card_rows = [
        {"challenge_id": f"{unit_id}-due-{index}", "lesson_id": first_lesson.get(unit_id, ""), "due_at": due_at}
        for unit_id, count in (review_due or {}).items()
        for index in range(count)
    ] + [dict(row) for row in cards]

    partitions = {
        "progress": progress_rows,
        "attempts": attempt_rows,
        "activity": activity_rows,
        "star_quiz_outcomes": outcome_rows,
        "review_cards": card_rows,
    }
    source = FailingSource(partitions, failing) if failing else FactSource(partitions)
    return student_evidence.StudentEvidence(student_id, content=built, source=source, now=moment)


def install(monkeypatch: pytest.MonkeyPatch, *values: student_evidence.StudentEvidence) -> list[str]:
    """Hand these values to `student_evidence.for_student`, by student id.

    Returns the ids asked for, in order, so a test can say who was read. A `now`
    the caller passes is honoured: the same facts, judged at that moment.
    """
    by_student = {value.student_id: value for value in values}
    asked: list[str] = []
    fallback_content = values[0].content if values else content()

    def for_student(
        student_id: str,
        *,
        locale: str = "de",
        content: student_evidence.Content | None = None,
        now: datetime | None = None,
    ) -> student_evidence.StudentEvidence:
        asked.append(student_id)
        known = by_student.get(student_id)
        if known is None:
            return student_evidence.StudentEvidence(
                student_id, content=fallback_content, source=FactSource({}), now=now
            )
        # A fresh value over the same rows, as each request gets its own.
        return student_evidence.StudentEvidence(
            student_id, content=known.content, source=known.source, now=now or known.now
        )

    monkeypatch.setattr(student_evidence, "for_student", for_student)
    return asked
