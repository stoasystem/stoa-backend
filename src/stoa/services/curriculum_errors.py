"""Why the curriculum console refused a request, and the contract of each code.

The authoring, review, publish and migration endpoints (`curriculum_ops_service`,
`curriculum_migration_service`) raise `RuleViolation(CurriculumErrorCode...)`
and `stoa.rule_violation` renders it as `{detail: {code, message,
correlationId}}` (#211, #277). The strings were sent as a bare `detail` before
(`{"detail": "stale_pointer"}`); the console reads both shapes
(stoa-frontend#583), so they keep their names.

What is wrong with a draft's content is not a refusal but the validation report
(`curriculum_issues`); `validation_failed` only says that report has a blocking
issue.
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, register_codes
from stoa.security.errors import SecurityClientAction


class CurriculumErrorCode(StrEnum):
    CURRICULUM_CAPABILITY_REQUIRED = "curriculum_capability_required"
    CURRICULUM_VERSION_NOT_FOUND = "curriculum_version_not_found"
    VALIDATION_FAILED = "validation_failed"
    DRAFT_NOT_EDITABLE = "draft_not_editable"
    NOT_REVIEWABLE = "not_reviewable"
    NOT_IN_REVIEW = "not_in_review"
    NOT_APPROVED = "not_approved"
    ROLLBACK_TARGET_NOT_PUBLISHABLE = "rollback_target_not_publishable"
    STALE_POINTER = "stale_pointer"
    EXERCISE_ID_CONFLICT = "exercise_id_conflict"
    ACTIVE_ASSIGNMENTS_BLOCK_ARCHIVE = "active_assignments_block_archive"
    MIGRATION_CONFIRMATION_MISMATCH = "migration_confirmation_mismatch"
    MIGRATION_NOT_READY = "migration_not_ready"
    MIGRATION_NOT_FOUND = "migration_not_found"
    INVALID_MANIFEST = "invalid_manifest"

    @property
    def contract(self) -> RuleContract:
        return CURRICULUM_ERROR_REGISTRY[self]


_CORRECT_INPUT = SecurityClientAction.CORRECT_INPUT
# The input fields that broke the rule. A draft refused on creation has no
# validation report to read, so the refusal names them.
_NAMES_FIELDS = frozenset({"fields"})

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.curriculum`).
CURRICULUM_ERROR_REGISTRY: dict[CurriculumErrorCode, RuleContract] = {
    CurriculumErrorCode.CURRICULUM_CAPABILITY_REQUIRED: RuleContract(403),
    CurriculumErrorCode.CURRICULUM_VERSION_NOT_FOUND: RuleContract(404),
    CurriculumErrorCode.VALIDATION_FAILED: RuleContract(
        422, action=_CORRECT_INPUT, public_fields=_NAMES_FIELDS
    ),
    CurriculumErrorCode.DRAFT_NOT_EDITABLE: RuleContract(409),
    CurriculumErrorCode.NOT_REVIEWABLE: RuleContract(409),
    CurriculumErrorCode.NOT_IN_REVIEW: RuleContract(409),
    CurriculumErrorCode.NOT_APPROVED: RuleContract(409),
    CurriculumErrorCode.ROLLBACK_TARGET_NOT_PUBLISHABLE: RuleContract(409),
    CurriculumErrorCode.STALE_POINTER: RuleContract(409),
    CurriculumErrorCode.EXERCISE_ID_CONFLICT: RuleContract(409),
    CurriculumErrorCode.ACTIVE_ASSIGNMENTS_BLOCK_ARCHIVE: RuleContract(409),
    CurriculumErrorCode.MIGRATION_CONFIRMATION_MISMATCH: RuleContract(409),
    CurriculumErrorCode.MIGRATION_NOT_READY: RuleContract(409),
    CurriculumErrorCode.MIGRATION_NOT_FOUND: RuleContract(404),
    CurriculumErrorCode.INVALID_MANIFEST: RuleContract(
        422, action=_CORRECT_INPUT, public_fields=_NAMES_FIELDS
    ),
}

register_codes("curriculum", CurriculumErrorCode, CURRICULUM_ERROR_REGISTRY)
