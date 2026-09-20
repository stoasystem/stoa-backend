"""Payment provider webhook routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from stoa.config import Settings, get_settings
from stoa.db.repositories import billing_fact_repo
from stoa.services import subscription_service
from stoa.security.route_inventory import explicit_route_classification

router = APIRouter()


# ---------------------------------------------------------------------------
# Card 007: the whole paid surface is frozen
# ---------------------------------------------------------------------------

# STOA is assignment-only and does not sell to consumers, so nobody may start,
# resume, inspect or reconcile a payment. Parent checkout, parent and admin
# billing views, manual subscription requests, refunds, rollout controls and
# the Stripe webhook all refuse with one declared 410.
#
# Same shape as `auth.PUBLIC_SELF_REGISTRATION_ENABLED`: one module-level
# switch, the routes stay registered so an old client reads a declared refusal
# instead of a 404, and the authorization inventory does not drift. The one
# difference is that nothing here is deleted -- every handler keeps its body
# below the guard, so flipping the switch restores the behaviour rather than
# leaving a 501.
#
# To unfreeze:
#   1. flip this to True, and drop `entitlement_service.MANUAL_BILLING_OVERRIDE_ENABLED`
#      back to True in the same change -- an unfrozen checkout with a frozen
#      override grants nothing;
#   2. re-provision the Stripe keys and webhook secret, and re-run the provider
#      readiness endpoint before any parent can reach checkout;
#   3. restore the frontend routes, navigation entries and price copy removed
#      in the same card (`stoa-frontend/src/pages/billing/`, `AppRouter.tsx`);
#   4. re-point the tests that now pin the frozen state
#      (`tests/test_billing_freeze.py` is the closure judge -- keep it, it is
#      what stops a newly added paid route from quietly escaping the freeze).
BILLING_AND_SUBSCRIPTION_ENABLED = False

_BILLING_FROZEN_CODE = "billing_frozen"


def billing_frozen() -> HTTPException:
    """The refusal every frozen billing and subscription route raises."""

    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": _BILLING_FROZEN_CODE,
            "message": "This is no longer available. Ask your STOA administrator.",
        },
    )


def refuse_if_frozen() -> None:
    """First statement of every paid handler, in `parents` and `admin` too.

    The switch is read here rather than imported into the other routers, so
    there is exactly one value to flip and no second copy that can be flipped
    and quietly disagree with this one.
    """

    if not BILLING_AND_SUBSCRIPTION_ENABLED:
        raise billing_frozen()


class StripeWebhookResponse(BaseModel):
    received: bool
    ignored: bool = False
    deduplicated: bool = False
    eventId: str
    eventType: str
    parentId: str | None = None
    billingStatus: str | None = None
    processingResult: str | None = None
    signatureVerified: bool = False
    factDisposition: str | None = None
    reconciliationDisposition: str | None = None
    activationDisposition: str | None = None


def _construct_event_then_register_provider_event(
    *,
    payload: bytes,
    signature_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Verify exact bytes, then expose only the durable registration capability."""
    event = subscription_service.construct_event(
        payload=payload,
        signature_header=signature_header,
        settings=settings,
    )
    return subscription_service.process_signed_billing_event(
        event=event,
        settings=settings,
        register_provider_event=billing_fact_repo.register_provider_event,
    )


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
@explicit_route_classification("public", "provider-signature authenticated webhook")
async def handle_stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Receive Stripe webhook events using the raw request body.

    Frozen by card 007. Stripe has never delivered an event here and no
    checkout can be created any more, so an inbound event is either replay or
    noise; accepting one would let it write billing facts nothing can produce.
    """
    refuse_if_frozen()
    payload = await request.body()
    return _construct_event_then_register_provider_event(
        payload=payload,
        signature_header=request.headers.get("stripe-signature"),
        settings=settings,
    )
