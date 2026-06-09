"""Payment provider webhook routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from stoa.config import Settings, get_settings
from stoa.services import subscription_service

router = APIRouter()


class StripeWebhookResponse(BaseModel):
    received: bool
    ignored: bool = False
    deduplicated: bool = False
    eventId: str
    eventType: str
    parentId: str | None = None
    billingStatus: str | None = None


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Receive Stripe webhook events using the raw request body."""
    payload = await request.body()
    return subscription_service.handle_stripe_webhook(
        payload=payload,
        signature_header=request.headers.get("stripe-signature"),
        settings=settings,
    )
