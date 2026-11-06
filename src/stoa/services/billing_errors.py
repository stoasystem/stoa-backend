"""What a parent's billing pages refuse with (#211).

The parent's checkout status, billing overview and allowance pages raise these
from `routers/parents.py`, as plain `RuleViolation`s. The strings are the ones
clients already compare; `subscription_service` still sends the two checkout
codes itself, in a body of its own, until payments are unfrozen and Stripe is
split out.
"""

from __future__ import annotations

from enum import StrEnum

from stoa.rule_violation import RuleContract, register_codes


class BillingErrorCode(StrEnum):
    CHECKOUT_NOT_FOUND = "checkout_not_found"
    CHECKOUT_TEMPORARILY_UNAVAILABLE = "checkout_temporarily_unavailable"
    BILLING_PROJECTION_TEMPORARILY_UNAVAILABLE = "billing_projection_temporarily_unavailable"
    ALLOWANCE_PROJECTION_TEMPORARILY_UNAVAILABLE = "allowance_projection_temporarily_unavailable"

    @property
    def contract(self) -> RuleContract:
        return BILLING_ERROR_REGISTRY[self]


_RETRY_LATER = RuleContract(503, "retry_later", retryable=True, max_attempts=1)

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.billing`).
BILLING_ERROR_REGISTRY: dict[BillingErrorCode, RuleContract] = {
    BillingErrorCode.CHECKOUT_NOT_FOUND: RuleContract(404),
    BillingErrorCode.CHECKOUT_TEMPORARILY_UNAVAILABLE: _RETRY_LATER,
    BillingErrorCode.BILLING_PROJECTION_TEMPORARILY_UNAVAILABLE: _RETRY_LATER,
    BillingErrorCode.ALLOWANCE_PROJECTION_TEMPORARILY_UNAVAILABLE: _RETRY_LATER,
}

register_codes("billing", BillingErrorCode, BILLING_ERROR_REGISTRY)

