"""Client-side product analytics ingestion — write-only.

The route is unauthenticated, so everything a caller sends is a claim: the
`sessionId` only groups one browser's events and confers nothing. Admission is
charged against the address the gateway observed, because an open write path
without a price is an unbounded bill.

Card 134: an event is checked against `event_catalog` and stored in the
statistics table (`analytics_store`), never the main table. An event the
catalog does not list is answered 202 like any other and dropped, so the web
client never sees an error for it. A request carrying a valid token is
recorded under the account's role and pseudonym; any other is `anonymous`.
"""
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from stoa import config, deps
from stoa.db import table as db_table
from stoa.observability import analytics_store, event_catalog, features, request_metrics
from stoa.security.identity import Actor, resolve_actor
from stoa.security.route_inventory import explicit_route_classification
from stoa.security.tokens import verify_access_token
from stoa.services import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

_INGEST_SCOPE = "analytics-events"


class AnalyticsEventIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    path: str = Field(default="", max_length=512)
    sessionId: str | None = Field(default=None, max_length=128)
    createdAt: str = Field(..., max_length=64)

    model_config = {"extra": "forbid"}


def _ingest_rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "analytics_ingest_rate_limited",
            "message": "Too many analytics events from this source. Try again later.",
        },
        headers={"Retry-After": str(config.settings().analytics_ingest_window_seconds)},
    )


def admit_analytics_event(
    request: Request,
    *,
    now: datetime | None = None,
    table: object | None = None,
    scope: str = _INGEST_SCOPE,
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
        scope=scope,
        source_digest=digest,
        limit=config.settings().analytics_ingest_max_events_per_window,
        window_seconds=config.settings().analytics_ingest_window_seconds,
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
    """Record one client analytics event in the statistics table."""
    admit_analytics_event(request, table=db_table.table())
    props = (
        event_catalog.clean_props(body.name, body.payload)
        if body.name in event_catalog.CLIENT_EVENTS
        else None
    )
    if props is None:
        analytics_store.dropped("unknown_event", body.name)
        return {"status": "accepted"}
    actor = await optional_actor(request)
    analytics_store.write_event(
        body.name,
        role=actor.role.value if actor is not None else analytics_store.ANONYMOUS,
        pid=analytics_store.pseudonym(actor.user_id) if actor is not None else None,
        sid=body.sessionId or None,
        route=features.frontend_route_template(body.path),
        props=props,
        release=request_metrics.release(),
    )
    return {"status": "accepted"}


async def optional_actor(request: Request) -> Actor | None:
    """The account a valid bearer token names, or `None`; never refuses.

    Resolved by hand rather than as a dependency: the route stays public, and a
    missing, expired or revoked token only makes the event anonymous.
    """
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        settings = config.settings()
        verified = await verify_access_token(
            token.strip(),
            allowed_issuers=settings.allowed_cognito_issuers,
            allowed_client_ids=settings.allowed_cognito_access_clients,
            key_provider=deps.get_jwks_key_provider(settings),
        )
        actor = await resolve_actor(verified, deps.get_identity_repository())
    except Exception:
        return None
    return None if actor.must_change_password else actor
