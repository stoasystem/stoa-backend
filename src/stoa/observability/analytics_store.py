"""The statistics table: usage events, daily actives and first appearances (card 134).

A table of its own (`ANALYTICS_TABLE_NAME`), never the main table: with no name
configured an event is dropped and counted in the log, nothing is written. Three
kinds of row, all with a `ttl`:

- `PK=DAY#<yyyy-mm-dd>`, `SK=<iso ts>#<uuid4>`: the event (90 days).
- `PK=ACTIVE#<yyyy-mm-dd>`, `SK=<role>#<pid>`: the pseudonym was active that
  day (400 days), written over by each of its events.
- `PK=FIRST#<pid>`, `SK=FIRST`: the day the pseudonym was first seen (2
  years), written once.

A row names a person only by `pid`, an HMAC of the account id under
`ANALYTICS_PSEUDONYM_KEY`; with no key there is no `pid`, only the browser
session `sid`. Never the account id, an email, a name or what a student wrote.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from stoa import config
from stoa.db import table as db_table

logger = logging.getLogger(__name__)

EVENT_TTL = timedelta(days=90)
ACTIVE_TTL = timedelta(days=400)
FIRST_TTL = timedelta(days=730)
ANONYMOUS = "anonymous"

_installed: object | None = None


def install(double: object | None) -> None:
    """Put `double` where the statistics table would be; `None` takes it away."""
    global _installed
    _installed = double


@lru_cache
def _real_table(name: str) -> object:
    # The gateway's resource, a table of its own: the main table's gateway is not used.
    return db_table._resource().Table(name)


def table() -> object | None:
    """The statistics table, or `None` when none is configured."""
    if _installed is not None:
        return _installed
    name = config.settings().analytics_table_name.strip()
    return _real_table(name) if name else None


def pseudonym(user_id: str | None) -> str | None:
    """The first 16 hex digits of HMAC-SHA256(key, user_id); `None` without a key."""
    key = config.settings().analytics_pseudonym_key
    if not key or not user_id:
        return None
    digest = hmac.new(key.encode("utf-8"), str(user_id).encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:16]


def dropped(reason: str, name: str) -> None:
    """Count one event that was not stored: one log line."""
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in name)[:64]
    logger.info("event_category=analytics_event_dropped reason=%s name=%s", reason, safe or "-")


def write_event(
    name: str,
    *,
    role: str,
    pid: str | None,
    sid: str | None,
    route: str,
    props: dict[str, Any],
    release: str,
    now: datetime | None = None,
) -> bool:
    """Store one event already checked against the catalog; never raises."""
    target = table()
    if target is None:
        dropped("table_not_configured", name)
        return False
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    day = moment.date().isoformat()
    epoch = int(moment.timestamp())
    try:
        _put_event(target, name, role, pid, sid, route, props, release, moment, day, epoch)
        if pid:
            # Only the pseudonym's first event of the day can be its first ever.
            if _mark_active(target, role, pid, moment, day, epoch):
                _mark_first(target, role, pid, day, epoch)
    except Exception as error:
        logger.warning(
            "event_category=analytics_event_dropped reason=write_failed error=%s",
            type(error).__name__,
        )
        return False
    return True


def _put_event(
    target: Any,
    name: str,
    role: str,
    pid: str | None,
    sid: str | None,
    route: str,
    props: dict[str, Any],
    release: str,
    moment: datetime,
    day: str,
    epoch: int,
) -> None:
    item: dict[str, Any] = {
        "PK": f"DAY#{day}",
        "SK": f"{moment.isoformat()}#{uuid.uuid4()}",
        "entity_type": "analytics_event",
        "name": name,
        "role": role,
        "pid": pid,
        "sid": sid,
        "route": route,
        "props": props,
        "release": release,
        "ttl": epoch + int(EVENT_TTL.total_seconds()),
    }
    target.put_item(Item={key: value for key, value in item.items() if value is not None})


def _mark_active(target: Any, role: str, pid: str, moment: datetime, day: str, epoch: int) -> bool:
    """Mark the day; whether this was the pseudonym's first event of it."""
    response = target.update_item(
        Key={"PK": f"ACTIVE#{day}", "SK": f"{role}#{pid}"},
        UpdateExpression=(
            "SET first_event_at = if_not_exists(first_event_at, :now), "
            "last_event_at = :now, #role = :role, pid = :pid, #ttl = :ttl"
        ),
        ExpressionAttributeNames={"#role": "role", "#ttl": "ttl"},
        ExpressionAttributeValues={
            ":now": moment.isoformat(),
            ":role": role,
            ":pid": pid,
            ":ttl": epoch + int(ACTIVE_TTL.total_seconds()),
        },
        ReturnValues="UPDATED_OLD",
    )
    old = (response or {}).get("Attributes") if isinstance(response, dict) else None
    return not (isinstance(old, dict) and "first_event_at" in old)


def _mark_first(target: Any, role: str, pid: str, day: str, epoch: int) -> None:
    try:
        db_table.put(
            table=target,
            Item={
                "PK": f"FIRST#{pid}",
                "SK": "FIRST",
                "first_day": day,
                "first_role": role,
                "ttl": epoch + int(FIRST_TTL.total_seconds()),
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
    except db_table.WriteRefused:
        # Already marked: the first day stays the first one.
        return
