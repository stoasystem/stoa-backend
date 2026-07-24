"""Payment provider webhook routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from stoa.config import Settings, get_settings
from stoa.db.repositories import billing_fact_repo
from stoa.services import subscription_service
from stoa.security.route_inventory import explicit_route_classification

router = APIRouter()


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
    """Receive Stripe webhook events using the raw request body."""
    payload = await request.body()
    return _construct_event_then_register_provider_event(
        payload=payload,
        signature_header=request.headers.get("stripe-signature"),
        settings=settings,
    )
