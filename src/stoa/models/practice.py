"""Allowlist contracts separating answer-free practice content from recorded results."""

from __future__ import annotations

from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OpaqueAttemptId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class _PracticeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PracticeChallengePreview(_PracticeContract):
    """The complete challenge shape safe to send before a recorded attempt."""

    challenge_id: NonEmptyText = Field(alias="challengeId")
    lesson_id: NonEmptyText = Field(alias="lessonId")
    prompt: NonEmptyText
    type: NonEmptyText
    choices: list[str] | None = None
    hint_available: bool = Field(alias="hintAvailable")
    unit_id: str | None = Field(default=None, alias="unitId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    grade_level: str | None = Field(default=None, alias="gradeLevel")
    topic_id: str | None = Field(default=None, alias="topicId")
    topic: str | None = None
    difficulty: str | None = None


class PracticeHintResponse(_PracticeContract):
    challenge_id: NonEmptyText = Field(alias="challengeId")
    hint: NonEmptyText


class PracticeAttemptResult(_PracticeContract):
    """Answer-bearing content unlocked only by a durable attempt receipt."""

    attempt_id: OpaqueAttemptId = Field(alias="attemptId")
    challenge_id: NonEmptyText = Field(alias="challengeId")
    correct: bool
    standard_answer: NonEmptyText = Field(alias="standardAnswer")
    explanation: NonEmptyText
    feedback: NonEmptyText
    next_challenge_id: str | None = Field(default=None, alias="nextChallengeId")
    retry_allowed: bool = Field(alias="retryAllowed")
    attempts_remaining: int = Field(alias="attemptsRemaining", ge=0)

    @classmethod
    def from_recorded_attempt(
        cls,
        recorded_attempt: Mapping[str, Any] | None,
        **result_fields: Any,
    ) -> "PracticeAttemptResult":
        """Fail closed unless persistence returned a non-empty immutable attempt ID."""
        attempt_id = str((recorded_attempt or {}).get("attempt_id") or "").strip()
        if not attempt_id:
            raise ValueError("a recorded attempt receipt is required before revealing answers")
        return cls(attemptId=attempt_id, **result_fields)


class PrivilegedPracticeAnswer(_PracticeContract):
    """Explicit answer projection for separately authorized teacher/admin reads."""

    challenge_id: NonEmptyText = Field(alias="challengeId")
    standard_answer: NonEmptyText = Field(alias="standardAnswer")
    explanation: NonEmptyText
    correct_feedback: NonEmptyText = Field(alias="correctFeedback")
    incorrect_feedback: NonEmptyText = Field(alias="incorrectFeedback")
