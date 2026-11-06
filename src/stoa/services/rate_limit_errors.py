"""The rate admission's refusals (`stoa.services.rate_limit`), and their contracts.

`rate_operation_conflict` and `rate_limit_unavailable` are the strings the
admission has always answered with; `hint_daily_limit` names what used to be
an English sentence.
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class RateLimitErrorCode(StrEnum):
    HINT_DAILY_LIMIT = "hint_daily_limit"
    RATE_OPERATION_CONFLICT = "rate_operation_conflict"
    RATE_LIMIT_UNAVAILABLE = "rate_limit_unavailable"

    @property
    def contract(self) -> RuleContract:
        return RATE_LIMIT_ERROR_REGISTRY[self]


# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.rate_limit`).
RATE_LIMIT_ERROR_REGISTRY: dict[RateLimitErrorCode, RuleContract] = {
    RateLimitErrorCode.HINT_DAILY_LIMIT: RuleContract(429, "retry_later"),
    RateLimitErrorCode.RATE_OPERATION_CONFLICT: RuleContract(409),
    # The counter could not be written; nothing was charged, so the same
    # request may be sent again (it has always asked for 30 seconds).
    RateLimitErrorCode.RATE_LIMIT_UNAVAILABLE: RuleContract(
        503,
        "retry_later",
        retryable=True,
        idempotent_only=True,
        max_attempts=2,
        retry_after_seconds=30,
    ),
}

register_codes("rate_limit", RateLimitErrorCode, RATE_LIMIT_ERROR_REGISTRY)


class RateLimitViolation(RuleViolation):
    """The rate admission refused an operation."""

    code: RateLimitErrorCode
