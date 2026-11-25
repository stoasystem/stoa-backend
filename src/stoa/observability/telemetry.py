"""Business events the backend records itself (card 134).

`record` takes the acting account's id only to turn it into its pseudonym;
the id itself is never stored. A failure is logged and swallowed: counting a
question never stands in the way of answering it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from stoa.observability import analytics_store, event_catalog, request_metrics

logger = logging.getLogger(__name__)


def record(
    event: str,
    *,
    actor_user_id: str | None,
    role: str | None,
    route: str = "",
    now: datetime | None = None,
    **props: Any,
) -> None:
    try:
        if event not in event_catalog.SERVER_EVENTS:
            analytics_store.dropped("unknown_event", event)
            return
        analytics_store.write_event(
            event,
            role=str(role or analytics_store.ANONYMOUS),
            pid=analytics_store.pseudonym(actor_user_id),
            sid=None,
            route=route,
            props=event_catalog.clean_props(event, props) or {},
            release=request_metrics.release(),
            now=now,
        )
    except Exception as error:
        logger.warning("telemetry_record_failed event=%s error=%s", event, type(error).__name__)


def elapsed_ms(since: object, now: datetime) -> int | None:
    """Milliseconds from an ISO timestamp to `now`, or `None` when unreadable."""
    if not isinstance(since, str) or not since:
        return None
    try:
        start = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if start.tzinfo is None or now.tzinfo is None:
            return None
        return max(0, int((now - start).total_seconds() * 1000))
    except (TypeError, ValueError):
        return None


def since_ms(since: object) -> int | None:
    return elapsed_ms(since, datetime.now(UTC))
