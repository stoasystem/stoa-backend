"""Client-side product analytics ingestion — write-only, no read API yet.

The frontend has posted here since day one; the route never existed, so every
`trackEvent(...)` call (login timing included) has been silently 404ing.

The route is unauthenticated, so everything a caller sends is a claim: the
`sessionId` only groups one browser's events and confers nothing. Admission is
charged against the address the gateway observed, and the stored row is bounded,
because an open write path with neither is an unbounded bill.
"""
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from stoa.config import settings
from stoa.db.dynamodb import get_table
from stoa.security.route_inventory import explicit_route_classification
from stoa.services import rate_limit

router = APIRouter()

_EVENT_TTL_SECONDS = 90 * 24 * 60 * 60
_INGEST_SCOPE = "analytics-events"
_MAX_PAYLOAD_KEY_LENGTH = 64

_DROPPED = object()


class AnalyticsEventIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    path: str = Field(default="", max_length=512)
    sessionId: str | None = Field(default=None, max_length=128)
    createdAt: str = Field(..., max_length=64)

    model_config = {"extra": "forbid"}


def _dynamo_safe(value: Any) -> Any:
    # DynamoDB refuses Python floats. Lists and maps are dropped rather than
    # stored: the frontend only ever sends string/number/boolean/null, so a
    # nested structure here is somebody else's client, and nesting is how one
    # request turns into a 400 KB row.
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value[: settings.analytics_payload_max_value_length]
    return _DROPPED


def _bounded_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return the storable payload and whether anything was dropped or cut."""
    bounded: dict[str, Any] = {}
    truncated = False
    for key, value in payload.items():
        if len(bounded) >= settings.analytics_payload_max_entries:
            truncated = True
            break
        safe_key = str(key)[:_MAX_PAYLOAD_KEY_LENGTH]
        safe_value = _dynamo_safe(value)
        if safe_value is _DROPPED:
            truncated = True
            continue
        if safe_key != str(key) or (isinstance(value, str) and safe_value != value):
            truncated = True
        bounded[safe_key] = safe_value
    return bounded, truncated


def _ingest_rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "analytics_ingest_rate_limited",
            "message": "Too many analytics events from this source. Try again later.",
        },
        headers={"Retry-After": str(settings.analytics_ingest_window_seconds)},
    )


def admit_analytics_event(
    request: Request, *, now: datetime | None = None, table: object | None = None
) -> None:
    """Charge one write to the caller's source window before anything is stored.

    The bucket key is the address the gateway observed, never the `sessionId` the
    caller chose: a limit keyed on caller-supplied bytes is a limit the caller
    lifts by picking new bytes.
    """
    try:
        digest = rate_limit.client_source_digest(request)
    except rate_limit.ProxyTopologyError as exc:
        raise _ingest_rate_limited() from exc
    admitted = rate_limit.admit_source_window(
        scope=_INGEST_SCOPE,
        source_digest=digest,
        limit=settings.analytics_ingest_max_events_per_window,
        window_seconds=settings.analytics_ingest_window_seconds,
        now=now,
        table=table,
    )
    if not admitted:
        raise _ingest_rate_limited()


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
async def ingest_event(body: AnalyticsEventIn, request: Request):
    """Record one client analytics event for later CloudWatch Logs Insights / table queries."""
    table = get_table()
    admit_analytics_event(request, table=table)
    session_id = body.sessionId or "anon"
    received_at = datetime.now(timezone.utc).isoformat()
    payload, payload_truncated = _bounded_payload(body.payload)
    table.put_item(
        Item={
            "PK": f"ANALYTICSEVENT#{session_id}",
            "SK": f"{received_at}#{uuid.uuid4()}",
            "entity_type": "analytics_event",
            "name": body.name,
            "payload": payload,
            "payload_truncated": payload_truncated,
            "path": body.path,
            "session_id": session_id,
            "client_created_at": body.createdAt,
            "received_at": received_at,
            "expires_at": int(time.time()) + _EVENT_TTL_SECONDS,
        }
    )
    return {"status": "accepted"}
