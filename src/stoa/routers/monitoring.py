"""Frontend error reports (`frontendErrorMonitoring.ts`), card 134.

The web client has posted its uncaught errors here since it shipped; the route
did not exist. Public like `/analytics/events` and charged the same way, per
observed source. A report becomes one `frontend_error` event in the statistics
table and one EMF line (`Stoa/Frontend`, `FrontendErrors` by feature). The
message is cut and hashed, the stack cut to eight frames without query strings,
and the route reduced to its shape.
"""

from __future__ import annotations

import hashlib
import logging
import re

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field

from stoa.db import table as db_table
from stoa.observability import analytics_store, event_catalog, features, request_metrics
from stoa.routers.analytics import admit_analytics_event, optional_actor
from stoa.security.route_inventory import explicit_route_classification

logger = logging.getLogger(__name__)

router = APIRouter()

_INGEST_SCOPE = "frontend-errors"
_MAX_FRAMES = 8
_MAX_FRAME_LENGTH = 300
_QUERY = re.compile(r"\?[^\s)]*")
# What a report keeps of its error: the kind, never the text. A message can hold
# an email, a child's words or an address the browser was on (card 134 audit);
# its hash still groups the reports.
_ERROR_KIND = re.compile(r"^[A-Z][A-Za-z]{0,63}$")
# A frame names code: Chrome's "at fn (url:1:2)", Firefox's and Safari's "fn@url:1:2".
_FRAME = re.compile(r"^\s*at\s|@\S+:\d+:\d+")


class FrontendErrorIn(BaseModel):
    appEnv: str = Field(default="", max_length=64)
    componentStack: str | None = Field(default=None, max_length=20000)
    errorId: str = Field(default="", max_length=128)
    message: str = Field(default="", max_length=4000)
    name: str = Field(default="", max_length=512)
    route: str = Field(default="", max_length=2048)
    source: str = Field(default="manual", max_length=64)
    stack: str | None = Field(default=None, max_length=20000)
    timestamp: str = Field(default="", max_length=64)

    # The client may grow a field before this does; it is ignored, not refused.
    model_config = ConfigDict(extra="ignore")


def message_hash(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]


def error_kind(name: str) -> str:
    """The error's class name when it is one, else "Error"."""
    name = name.strip()
    return name if _ERROR_KIND.fullmatch(name) else "Error"


def trimmed_stack(stack: str | None) -> str | None:
    """The first eight frames, each without a query string and cut to 300."""
    if not stack:
        return None
    frames = [
        _QUERY.sub("", line).strip()[:_MAX_FRAME_LENGTH]
        for line in stack.splitlines()
        if _FRAME.search(line)
    ][:_MAX_FRAMES]
    return "\n".join(frames) or None


@router.post("/frontend-errors", status_code=status.HTTP_202_ACCEPTED)
@explicit_route_classification(
    "public",
    "anonymous-tolerant frontend error reports; the client strips tokens before sending",
)
async def report_frontend_error(body: FrontendErrorIn, request: Request):
    """Record one frontend error report."""
    admit_analytics_event(request, table=db_table.table(), scope=_INGEST_SCOPE)
    route = features.frontend_route_template(body.route)
    feature = features.feature_for_frontend_route(route)
    release = request_metrics.release()
    message = body.message.strip()
    try:
        request_metrics.write_line(
            request_metrics.emf_line(
                request_metrics.FRONTEND_NAMESPACE,
                {"FrontendErrors": (1, "Count")},
                feature=feature,
                properties={"route": route, "release": release, "source": body.source[:32]},
            )
        )
    except Exception:
        logger.warning("frontend_error_metric_failed", exc_info=True)
    actor = await optional_actor(request)
    props = event_catalog.clean_props(
        "frontend_error",
        {
            "route": route,
            "message_hash": message_hash(message),
            "release": release,
            "message": error_kind(body.name),
            "name": body.name,
            "source": body.source,
            "stack": trimmed_stack(body.stack),
        },
    )
    analytics_store.write_event(
        "frontend_error",
        role=actor.role.value if actor is not None else analytics_store.ANONYMOUS,
        pid=analytics_store.pseudonym(actor.user_id) if actor is not None else None,
        sid=None,
        route=route,
        props=props or {},
        release=release,
    )
    return {"status": "accepted"}
