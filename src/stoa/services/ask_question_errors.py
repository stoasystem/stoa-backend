"""A question's own failure codes, and the contract each is sent under.

The strings are the ones the frontend compares, so they never change. They
are raised as `AttachmentDecisionError` and rendered, like every rule
violation, by `stoa.rule_violation`.

It sits beside the `ask_question` package rather than in it, like the other
`*_errors` modules: `stoa.models.error` names these codes in the OpenAPI error
bodies, and importing anything inside the package first runs the package's
`__init__`, which loads the whole question flow (#306).
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, register_codes
from stoa.security.attachment_errors import AttachmentClientAction, AttachmentErrorCode


class AskQuestionErrorCode(StrEnum):
    MESSAGE_IDEMPOTENCY_CONFLICT = "message_idempotency_conflict"
    MESSAGE_IN_PROGRESS = "message_in_progress"
    MESSAGE_DAILY_LIMIT = "message_daily_limit"
    MESSAGE_FAILED = "message_failed"
    MESSAGE_COMMAND_EXPIRED = "message_command_expired"
    MESSAGE_COMMAND_NOT_FOUND = "message_command_not_found"
    # The weekly AI allowance (准入, `_admission`).
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    PROVIDER_TOKEN_COUNT_UNAVAILABLE = "provider_token_count_unavailable"
    ALLOWANCE_UNAVAILABLE = "allowance_unavailable"
    # The student's usage period has ended, or they have none (#344). A request
    # for a human teacher is refused with this same code: one string may name
    # only one code, and the client reads the code alone.
    USAGE_PERIOD_ENDED = "usage_period_ended"

    @property
    def contract(self) -> RuleContract:
        return ASK_QUESTION_ERROR_REGISTRY[self]


# A refused first message names the conversation already made (#61).
_NAMES_CONVERSATION = frozenset({"conversationId"})

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.ask_question`).
ASK_QUESTION_ERROR_REGISTRY: dict[AskQuestionErrorCode, RuleContract] = {
    AskQuestionErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT: RuleContract(
        409,
        action=AttachmentClientAction.SELECT_FILE,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.MESSAGE_IN_PROGRESS: RuleContract(
        409,
        action=AttachmentClientAction.RETRY_LATER,
        retryable=True,
        idempotent_only=True,
        max_attempts=20,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.MESSAGE_DAILY_LIMIT: RuleContract(
        429,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.MESSAGE_FAILED: RuleContract(
        409,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.MESSAGE_COMMAND_EXPIRED: RuleContract(
        409,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.MESSAGE_COMMAND_NOT_FOUND: RuleContract(
        409,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    AskQuestionErrorCode.ALLOWANCE_EXHAUSTED: RuleContract(
        429,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    # Nothing was paid for: the same message may be sent again.
    AskQuestionErrorCode.PROVIDER_TOKEN_COUNT_UNAVAILABLE: RuleContract(
        503,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    # The allowance could not be read or settled. The answer, if there is one,
    # is kept: sending the same message again returns it once settling succeeds.
    AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE: RuleContract(
        503,
        action=AttachmentClientAction.RETRY_LATER,
        public_fields=_NAMES_CONVERSATION,
    ),
    # Asking again changes nothing until an administrator extends the period
    # (payment is offline), so it is not retryable and names no action.
    AskQuestionErrorCode.USAGE_PERIOD_ENDED: RuleContract(
        403,
        public_fields=_NAMES_CONVERSATION,
    ),
}

# Registering refuses a string that any other domain's code already names:
# both reach a client through the same `code` field.
register_codes("ask_question", AskQuestionErrorCode, ASK_QUESTION_ERROR_REGISTRY)


def parse_error_code(value: str) -> AskQuestionErrorCode | AttachmentErrorCode:
    """The code a stored string names, the question's own first.

    Raises `ValueError` for a string that names neither.
    """
    try:
        return AskQuestionErrorCode(value)
    except ValueError:
        return AttachmentErrorCode(value)
