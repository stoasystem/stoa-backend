"""Moderation refusals (`stoa.services.moderation_service`), and their contracts.

A reporter who may not report the content is refused with the security codes
(`action_not_allowed`, `resource_not_found`); a page cursor that does not
decode with `cursor_invalid` (`stoa.services.account_errors`).
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class ModerationErrorCode(StrEnum):
    QUESTION_NOT_WRITABLE = "question_not_writable"
    MODERATION_CASE_NOT_FOUND = "moderation_case_not_found"
    CASE_IMAGE_NOT_FOUND = "case_image_not_found"
    CASE_IMAGE_UNAVAILABLE = "case_image_unavailable"
    IMAGE_CASE_NOT_REPORTABLE = "image_case_not_reportable"
    REPORTED_MESSAGE_NOT_FOUND = "reported_message_not_found"
    NO_AI_ANSWER_TO_REPORT = "no_ai_answer_to_report"
    NO_TEACHER_REPLY_TO_REPORT = "no_teacher_reply_to_report"

    @property
    def contract(self) -> RuleContract:
        return MODERATION_ERROR_REGISTRY[self]


_C = ModerationErrorCode

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.moderation`).
MODERATION_ERROR_REGISTRY: dict[ModerationErrorCode, RuleContract] = {
    # The question's record is missing what a case has to name (its owner and
    # privacy generation), so no case can be opened against it.
    _C.QUESTION_NOT_WRITABLE: RuleContract(409),
    _C.MODERATION_CASE_NOT_FOUND: RuleContract(404),
    _C.CASE_IMAGE_NOT_FOUND: RuleContract(404),
    # The stored image could not be read, or no longer matches its digest.
    _C.CASE_IMAGE_UNAVAILABLE: RuleContract(503, "retry_later"),
    _C.IMAGE_CASE_NOT_REPORTABLE: RuleContract(400),
    _C.REPORTED_MESSAGE_NOT_FOUND: RuleContract(404),
    _C.NO_AI_ANSWER_TO_REPORT: RuleContract(400),
    _C.NO_TEACHER_REPLY_TO_REPORT: RuleContract(400),
}

register_codes("moderation", ModerationErrorCode, MODERATION_ERROR_REGISTRY)


class ModerationViolation(RuleViolation):
    """A moderation request was refused."""

    code: ModerationErrorCode
