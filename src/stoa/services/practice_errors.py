"""Practice refusals: lessons, quizzes, star quizzes and answers (#211).

Raised by `stoa.routers.practice`. The `star_quiz_*`, `lesson_quiz_*`,
`lesson_exercises_unanswered`, `practice_answer_invalid` and
`practice_attempt_unavailable` strings are the ones the web client already
compares (`useStarQuizRun.ts`, `quiz.ts`), so they never change. A star quiz
that is cooling down names when it can be taken again (`retryAt`).
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class PracticeErrorCode(StrEnum):
    # The star quiz of one knowledge point (#165).
    STAR_QUIZ_UNKNOWN_STAR = "star_quiz_unknown_star"
    STAR_QUIZ_ALREADY_LIT = "star_quiz_already_lit"
    STAR_QUIZ_COOLING_DOWN = "star_quiz_cooling_down"
    STAR_QUIZ_UNAVAILABLE = "star_quiz_unavailable"
    STAR_QUIZ_NOT_FOUND = "star_quiz_not_found"
    STAR_QUIZ_FINISHED = "star_quiz_finished"
    STAR_QUIZ_EXPIRED = "star_quiz_expired"
    STAR_QUIZ_OUT_OF_ORDER = "star_quiz_out_of_order"
    # A lesson's quiz, and the credential passing it hands out.
    LESSON_QUIZ_NOT_FOUND = "lesson_quiz_not_found"
    LESSON_QUIZ_FINISHED = "lesson_quiz_finished"
    LESSON_QUIZ_EXPIRED = "lesson_quiz_expired"
    LESSON_QUIZ_UNAVAILABLE = "lesson_quiz_unavailable"
    LESSON_QUIZ_OUT_OF_ORDER = "lesson_quiz_out_of_order"
    LESSON_QUIZ_CREDENTIAL_INVALID = "lesson_quiz_credential_invalid"
    LESSON_QUIZ_CREDENTIAL_EXPIRED = "lesson_quiz_credential_expired"
    LESSON_EXERCISES_UNANSWERED = "lesson_exercises_unanswered"
    # Answers and their attempts.
    PRACTICE_ANSWER_INVALID = "practice_answer_invalid"
    PRACTICE_ATTEMPT_UNAVAILABLE = "practice_attempt_unavailable"
    PRACTICE_ATTEMPT_NOT_FOUND = "practice_attempt_not_found"
    # The curriculum as the student walks it.
    CURRICULUM_STUDENT_REQUIRED = "curriculum_student_required"
    CURRICULUM_LESSON_NOT_FOUND = "curriculum_lesson_not_found"
    NO_LESSONS_AVAILABLE = "no_lessons_available"
    SUBJECT_UNKNOWN = "subject_unknown"
    TOPIC_NOT_FOUND = "topic_not_found"
    NO_TOPICS_FOUND = "no_topics_found"

    @property
    def contract(self) -> RuleContract:
        return PRACTICE_ERROR_REGISTRY[self]


_C = PracticeErrorCode
_GONE = RuleContract(404)
_CONFLICT = RuleContract(409)

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.practice`).
PRACTICE_ERROR_REGISTRY: dict[PracticeErrorCode, RuleContract] = {
    _C.STAR_QUIZ_UNKNOWN_STAR: _GONE,
    _C.STAR_QUIZ_ALREADY_LIT: _CONFLICT,
    _C.STAR_QUIZ_COOLING_DOWN: RuleContract(
        409, "retry_later", public_fields=frozenset({"retryAt"})
    ),
    _C.STAR_QUIZ_UNAVAILABLE: _CONFLICT,
    _C.STAR_QUIZ_NOT_FOUND: _GONE,
    _C.STAR_QUIZ_FINISHED: _CONFLICT,
    _C.STAR_QUIZ_EXPIRED: _CONFLICT,
    _C.STAR_QUIZ_OUT_OF_ORDER: _CONFLICT,
    _C.LESSON_QUIZ_NOT_FOUND: _GONE,
    _C.LESSON_QUIZ_FINISHED: _CONFLICT,
    _C.LESSON_QUIZ_EXPIRED: _CONFLICT,
    _C.LESSON_QUIZ_UNAVAILABLE: _CONFLICT,
    _C.LESSON_QUIZ_OUT_OF_ORDER: _CONFLICT,
    _C.LESSON_QUIZ_CREDENTIAL_INVALID: _CONFLICT,
    _C.LESSON_QUIZ_CREDENTIAL_EXPIRED: _CONFLICT,
    # `{count}` exercises are still to be answered right.
    _C.LESSON_EXERCISES_UNANSWERED: _CONFLICT,
    _C.PRACTICE_ANSWER_INVALID: RuleContract(422, "correct_input"),
    # Nothing was recorded; the same answer may be sent again.
    _C.PRACTICE_ATTEMPT_UNAVAILABLE: RuleContract(503, "retry_later", retryable=True, max_attempts=2),
    _C.PRACTICE_ATTEMPT_NOT_FOUND: _GONE,
    _C.CURRICULUM_STUDENT_REQUIRED: RuleContract(400, "correct_input"),
    _C.CURRICULUM_LESSON_NOT_FOUND: _GONE,
    _C.NO_LESSONS_AVAILABLE: _GONE,
    _C.SUBJECT_UNKNOWN: RuleContract(422, "correct_input"),
    _C.TOPIC_NOT_FOUND: _GONE,
    _C.NO_TOPICS_FOUND: _GONE,
}

register_codes("practice", PracticeErrorCode, PRACTICE_ERROR_REGISTRY)


class PracticeViolation(RuleViolation):
    """A practice request was refused."""

    code: PracticeErrorCode
