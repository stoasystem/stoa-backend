"""Allowlist contracts separating answer-free practice content from recorded results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from typing import Annotated, Any, Mapping

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StringConstraints


#: What a challenge is, when the stored row does not say.
#:
#: A row with no `type` has no `options` either - all 60 such rows in the
#: curriculum today - so the only kind it can be answered as is a typed answer.
#: The review path used to default to `multiple_choice` instead, which handed
#: the client a choice question with nothing to choose from: the same question
#: was answerable inside its lesson and unanswerable on the review page. One
#: definition, so the two paths cannot drift apart again (#124).
DEFAULT_CHALLENGE_TYPE = "text_input"

#: What the student projections say about `type` and `figure`, for the client.
TYPE_DESCRIPTION = (
    "How the exercise is answered: `text_input` (typed), `multiple_choice` (one option), "
    "`multi_select` (a set of options, see the answer submission), `grid_drawing` "
    "(a drawing on `grid`), or another kind."
)
FIGURE_DESCRIPTION = (
    "An allowlisted inline SVG. In a `multi_select` exercise an element carrying "
    "`data-choice=\"B\"` is a hotspot: the option with that letter, A for the first."
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OpaqueAttemptId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class _PracticeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GridPoint(_PracticeContract):
    """A labelled point on a grid; a coordinate is a multiple of the grid's step."""

    label: NonEmptyText
    x: int | float
    y: int | float


class GridDrawing(_PracticeContract):
    """Points, and segments and polygons joining points by label (`grid_drawing`, #594).

    The same shape is the figure already on a grid (`GridSpec.given`), what a
    student sends as the answer to a `grid_drawing` exercise, the answer a
    receipt records, and the solution shown once an answer is on record.
    """

    points: list[GridPoint] = Field(default_factory=list)
    segments: list[list[str]] = Field(default_factory=list)
    polygons: list[list[str]] = Field(default_factory=list)


class GridLimits(_PracticeContract):
    """The most one drawing may hold."""

    points: int
    segments: int
    polygons: int


class GridSpec(_PracticeContract):
    """The grid a `grid_drawing` exercise is drawn on, without its checks or solutions.

    Bounds are whole numbers; `step` is 1 or 0.5. `axes` draws the axes through
    0 and `axisLabels` numbers them. `labels` are the point names the exercise
    asks for, in order; a student's labels must differ from the given figure's.
    The exercise's `figure` is this grid and its given figure drawn as an SVG.
    """

    x_min: int = Field(alias="xMin")
    x_max: int = Field(alias="xMax")
    y_min: int = Field(alias="yMin")
    y_max: int = Field(alias="yMax")
    step: int | float
    axes: bool = False
    axis_labels: bool = Field(default=False, alias="axisLabels")
    labels: list[str] = Field(default_factory=list)
    given: GridDrawing = Field(default_factory=GridDrawing)
    limits: GridLimits


class PracticeChallengePreview(_PracticeContract):
    """The complete challenge shape safe to send before a recorded attempt."""

    challenge_id: NonEmptyText = Field(alias="challengeId")
    lesson_id: NonEmptyText = Field(alias="lessonId")
    prompt: NonEmptyText
    type: NonEmptyText = Field(description=TYPE_DESCRIPTION)
    choices: list[str] | None = Field(
        default=None,
        alias="options",
        validation_alias=AliasChoices("options", "choices"),
    )
    hint_available: bool = Field(alias="hintAvailable")
    figure: str | None = Field(default=None, description=FIGURE_DESCRIPTION)
    option_figures: list[str] | None = Field(default=None, alias="optionFigures")
    grid: GridSpec | None = None
    unit_id: str | None = Field(default=None, alias="unitId")
    subject_id: str | None = Field(default=None, alias="subjectId")
    grade_level: str | None = Field(default=None, alias="gradeLevel")
    topic_id: str | None = Field(default=None, alias="topicId")
    topic: str | None = None
    difficulty: str | None = None


class LessonSection(_PracticeContract):
    """One explanation card of a lesson, in the reader's language (#465).

    Shown before the lesson's exercises, in the lesson's order. `body` may hold
    LaTeX. The stored `translations` the card was chosen from are not sent.
    """

    id: NonEmptyText
    title: NonEmptyText
    body: NonEmptyText


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
    sections: list[LessonSection] = Field(default_factory=list)
    challenges: list[PracticeChallengePreview]


class PracticeExercisePreview(_PracticeContract):
    """Answer-free curriculum exercise projection."""

    exercise_id: NonEmptyText = Field(alias="id")
    lesson_id: NonEmptyText = Field(alias="lessonId")
    subject_id: NonEmptyText = Field(alias="subjectId")
    topic_id: NonEmptyText = Field(alias="topicId")
    type: NonEmptyText = Field(description=TYPE_DESCRIPTION)
    prompt: NonEmptyText
    choices: list[str] | None = None
    figure: str | None = Field(default=None, description=FIGURE_DESCRIPTION)
    option_figures: list[str] | None = Field(default=None, alias="optionFigures")
    grid: GridSpec | None = None
    difficulty: str = "practice"
    estimated_minutes: int = Field(default=5, alias="estimatedMinutes", ge=0)
    skills: list[str] = Field(default_factory=list)
    rollout_state: str = Field(default="active", alias="rolloutState")
    source: str = "practice_backfill"


class CurriculumLessonPreview(_PracticeContract):
    """Student curriculum lesson detail without exercise explanations or answer derivatives.

    The lesson's own explanation cards (`sections`) are for students and are sent.
    """

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
    sections: list[LessonSection] = Field(default_factory=list)
    exercises: list[PracticeExercisePreview]
    next_step: str = Field(default="", alias="nextStep")


class CurriculumExerciseListPreview(_PracticeContract):
    items: list[PracticeExercisePreview]
    count: int = Field(ge=0)


#: What `answer` holds, by exercise type: the contract the client answers by.
ANSWER_DESCRIPTION = (
    "By the exercise's `type`. `multiple_choice`: the picked option's text, as shown. "
    "`multi_select`: the numbers of the picked options, 0 for the first, in any order, "
    "each at most once, at least one: `[0, 2]`. A hotspot in the figure "
    "(`data-choice=\"B\"`) is the option with that letter, A for the first. "
    "`grid_drawing`: a drawing, `{points: [{label, x, y}], segments: [[a, b]], "
    "polygons: [[a, b, c, ...]]}`, segments and polygons naming points by label, "
    "the student's or the given figure's. Points lie on grid points inside the grid; "
    "labels are 1-3 letters, digits or primes, unique and not a given label; two "
    "points never share a grid point; a polygon has 3-12 different points; at most "
    "`grid.limits`, and not empty. "
    "Anything else: the typed text, or a list of texts for an ordering. "
    "An answer that cannot be one is refused with `practice_answer_invalid`."
)


class PracticeAnswerSubmission(_PracticeContract):
    # The route treats this as untrusted input and narrows it through the bounded
    # submitted-answer normalizer before comparison or persistence.  Keeping the
    # input object-valued also lets the route return one redacted error contract
    # instead of echoing unsupported values through validation diagnostics.
    answer: object = Field(description=ANSWER_DESCRIPTION)
    # The learning session the answer is given in: the Ask conversation open
    # beside the exercise, if any. The receipt records whether the student
    # asked about this exercise there before answering (#449). One that is not
    # the student's own counts as no session.
    conversationId: str | None = Field(default=None, min_length=1, max_length=128)


class QuizAnswerSubmission(_PracticeContract):
    """One answer to a lesson quiz, naming the exercise it answers (#213, #113).

    `exerciseId` names the exercise answered, so the same answer sent twice -
    a retry after a lost response - is recognised and answered with the first
    result rather than judged against the next exercise.
    """

    answer: object = Field(description=ANSWER_DESCRIPTION)
    exercise_id: str = Field(alias="exerciseId", min_length=1, max_length=200)


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
    correct_options: list[int] | None = Field(
        default=None,
        alias="correctOptions",
        description=(
            "Only for a `multi_select` exercise: the numbers of its right options, "
            "0 for the first, in order. `standardAnswer` is the same options as text."
        ),
    )
    standard_drawing: GridDrawing | None = Field(
        default=None,
        alias="standardDrawing",
        description=(
            "Only for a `grid_drawing` exercise: a drawing that is right. Another drawing "
            "may be right too; `standardAnswer` is this one written out."
        ),
    )
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


class LegacyAnswerState(str, Enum):
    """Whether mistake review can faithfully reproduce the submitted answer."""

    RECORDED = "recorded"
    UNKNOWN_LEGACY = "unknown_legacy"


class PracticeMistake(_PracticeContract):
    """One wrong-attempt projection with explicit historical-answer state."""

    id: NonEmptyText
    challenge_id: NonEmptyText = Field(alias="challengeId")
    subject_id: str = Field(default="", alias="subjectId")
    topic: str = ""
    prompt: str = ""
    your_answer: str | list[str] | GridDrawing | None = Field(alias="yourAnswer")
    answer_state: LegacyAnswerState = Field(alias="answerState")
    message: str | None = None
    created_at: str = Field(default="", alias="createdAt")


class PracticeMistakesResponse(_PracticeContract):
    items: list[PracticeMistake]


class ReviewReason(_PracticeContract):
    """Why a question is due now (#447).

    The numbers are for the client to reason with; a student is shown the
    `bandLabel`, never `retrievability` as a percentage. `band` and
    `retrievability` are null for a card with no answer behind it.
    """

    days_overdue: int = Field(default=0, alias="daysOverdue")
    retrievability: float | None = None
    target_retention: float = Field(alias="targetRetention")
    latest_wrong: bool = Field(default=False, alias="latestWrong")
    band: Literal["fresh", "fading", "forgetting", "forgotten"] | None = None
    band_label: str | None = Field(default=None, alias="bandLabel")


class ReviewCard(_PracticeContract):
    """A question due to be attempted again, without its answer."""

    challenge_id: NonEmptyText = Field(alias="challengeId")
    lesson_id: str = Field(default="", alias="lessonId")
    subject_id: str = Field(default="", alias="subjectId")
    topic_id: str = Field(default="", alias="topicId")
    prompt: str = ""
    options: list[str] = Field(default_factory=list)
    figure: str | None = Field(default=None, description=FIGURE_DESCRIPTION)
    option_figures: list[str] | None = Field(default=None, alias="optionFigures")
    grid: GridSpec | None = None
    type: str = Field(default=DEFAULT_CHALLENGE_TYPE, description=TYPE_DESCRIPTION)
    due_at: str = Field(default="", alias="dueAt")
    lapses: int = 0
    reps: int = 0
    reason: ReviewReason | None = None


class ReviewDueResponse(_PracticeContract):
    items: list[ReviewCard]
    due_count: int = Field(default=0, alias="dueCount")
    generated_at: str = Field(default="", alias="generatedAt")


class ReviewSummaryResponse(_PracticeContract):
    due_count: int = Field(default=0, alias="dueCount")
    scheduled_count: int = Field(default=0, alias="scheduledCount")
    next_due_at: str = Field(default="", alias="nextDueAt")


class PrivilegedPracticeAnswer(_PracticeContract):
    """Explicit answer projection for separately authorized teacher/admin reads."""

    challenge_id: NonEmptyText = Field(alias="challengeId")
    standard_answer: NonEmptyText = Field(alias="standardAnswer")
    explanation: NonEmptyText
    correct_feedback: NonEmptyText = Field(alias="correctFeedback")
    incorrect_feedback: NonEmptyText = Field(alias="incorrectFeedback")
