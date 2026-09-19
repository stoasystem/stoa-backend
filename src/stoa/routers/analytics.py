"""Client-side product analytics ingestion — write-only, no read API yet.

The frontend has posted here since day one; the route never existed, so every
`trackEvent(...)` call (login timing included) has been silently 404ing.
"""
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from stoa.db.dynamodb import get_table
from stoa.security.route_inventory import explicit_route_classification

router = APIRouter()

_EVENT_TTL_SECONDS = 90 * 24 * 60 * 60


class AnalyticsEventIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    path: str = Field(default="", max_length=512)
    sessionId: str | None = Field(default=None, max_length=128)
    createdAt: str = Field(..., max_length=64)

    model_config = {"extra": "forbid"}


def _dynamo_safe(value: Any) -> Any:
    # DynamoDB refuses Python floats; the frontend only ever sends
    # string/number/boolean/null, so this is the full range to convert.
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return value


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
@explicit_route_classification(
    "public",
    "anonymous-tolerant analytics ingestion; frontend strips free-text fields before sending",
    # sessionId is minted by the browser and is nobody's account id: it only
    # groups one visitor's events. The inventory still demands it be declared,
    # because an undeclared identifier on a public route is how a real one
    # would slip in unnoticed.
    allowed_identifiers=("sessionId",),
    identifier_scope="command-local",
)
async def ingest_event(body: AnalyticsEventIn):
    """Record one client analytics event for later CloudWatch Logs Insights / table queries."""
    session_id = body.sessionId or "anon"
    received_at = datetime.now(timezone.utc).isoformat()
    table = get_table()
    table.put_item(
        Item={
            "PK": f"ANALYTICSEVENT#{session_id}",
            "SK": f"{received_at}#{uuid.uuid4()}",
            "entity_type": "analytics_event",
            "name": body.name,
            "payload": {key: _dynamo_safe(value) for key, value in body.payload.items()},
            "path": body.path,
            "session_id": session_id,
            "client_created_at": body.createdAt,
            "received_at": received_at,
            "expires_at": int(time.time()) + _EVENT_TTL_SECONDS,
        }
    )
    return {"status": "accepted"}
