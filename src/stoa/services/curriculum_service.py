"""Curriculum catalog projections built from existing practice content."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.services import practice_projection_service

SUPPORTED_SUBJECTS = {"math", "physics", "german", "english"}
VISIBLE_STATES = {"active"}
PREVIEW_ROLES = {"admin", "teacher"}


def list_catalog(
    *,
    subject_id: str | None = None,
    grade_level: str | None = None,
    rollout_state: str | None = None,
    include_preview: bool = False,
) -> dict[str, Any]:
    subjects = [
        _build_subject(subject)
        for subject in sorted(practice_repo.get_subjects(), key=lambda item: _as_int(item.get("order", 0)))
        if _subject_matches(subject, subject_id, grade_level)
        and _matches_state(subject, rollout_state, include_preview)
        and _normal_subject_id(subject.get("subject_id", "")) in SUPPORTED_SUBJECTS
    ]
    topics = [
        _build_topic(topic)
        for topic in sorted(practice_repo.get_topics(subject_id), key=lambda item: _as_int(item.get("order", 0)))
        if _topic_matches(topic, subject_id, grade_level) and _matches_state(topic, rollout_state, include_preview)
    ]
    units = [
        _build_unit(unit)
        for unit in sorted(_all_units(topics), key=lambda item: (_normal_subject_id(item.get("subject_id", "")), item.get("topic_id", ""), _as_int(item.get("order", 0))))
        if _matches_state(unit, rollout_state, include_preview)
    ]
    lessons = [
        _build_lesson(lesson, exercise_count=len(_active_exercises_for_lesson(lesson["lesson_id"], include_preview)))
        for lesson in sorted(practice_repo.get_lessons(), key=lambda item: (item.get("topic_id", ""), item.get("unit_id", ""), _as_int(item.get("order", 0))))
        if _lesson_matches(lesson, subject_id, grade_level) and _matches_state(lesson, rollout_state, include_preview)
    ]

    return {
        "subjects": subjects,
        "topics": topics,
        "units": units,
        "lessons": lessons,
        "rolloutSubjects": sorted(SUPPORTED_SUBJECTS),
        "includePreview": include_preview,
        "source": "practice_backfill",
    }


def get_lesson_detail(
    lesson_id: str,
    *,
    include_preview: bool = False,
) -> dict[str, Any] | None:
    lesson = practice_repo.get_lesson(lesson_id)
    if not lesson or not _is_visible(lesson, include_preview):
        return None

    exercises = [
        practice_projection_service.build_exercise_preview(exercise)
        for exercise in _active_exercises_for_lesson(lesson_id, include_preview)
    ]
    return practice_projection_service.build_curriculum_lesson_preview(lesson, exercises)


def list_exercises(
    *,
    lesson_id: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
    difficulty: str | None = None,
    rollout_state: str | None = None,
    include_preview: bool = False,
) -> dict[str, Any]:
    raw_items = practice_repo.get_all_challenges(lesson_id=lesson_id, subject_id=subject_id, topic_id=topic_id)
    items = [
        practice_projection_service.build_exercise_preview(item)
        for item in sorted(raw_items, key=lambda challenge: (challenge.get("lesson_id", ""), _as_int(challenge.get("order", 0))))
        if _matches_state(item, rollout_state, include_preview)
        and (difficulty is None or str(item.get("difficulty", "")).lower() == difficulty.lower())
    ]
    return {"items": items, "count": len(items)}


def get_progress_summary(
    student_id: str,
    *,
    subject_id: str | None = None,
) -> dict[str, Any]:
    progress = practice_repo.get_progress(student_id, subject_id)
    completed = [item for item in progress if item.get("status") == "completed"]
    mistakes = practice_repo.get_mistakes(student_id)
    if subject_id:
        mistakes = [item for item in mistakes if _normal_subject_id(item.get("subject_id", "")) == _normal_subject_id(subject_id)]

    weak_topic_counts = Counter(item.get("topic_id", "") for item in mistakes if item.get("topic_id"))
    return {
        "studentId": student_id,
        "subjectId": subject_id,
        "completedLessons": len(completed),
        "completedLessonIds": [item.get("lesson_id", "") for item in completed if item.get("lesson_id")],
        "mistakeCount": len(mistakes),
        "weakTopics": [
            {"topicId": topic_id, "count": count}
            for topic_id, count in weak_topic_counts.most_common(5)
        ],
        "source": "practice_progress",
    }


def can_preview(user: dict[str, Any]) -> bool:
    return str(user.get("role", "")).lower() in PREVIEW_ROLES


def can_view_answer_keys(user: dict[str, Any]) -> bool:
    return can_preview(user)


def _all_units(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for topic in topics:
        units.extend(practice_repo.get_units(topic["id"]))
    return units


def _active_exercises_for_lesson(lesson_id: str, include_preview: bool) -> list[dict[str, Any]]:
    return [
        challenge
        for challenge in practice_repo.get_challenges(lesson_id)
        if _is_visible(challenge, include_preview)
    ]


def _build_subject(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _normal_subject_id(raw["subject_id"]),
        "name": raw.get("name", raw["subject_id"].title()),
        "description": raw.get("description", ""),
        "gradeLevels": raw.get("grade_levels", []),
        "language": raw.get("language", _subject_language(raw["subject_id"])),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
    }


def _build_topic(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["topic_id"],
        "subjectId": _normal_subject_id(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "title": raw.get("title", raw["topic_id"]),
        "description": raw.get("description", ""),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
    }


def _build_unit(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["unit_id"],
        "subjectId": _normal_subject_id(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "topicId": raw["topic_id"],
        "title": raw.get("title", raw["unit_id"]),
        "description": raw.get("description", ""),
        "rolloutState": _content_state(raw),
        "order": _as_int(raw.get("order", 0)),
    }


def _build_lesson(raw: dict[str, Any], *, exercise_count: int) -> dict[str, Any]:
    return {
        "id": raw["lesson_id"],
        "subjectId": _normal_subject_id(raw["subject_id"]),
        "gradeLevel": raw.get("grade_level", raw.get("grade_band", "")),
        "unitId": raw.get("unit_id", ""),
        "topicId": raw["topic_id"],
        "title": raw.get("title", raw["lesson_id"]),
        "objective": raw.get("objective", raw.get("description", "")),
        "difficulty": raw.get("difficulty", "practice"),
        "estimatedMinutes": _as_int(raw.get("estimated_minutes", 10)),
        "rolloutState": _content_state(raw),
        "exerciseCount": exercise_count,
        "source": raw.get("source", "practice_backfill"),
    }


def _build_exercise(raw: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper; student curriculum projections are always answer-free."""
    return practice_projection_service.build_exercise_preview(raw)


def _subject_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and _normal_subject_id(raw.get("subject_id", "")) != _normal_subject_id(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _topic_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and _normal_subject_id(raw.get("subject_id", "")) != _normal_subject_id(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _lesson_matches(raw: dict[str, Any], subject_id: str | None, grade_level: str | None) -> bool:
    if subject_id and _normal_subject_id(raw.get("subject_id", "")) != _normal_subject_id(subject_id):
        return False
    return _grade_matches(raw, grade_level)


def _grade_matches(raw: dict[str, Any], grade_level: str | None) -> bool:
    if not grade_level:
        return True
    grade_values = raw.get("grade_levels") or [raw.get("grade_level", raw.get("grade_band", ""))]
    return grade_level in grade_values


def _is_visible(raw: dict[str, Any], include_preview: bool) -> bool:
    state = _content_state(raw)
    return include_preview or state in VISIBLE_STATES


def _matches_state(raw: dict[str, Any], rollout_state: str | None, include_preview: bool) -> bool:
    if not _is_visible(raw, include_preview):
        return False
    return rollout_state is None or _content_state(raw) == rollout_state.lower()


def _content_state(raw: dict[str, Any]) -> str:
    return str(raw.get("rollout_state") or raw.get("content_state") or raw.get("status") or "active").lower()


def _subject_language(subject_id: str) -> str:
    subject = _normal_subject_id(subject_id)
    if subject == "german":
        return "de"
    if subject == "english":
        return "en"
    return "neutral"


def _normal_subject_id(subject_id: str) -> str:
    value = str(subject_id).strip().lower()
    aliases = {"mathematics": "math", "mathematik": "math", "deutsch": "german", "englisch": "english"}
    return aliases.get(value, value)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    return int(value)
