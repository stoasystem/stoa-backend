"""Typed answer-free previews and attempt-gated practice result projections."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from stoa.models.practice import (
    CurriculumLessonPreview,
    DirectionalHintTemplateId,
    HintNonDerivabilityDecision,
    LegacyAnswerState,
    PracticeAttemptResult,
    PracticeChallengePreview,
    PracticeExercisePreview,
    PracticeLessonPreview,
    PracticeMistake,
    PrivilegedPracticeAnswer,
)
from stoa.db.repositories import practice_repo


DIRECTIONAL_HINT_POLICY_VERSION = "practice-directional-hints-v1"
PRACTICE_SUBMITTED_ANSWER_SCHEMA_VERSION = 1
PRACTICE_SUBMITTED_ANSWER_MAX_BYTES = 4096
PRACTICE_SUBMITTED_ANSWER_MAX_DEPTH = 1
PRACTICE_SUBMITTED_ANSWER_MAX_ITEMS = 50
LEGACY_ANSWER_UNKNOWN_MESSAGE = "当时提交的答案未保存"
DIRECTIONAL_HINT_TEMPLATES: dict[str, str] = {
    DirectionalHintTemplateId.REVIEW_PROBLEM_STRUCTURE.value: (
        "Identify what the problem gives you and which operation it asks for."
    ),
    DirectionalHintTemplateId.CHECK_EACH_STEP.value: (
        "Check each step against the rule named in the question."
    ),
    DirectionalHintTemplateId.REPRESENT_BEFORE_SOLVING.value: (
        "Represent the given relationships before you calculate."
    ),
}


def normalize_submitted_answer(value: object) -> str | list[str]:
    """Return a bounded JSON-safe answer without changing its visible bytes."""
    if isinstance(value, str):
        normalized: str | list[str] = value
        item_count = 1
    elif isinstance(value, list):
        if PRACTICE_SUBMITTED_ANSWER_MAX_DEPTH < 1 or any(
            isinstance(child, list) for child in value
        ):
            raise ValueError("submitted answer exceeds the depth bound")
        if any(not isinstance(child, str) for child in value):
            raise ValueError("submitted answer uses an unsupported value type")
        normalized = list(value)
        item_count = len(normalized)
    else:
        raise ValueError("submitted answer uses an unsupported value type")
    if item_count > PRACTICE_SUBMITTED_ANSWER_MAX_ITEMS:
        raise ValueError("submitted answer exceeds the item bound")
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > PRACTICE_SUBMITTED_ANSWER_MAX_BYTES:
        raise ValueError("submitted answer exceeds the serialized byte bound")
    return normalized


def build_mistake_projection(attempt: Mapping[str, Any]) -> PracticeMistake:
    """Project a recorded wrong answer or an explicit legacy unknown."""
    challenge_id = attempt.get("challenge_id")
    if not isinstance(challenge_id, str) or not challenge_id.strip():
        raise ValueError("mistake row has no challenge identity")
    raw_id = attempt.get("SK") or attempt.get("attempt_id") or challenge_id
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ValueError("mistake row has no stable identity")

    answer_key = next(
        (key for key in ("submitted_answer", "student_answer") if key in attempt),
        None,
    )
    if answer_key is None:
        answer = None
        answer_state = LegacyAnswerState.UNKNOWN_LEGACY
        message = LEGACY_ANSWER_UNKNOWN_MESSAGE
    else:
        answer = normalize_submitted_answer(attempt[answer_key])
        answer_state = LegacyAnswerState.RECORDED
        message = None

    return PracticeMistake(
        id=raw_id,
        challengeId=challenge_id,
        subjectId=str(attempt.get("subject_id") or ""),
        topic=str(attempt.get("topic_id") or ""),
        prompt=str(attempt.get("prompt") or ""),
        yourAnswer=answer,
        answerState=answer_state,
        message=message,
        createdAt=str(attempt.get("created_at") or ""),
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
            hintAvailable=approved_directional_hint(raw) is not None,
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
    """Render only a reviewed constant selected by an exact content-bound decision."""
    if any(
        field in challenge
        for field in ("hint", "hint_approved", "directional_hint_parameters")
    ):
        return None
    raw_template_id = challenge.get("directional_hint_template_id")
    raw_decision = challenge.get("hint_non_derivability_decision")
    if not isinstance(raw_template_id, str) or not isinstance(raw_decision, Mapping):
        return None
    try:
        template_id = DirectionalHintTemplateId(raw_template_id)
        decision = HintNonDerivabilityDecision.model_validate(raw_decision)
    except (TypeError, ValueError):
        return None
    if decision.approved_at.utcoffset() is None:
        return None
    content_hash = practice_repo.canonical_challenge_content_hash(dict(challenge))
    version = f"sha256:{content_hash}"
    if (
        decision.template_id is not template_id
        or decision.challenge_version != version
        or decision.content_hash != content_hash
        or decision.policy_version != DIRECTIONAL_HINT_POLICY_VERSION
        or challenge.get("challenge_content_hash") != content_hash
        or challenge.get("challenge_version") != version
    ):
        return None
    return DIRECTIONAL_HINT_TEMPLATES.get(template_id.value)


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
