"""Allowlist contracts separating answer-free practice content from recorded results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from typing import Annotated, Any, Mapping

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StringConstraints


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
    choices: list[str] | None = Field(
        default=None,
        alias="options",
        validation_alias=AliasChoices("options", "choices"),
    )
    hint_available: bool = Field(alias="hintAvailable")
    unit_id: str | None = Field(default=None, alias="unitId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    grade_level: str | None = Field(default=None, alias="gradeLevel")
    topic_id: str | None = Field(default=None, alias="topicId")
    topic: str | None = None
    difficulty: str | None = None


class PracticeLessonPreview(_PracticeContract):
    """Answer-free lesson projection shared by overview, path, and lesson reads."""

    lesson_id: NonEmptyText = Field(alias="id")
    unit_id: str = Field(default="", alias="unitId")
    subject_id: NonEmptyText = Field(alias="subjectId")
    grade_level: str = Field(default="", alias="gradeLevel")
    topic_id: NonEmptyText = Field(alias="topicId")
    title: NonEmptyText
    topic: str = ""
    difficulty: str = "practice"
    status: str = "available"
    estimated_minutes: int = Field(default=10, alias="estimatedMinutes", ge=0)
    challenges: list[PracticeChallengePreview]


class PracticeExercisePreview(_PracticeContract):
    """Answer-free curriculum exercise projection."""

    exercise_id: NonEmptyText = Field(alias="id")
    lesson_id: NonEmptyText = Field(alias="lessonId")
    subject_id: NonEmptyText = Field(alias="subjectId")
    topic_id: NonEmptyText = Field(alias="topicId")
    type: NonEmptyText
    prompt: NonEmptyText
    choices: list[str] | None = None
    difficulty: str = "practice"
    estimated_minutes: int = Field(default=5, alias="estimatedMinutes", ge=0)
    skills: list[str] = Field(default_factory=list)
    rollout_state: str = Field(default="active", alias="rolloutState")
    source: str = "practice_backfill"


class CurriculumLessonPreview(_PracticeContract):
    """Student curriculum lesson detail without explanations or answer derivatives."""

    lesson_id: NonEmptyText = Field(alias="id")
    subject_id: NonEmptyText = Field(alias="subjectId")
    grade_level: str = Field(default="", alias="gradeLevel")
    unit_id: str = Field(default="", alias="unitId")
    topic_id: NonEmptyText = Field(alias="topicId")
    title: NonEmptyText
    objective: str = ""
    difficulty: str = "practice"
    estimated_minutes: int = Field(default=10, alias="estimatedMinutes", ge=0)
    rollout_state: str = Field(default="active", alias="rolloutState")
    exercise_count: int = Field(default=0, alias="exerciseCount", ge=0)
    source: str = "practice_backfill"
    prerequisite_lesson_ids: list[str] = Field(
        default_factory=list, alias="prerequisiteLessonIds"
    )
    exercises: list[PracticeExercisePreview]
    next_step: str = Field(default="", alias="nextStep")


class CurriculumExerciseListPreview(_PracticeContract):
    items: list[PracticeExercisePreview]
    count: int = Field(ge=0)


class PracticeAnswerSubmission(_PracticeContract):
    answer: str | list[str]


class PracticeHintResponse(_PracticeContract):
    challenge_id: NonEmptyText = Field(alias="challengeId")
    hint_available: bool = Field(alias="hintAvailable")
    hint: NonEmptyText | None = None


class DirectionalHintTemplateId(str, Enum):
    """Closed IDs whose rendered bytes are reviewed and parameter-free."""

    REVIEW_PROBLEM_STRUCTURE = "review_problem_structure"
    CHECK_EACH_STEP = "check_each_step"
    REPRESENT_BEFORE_SOLVING = "represent_before_solving"


class HintReviewerRole(str, Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class HintNonDerivabilityDecision(_PracticeContract):
    """Fail-closed approval bound to one exact complete challenge version."""

    template_id: DirectionalHintTemplateId
    challenge_version: NonEmptyText
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    reviewer_id: NonEmptyText
    reviewer_role: HintReviewerRole
    policy_version: Literal["practice-directional-hints-v1"]
    decision: Literal["non_derivable"]
    approved_at: datetime


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
