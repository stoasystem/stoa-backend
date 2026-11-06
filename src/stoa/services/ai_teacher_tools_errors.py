"""Refusals of the reviewed AI teacher tools (`stoa.services.ai_teacher_tools_service`)."""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class AiTeacherToolsErrorCode(StrEnum):
    AI_DRAFT_NOT_FOUND = "ai_draft_not_found"
    DRAFT_ALREADY_ARCHIVED = "draft_already_archived"
    DRAFT_ALREADY_REVIEWED = "draft_already_reviewed"
    DRAFT_QUESTION_UNAVAILABLE = "draft_question_unavailable"
    DRAFT_TYPE_UNSUPPORTED = "draft_type_unsupported"
    DRAFT_OPTION_UNSUPPORTED = "draft_option_unsupported"
    QUESTION_OF_ANOTHER_STUDENT = "question_of_another_student"
    SUBJECT_UNSUPPORTED = "subject_unsupported"
    TOPIC_REQUIRED = "topic_required"
    EXERCISE_COUNT_INVALID = "exercise_count_invalid"

    @property
    def contract(self) -> RuleContract:
        return AI_TEACHER_TOOLS_ERROR_REGISTRY[self]


_C = AiTeacherToolsErrorCode
_INPUT = RuleContract(400, "correct_input")

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.ai_teacher_tools`).
AI_TEACHER_TOOLS_ERROR_REGISTRY: dict[AiTeacherToolsErrorCode, RuleContract] = {
    _C.AI_DRAFT_NOT_FOUND: RuleContract(404),
    _C.DRAFT_ALREADY_ARCHIVED: RuleContract(409),
    _C.DRAFT_ALREADY_REVIEWED: RuleContract(409),
    _C.DRAFT_QUESTION_UNAVAILABLE: RuleContract(409),
    _C.DRAFT_TYPE_UNSUPPORTED: _INPUT,
    # `{field}` names the request field (`difficulty`, `status`, ...).
    _C.DRAFT_OPTION_UNSUPPORTED: _INPUT,
    _C.QUESTION_OF_ANOTHER_STUDENT: _INPUT,
    _C.SUBJECT_UNSUPPORTED: _INPUT,
    _C.TOPIC_REQUIRED: _INPUT,
    _C.EXERCISE_COUNT_INVALID: _INPUT,
}

register_codes("ai_teacher_tools", AiTeacherToolsErrorCode, AI_TEACHER_TOOLS_ERROR_REGISTRY)


class AiTeacherToolsViolation(RuleViolation):
    """A request to the AI teacher tools was refused."""

    code: AiTeacherToolsErrorCode
