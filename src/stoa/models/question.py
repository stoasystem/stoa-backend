from enum import Enum


class QuestionStatus(str, Enum):
    PENDING = "pending"
    SUBMISSION_FAILED = "submission_failed"
    AI_ANSWERED = "ai_answered"
    ESCALATED = "escalated"
    TEACHER_ACTIVE = "teacher_active"
    RESOLVED = "resolved"
    # A chat help request the student took back before any teacher took it
    # (#86). Terminal: not dispatched, not resolved, not counted as answered.
    WITHDRAWN = "withdrawn"
    # One no teacher took within the waiting limit, ended by the sweep (#87).
    EXPIRED = "expired"


# A request that ended without a teacher: no longer waiting, never answered.
# The queue row's status and its dispatch status both end in these words.
ENDED_WITHOUT_TEACHER = frozenset({QuestionStatus.WITHDRAWN.value, QuestionStatus.EXPIRED.value})
