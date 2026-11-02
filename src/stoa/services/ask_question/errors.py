"""A question's own failure codes, and the contract each is sent under.

The strings are the ones the frontend compares, so they never change. They
are rendered through `AttachmentDecisionError` and the conversation route's
`_raise_attachment` until #211 gives errors one home.
"""

from enum import StrEnum

from stoa.security.attachment_errors import (
    AttachmentClientAction,
    AttachmentErrorCode,
    AttachmentErrorContract,
)


class AskQuestionErrorCode(StrEnum):
    MESSAGE_IDEMPOTENCY_CONFLICT = "message_idempotency_conflict"
    MESSAGE_IN_PROGRESS = "message_in_progress"
    MESSAGE_DAILY_LIMIT = "message_daily_limit"
    MESSAGE_FAILED = "message_failed"
    MESSAGE_COMMAND_EXPIRED = "message_command_expired"
    MESSAGE_COMMAND_NOT_FOUND = "message_command_not_found"

    @property
    def contract(self) -> AttachmentErrorContract:
        return ASK_QUESTION_ERROR_REGISTRY[self]


ASK_QUESTION_ERROR_REGISTRY: dict[AskQuestionErrorCode, AttachmentErrorContract] = {
    AskQuestionErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT: AttachmentErrorContract(
        409,
        "This message key was already used for a different request.",
        AttachmentClientAction.SELECT_FILE,
    ),
    AskQuestionErrorCode.MESSAGE_IN_PROGRESS: AttachmentErrorContract(
        409,
        "This message is still being processed. Try again shortly.",
        AttachmentClientAction.RETRY_LATER,
        retryable=True,
        idempotent_only=True,
        max_attempts=20,
    ),
    AskQuestionErrorCode.MESSAGE_DAILY_LIMIT: AttachmentErrorContract(
        429,
        "Your daily message limit is reached. Try again tomorrow.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AskQuestionErrorCode.MESSAGE_FAILED: AttachmentErrorContract(
        409,
        "This message could not be completed. Send it again.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AskQuestionErrorCode.MESSAGE_COMMAND_EXPIRED: AttachmentErrorContract(
        409,
        "This message request expired. Send it again.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AskQuestionErrorCode.MESSAGE_COMMAND_NOT_FOUND: AttachmentErrorContract(
        409,
        "This message request is unavailable. Send it again.",
        AttachmentClientAction.RETRY_LATER,
    ),
}

if set(ASK_QUESTION_ERROR_REGISTRY) != set(AskQuestionErrorCode):
    missing = set(AskQuestionErrorCode) - set(ASK_QUESTION_ERROR_REGISTRY)
    extra = set(ASK_QUESTION_ERROR_REGISTRY) - set(AskQuestionErrorCode)
    raise RuntimeError(f"question error registry is not exhaustive: missing={missing}, extra={extra}")

# Both kinds reach a client through the same `code` field, so a string must
# name one code only.
if {code.value for code in AskQuestionErrorCode} & {code.value for code in AttachmentErrorCode}:
    raise RuntimeError("question and attachment error codes share a string")


def parse_error_code(value: str) -> AskQuestionErrorCode | AttachmentErrorCode:
    """The code a stored string names, the question's own first.

    Raises `ValueError` for a string that names neither.
    """
    try:
        return AskQuestionErrorCode(value)
    except ValueError:
        return AttachmentErrorCode(value)
