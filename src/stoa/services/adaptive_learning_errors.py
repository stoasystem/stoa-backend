"""Refusals of adaptive learning: assignments and their automation (#211).

Raised by `stoa.services.adaptive_learning_service`. An automation batch that
meets one of these while executing a candidate records it as that candidate's
refusal rather than failing the batch.
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class AdaptiveLearningErrorCode(StrEnum):
    QUESTION_HISTORY_UNAVAILABLE = "question_history_unavailable"
    ASSIGNMENT_NOT_FOUND = "assignment_not_found"
    ASSIGNMENT_STATUS_NOT_CREATABLE = "assignment_status_not_creatable"
    ASSIGNMENT_STATUS_UNSUPPORTED = "assignment_status_unsupported"
    ASSIGNMENT_ACTION_UNSUPPORTED = "assignment_action_unsupported"
    ASSIGNMENT_NOT_STARTABLE = "assignment_not_startable"
    ASSIGNMENT_NOT_COMPLETABLE = "assignment_not_completable"
    ASSIGNMENT_NOT_SKIPPABLE = "assignment_not_skippable"
    ASSIGNMENT_SOURCE_TYPE_UNSUPPORTED = "assignment_source_type_unsupported"
    ASSIGNMENT_SOURCE_NOT_FOUND = "assignment_source_not_found"
    AI_DRAFT_NOT_ASSIGNABLE = "ai_draft_not_assignable"
    DRAFT_OF_ANOTHER_STUDENT = "draft_of_another_student"
    BATCH_APPROVAL_REQUIRED = "batch_approval_required"
    BATCH_CANDIDATES_REQUIRED = "batch_candidates_required"
    BATCH_PREVIEW_STALE = "batch_preview_stale"
    CANDIDATE_NOT_IN_PREVIEW = "candidate_not_in_preview"
    CANDIDATE_PREVIEW_MISMATCH = "candidate_preview_mismatch"
    CANDIDATE_STATUS_MISMATCH = "candidate_status_mismatch"
    AUTOMATION_SOURCE_TYPE_UNSUPPORTED = "automation_source_type_unsupported"
    AUTOMATION_SOURCE_TYPE_REQUIRED = "automation_source_type_required"
    POLICY_VALUE_UNSUPPORTED = "policy_value_unsupported"
    POLICY_VALUE_BLANK = "policy_value_blank"

    @property
    def contract(self) -> RuleContract:
        return ADAPTIVE_LEARNING_ERROR_REGISTRY[self]


_C = AdaptiveLearningErrorCode
_INPUT = RuleContract(400, "correct_input")
# The assignment, or the preview a batch was approved from, moved on.
_STATE = RuleContract(409)

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.adaptive_learning`).
ADAPTIVE_LEARNING_ERROR_REGISTRY: dict[AdaptiveLearningErrorCode, RuleContract] = {
    _C.QUESTION_HISTORY_UNAVAILABLE: RuleContract(
        503, "retry_later", retryable=True, idempotent_only=True, max_attempts=2
    ),
    _C.ASSIGNMENT_NOT_FOUND: RuleContract(404),
    _C.ASSIGNMENT_STATUS_NOT_CREATABLE: _INPUT,
    _C.ASSIGNMENT_STATUS_UNSUPPORTED: _INPUT,
    _C.ASSIGNMENT_ACTION_UNSUPPORTED: _INPUT,
    _C.ASSIGNMENT_NOT_STARTABLE: _STATE,
    _C.ASSIGNMENT_NOT_COMPLETABLE: _STATE,
    _C.ASSIGNMENT_NOT_SKIPPABLE: _STATE,
    _C.ASSIGNMENT_SOURCE_TYPE_UNSUPPORTED: _INPUT,
    # The curriculum exercise or AI draft an assignment would be made from.
    _C.ASSIGNMENT_SOURCE_NOT_FOUND: RuleContract(404),
    _C.AI_DRAFT_NOT_ASSIGNABLE: _STATE,
    _C.DRAFT_OF_ANOTHER_STUDENT: _INPUT,
    _C.BATCH_APPROVAL_REQUIRED: _INPUT,
    _C.BATCH_CANDIDATES_REQUIRED: _INPUT,
    _C.BATCH_PREVIEW_STALE: _STATE,
    _C.CANDIDATE_NOT_IN_PREVIEW: _STATE,
    _C.CANDIDATE_PREVIEW_MISMATCH: _STATE,
    _C.CANDIDATE_STATUS_MISMATCH: _INPUT,
    _C.AUTOMATION_SOURCE_TYPE_UNSUPPORTED: _INPUT,
    _C.AUTOMATION_SOURCE_TYPE_REQUIRED: _INPUT,
    _C.POLICY_VALUE_UNSUPPORTED: _INPUT,
    _C.POLICY_VALUE_BLANK: _INPUT,
}

register_codes("adaptive_learning", AdaptiveLearningErrorCode, ADAPTIVE_LEARNING_ERROR_REGISTRY)


class AdaptiveLearningViolation(RuleViolation):
    """An assignment or automation request was refused."""

    code: AdaptiveLearningErrorCode
