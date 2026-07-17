"""Typed answer-free previews and attempt-gated practice result projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stoa.models.practice import (
    CurriculumLessonPreview,
    PracticeAttemptResult,
    PracticeChallengePreview,
    PracticeExercisePreview,
    PracticeLessonPreview,
    PrivilegedPracticeAnswer,
)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


def build_challenge_preview(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only fields approved for a pre-attempt challenge response."""
    return _dump(
        PracticeChallengePreview(
            challengeId=raw["challenge_id"],
            lessonId=raw["lesson_id"],
            unitId=raw.get("unit_id"),
            subjectId=raw.get("subject_id"),
            gradeLevel=raw.get("grade_level"),
            topicId=raw.get("topic_id"),
            topic=raw.get("topic_title"),
            difficulty=raw.get("difficulty"),
            type=raw.get("type", "text_input"),
            prompt=raw["prompt"],
            options=raw.get("options"),
            hintAvailable=bool(raw.get("hint") and raw.get("hint_approved") is True),
        )
    )


def build_lesson_preview(
    raw: Mapping[str, Any],
    challenges: list[Mapping[str, Any]],
    status: str = "available",
) -> dict[str, Any]:
    """Build a lesson from answer-free challenge projections only."""
    return _dump(
        PracticeLessonPreview(
            id=raw["lesson_id"],
            unitId=raw.get("unit_id", ""),
            subjectId=raw["subject_id"],
            gradeLevel=raw.get("grade_level", ""),
            topicId=raw["topic_id"],
            title=raw["title"],
            topic=raw.get("topic_title", ""),
            difficulty=raw.get("difficulty", "practice"),
            status=status,
            estimatedMinutes=raw.get("estimated_minutes", 10),
            challenges=[PracticeChallengePreview.model_validate(item) for item in challenges],
        )
    )


def build_exercise_preview(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only fields approved for student curriculum exercise responses."""
    return _dump(
        PracticeExercisePreview(
            id=raw["challenge_id"],
            lessonId=raw["lesson_id"],
            subjectId=_normal_subject_id(raw["subject_id"]),
            topicId=raw["topic_id"],
            type=raw.get("type", "text_input"),
            prompt=raw["prompt"],
            choices=raw.get("options"),
            difficulty=raw.get("difficulty", "practice"),
            estimatedMinutes=_as_int(raw.get("estimated_minutes", 5)),
            skills=raw.get("skills", []),
            rolloutState=_content_state(raw),
            source=raw.get("source", "practice_backfill"),
        )
    )


def build_curriculum_lesson_preview(
    raw: Mapping[str, Any], exercises: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Build answer-free curriculum detail, including all nested exercises."""
    return _dump(
        CurriculumLessonPreview(
            id=raw["lesson_id"],
            subjectId=_normal_subject_id(raw["subject_id"]),
            gradeLevel=raw.get("grade_level", raw.get("grade_band", "")),
            unitId=raw.get("unit_id", ""),
            topicId=raw["topic_id"],
            title=raw.get("title", raw["lesson_id"]),
            objective=raw.get("objective", raw.get("description", "")),
            difficulty=raw.get("difficulty", "practice"),
            estimatedMinutes=_as_int(raw.get("estimated_minutes", 10)),
            rolloutState=_content_state(raw),
            exerciseCount=len(exercises),
            source=raw.get("source", "practice_backfill"),
            prerequisiteLessonIds=raw.get("prerequisite_lesson_ids", []),
            exercises=[PracticeExercisePreview.model_validate(item) for item in exercises],
            nextStep=raw.get("next_step", ""),
        )
    )


def build_attempt_result(
    recorded_attempt: Mapping[str, Any] | None,
) -> PracticeAttemptResult:
    """Build an answer-bearing result from one complete immutable receipt only."""
    receipt = dict(recorded_attempt or {})
    required_text = (
        "attempt_id",
        "student_id",
        "challenge_id",
        "challenge_version",
        "challenge_content_hash",
        "standard_answer",
        "explanation",
        "correct_feedback",
        "incorrect_feedback",
        "feedback",
        "subject_id",
        "topic_id",
        "lesson_id",
        "created_at",
    )
    if any(not isinstance(receipt.get(field), str) or not receipt[field].strip() for field in required_text):
        raise ValueError("a complete immutable attempt receipt is required")
    content_hash = receipt["challenge_content_hash"]
    if (
        len(content_hash) != 64
        or receipt["challenge_version"] != f"sha256:{content_hash}"
        or type(receipt.get("correct")) is not bool
        or not ({"submitted_answer", "student_answer"} & receipt.keys())
    ):
        raise ValueError("a complete immutable attempt receipt is required")
    expected_feedback = (
        receipt["correct_feedback"]
        if receipt["correct"]
        else receipt["incorrect_feedback"]
    )
    if receipt["feedback"] != expected_feedback:
        raise ValueError("a complete immutable attempt receipt is required")
    next_challenge_id = receipt.get("next_challenge_id")
    if next_challenge_id is not None and not isinstance(next_challenge_id, str):
        raise ValueError("a complete immutable attempt receipt is required")
    correct = receipt["correct"]
    return PracticeAttemptResult.from_recorded_attempt(
        receipt,
        challengeId=receipt["challenge_id"],
        correct=correct,
        standardAnswer=receipt["standard_answer"],
        explanation=receipt["explanation"],
        feedback=receipt["feedback"],
        nextChallengeId=next_challenge_id,
        retryAllowed=not correct,
        attemptsRemaining=0 if correct else 2,
    )


def build_privileged_answer(challenge: Mapping[str, Any]) -> PrivilegedPracticeAnswer:
    """Project only the explicit teacher/admin pre-attempt answer contract."""
    standard_answer = challenge.get("correct_answer", challenge.get("answer_key"))
    return PrivilegedPracticeAnswer(
        challengeId=challenge["challenge_id"],
        standardAnswer=str(standard_answer or "No standard answer is available."),
        explanation=str(
            challenge.get("explanation")
            or "Compare the solution method with the standard answer."
        ),
        correctFeedback=str(challenge.get("correct_feedback") or "Correct."),
        incorrectFeedback=str(
            challenge.get("incorrect_feedback")
            or "Review the explanation and try again."
        ),
    )


def approved_directional_hint(challenge: Mapping[str, Any]) -> str | None:
    """Return only an explicitly approved hint that contains no answer material."""
    if challenge.get("hint_approved") is not True:
        return None
    hint = str(challenge.get("hint") or "").strip()
    normalized_hint = _normalize_sensitive_text(hint)
    if not normalized_hint:
        return None
    for sensitive in (
        challenge.get("correct_answer"),
        challenge.get("answer_key"),
        challenge.get("explanation"),
        challenge.get("correct_feedback"),
        challenge.get("incorrect_feedback"),
    ):
        normalized_sensitive = _normalize_sensitive_text(sensitive)
        if normalized_sensitive and normalized_sensitive in normalized_hint:
            return None
    return hint


def _normalize_sensitive_text(value: Any) -> str:
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def _content_state(raw: Mapping[str, Any]) -> str:
    return str(
        raw.get("rollout_state")
        or raw.get("content_state")
        or raw.get("status")
        or "active"
    ).lower()


def _normal_subject_id(subject_id: Any) -> str:
    value = str(subject_id).strip().lower()
    aliases = {
        "mathematics": "math",
        "mathematik": "math",
        "deutsch": "german",
        "englisch": "english",
    }
    return aliases.get(value, value)


def _as_int(value: Any, default: int = 0) -> int:
    return default if value is None else int(value)
