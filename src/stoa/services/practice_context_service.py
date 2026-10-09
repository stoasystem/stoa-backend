"""The exercise a question was asked beside, resolved from ids alone (#61).

The client sends three ids and nothing else. Every word the model is later told
about the exercise is looked up here: the wording of the question, the lesson
and chapter it sits in, the knowledge point's learning state, its recommendation
and its due-review count, and the student's own recent wrong answers on it. An
id that does not exist, does not line up with the other two, or names content
this student cannot see is refused, and the route turns that into a 422.

The judgement itself is not re-implemented. The learning state comes from
`knowledge_mastery_service`, the due-review count and the recommendation rule
from `knowledge_map_service`: a second copy of either would drift from the star
map, and the student would read one answer on the map and another in the chat.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.services import (
    curriculum_service,
    knowledge_map_service,
    knowledge_mastery_service,
    practice_projection_service,
)

SCHEMA_VERSION = "practice-context.v1"

# Three, not more. Each one carries a question and the answer the student gave,
# so the block grows fast against a prompt that already holds six turns of
# history and possibly an attachment; and what the assistant needs is the shape of
# the recent mistakes, not a transcript of every one. Three fits two or three
# lines per mistake inside the bound below with room to spare.
RECENT_MISTAKE_LIMIT = 3

_MAX_PROMPT_CHARS = 400
_MAX_ANSWER_CHARS = 200


class PracticeContextUnresolved(Exception):
    """The three ids name nothing this student may be shown."""


def resolve(
    student_id: str,
    *,
    challenge_id: str,
    lesson_id: str,
    unit_id: str,
    locale: str = "de",
) -> dict[str, Any]:
    """Everything the assistant is told about this exercise, read from the store."""
    if not _all_named(challenge_id, lesson_id, unit_id):
        raise PracticeContextUnresolved("practice context ids are incomplete")

    challenge = practice_repo.get_challenge(challenge_id)
    if not isinstance(challenge, Mapping):
        raise PracticeContextUnresolved("no such exercise")
    if practice_projection_service.content_state(challenge) not in curriculum_service.VISIBLE_STATES:
        raise PracticeContextUnresolved("exercise is not visible to this student")
    if str(challenge.get("lesson_id") or "") != lesson_id:
        raise PracticeContextUnresolved("exercise does not belong to that lesson")

    catalog = curriculum_service.list_catalog(locale=locale)
    lessons = _rows(catalog, "lessons")
    lesson = _by_id(lessons, lesson_id)
    if lesson is None or str(lesson.get("unitId") or "") != unit_id:
        raise PracticeContextUnresolved("lesson does not belong to that knowledge point")
    unit = _by_id(_rows(catalog, "units"), unit_id)
    if unit is None:
        raise PracticeContextUnresolved("no such knowledge point")
    topic = _by_id(_rows(catalog, "topics"), str(unit.get("topicId") or ""))

    states = knowledge_mastery_service.unit_states(
        student_id, locale=locale, catalog=catalog
    )
    judged = states.get(unit_id)
    if judged is None:
        raise PracticeContextUnresolved("no such knowledge point")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "challengeId": challenge_id,
        "lessonId": lesson_id,
        "unitId": unit_id,
        "subjectId": str(unit.get("subjectId") or ""),
        "challengeType": str(challenge.get("type") or "text_input"),
        "challengePrompt": _bounded(challenge.get("prompt"), _MAX_PROMPT_CHARS),
        "lessonTitle": _bounded(lesson.get("title"), _MAX_PROMPT_CHARS),
        "unitTitle": _bounded(unit.get("title"), _MAX_PROMPT_CHARS),
        "topicId": str(unit.get("topicId") or ""),
        "topicTitle": _bounded((topic or {}).get("title"), _MAX_PROMPT_CHARS),
        "state": judged.state.value,
        "recommendation": _recommendation(unit_id, catalog, states),
        "reviewDue": _review_due(student_id, lessons, unit_id),
        "recentMistakes": _recent_mistakes(student_id, unit_id, lessons),
    }


def _all_named(*values: str) -> bool:
    return all(isinstance(value, str) and value.strip() for value in values)


def _rows(catalog: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    return [item for item in catalog.get(key) or () if isinstance(item, Mapping)]


def _by_id(rows: Sequence[Mapping[str, Any]], row_id: str) -> Mapping[str, Any] | None:
    for row in rows:
        if str(row.get("id") or "") == row_id:
            return row
    return None


def _bounded(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _review_due(student_id: str, lessons: Sequence[Mapping[str, Any]], unit_id: str) -> int:
    """How many review cards are due on this knowledge point. A count, not a flag.

    Zero and "nothing due" are the same answer; one due card and nine are not,
    and an assistant that cannot tell them apart gives the same nudge either way.
    """
    counts = knowledge_map_service._review_due_by_unit(student_id, lessons)
    return int(counts.get(unit_id, 0))


def _recommendation(
    unit_id: str,
    catalog: Mapping[str, Any],
    states: Mapping[str, knowledge_mastery_service.UnitMastery],
) -> dict[str, str] | None:
    """Whether the star map would point the student here, decided its way.

    Separate from the learning state on purpose: `in_progress` is a fact about
    this knowledge point, being recommended is a fact about it among all the
    others in its subject.
    """
    units = _rows(catalog, "units")
    unit = _by_id(units, unit_id)
    if unit is None:
        return None
    subject_id = str(unit.get("subjectId") or "")
    chapter_order = {
        str(topic.get("id") or ""): index
        for index, topic in enumerate(
            sorted(
                _rows(catalog, "topics"),
                key=lambda item: (
                    str(item.get("subjectId") or ""),
                    int(item.get("order") or 0),
                    str(item.get("id") or ""),
                ),
            )
        )
    }
    stars = [
        {"unitId": str(item.get("id") or ""), "state": judged.state.value}
        for item in sorted(
            units,
            key=lambda item: (
                chapter_order.get(str(item.get("topicId") or ""), len(chapter_order)),
                int(item.get("order") or 0),
                str(item.get("id") or ""),
            ),
        )
        if str(item.get("subjectId") or "") == subject_id
        and (judged := states.get(str(item.get("id") or ""))) is not None
        and judged.lesson_count > 0
    ]
    if knowledge_map_service._recommended_unit(stars) != unit_id:
        return None
    return {"source": "system"}


def _recent_mistakes(
    student_id: str, unit_id: str, lessons: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """This student's last wrong answers on this knowledge point, newest first.

    Only answers the backend judged. A self-reported one was never checked, and
    #93 already keeps those out of what a knowledge point is judged on.
    """
    lesson_ids = {
        str(lesson.get("id") or "")
        for lesson in lessons
        if str(lesson.get("unitId") or "") == unit_id
    }
    mine = [
        attempt
        for attempt in practice_repo.get_mistakes(student_id)
        if isinstance(attempt, Mapping)
        and not attempt.get("self_reported")
        and (
            str(attempt.get("unit_id") or "") == unit_id
            or (
                not attempt.get("unit_id")
                and str(attempt.get("lesson_id") or "") in lesson_ids
            )
        )
    ]
    mine.sort(
        key=lambda attempt: (
            str(attempt.get("created_at") or ""),
            str(attempt.get("attempt_id") or ""),
        ),
        reverse=True,
    )
    return [
        {
            "challengeId": str(attempt.get("challenge_id") or ""),
            "prompt": _bounded(attempt.get("prompt"), _MAX_PROMPT_CHARS),
            "studentAnswer": _answer_text(attempt),
            "createdAt": str(attempt.get("created_at") or ""),
        }
        for attempt in mine[:RECENT_MISTAKE_LIMIT]
    ]


def _answer_text(attempt: Mapping[str, Any]) -> str:
    answer = attempt.get("submitted_answer", attempt.get("student_answer"))
    if isinstance(answer, list):
        answer = ", ".join(str(item) for item in answer)
    return _bounded(answer, _MAX_ANSWER_CHARS)
