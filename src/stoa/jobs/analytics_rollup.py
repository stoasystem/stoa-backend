"""Fold a day of usage events into rollup rows (card 134).

Scheduled once a day for the day before (UTC). `{"day": "yyyy-mm-dd"}` folds that
day instead, and `{"days": n}` the n days before today; folding a day again
replaces its rows.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from stoa.observability import analytics_store, usage_stats

logger = logging.getLogger(__name__)

MAX_BACKFILL_DAYS = 90


def target_days(event: dict[str, Any] | None, *, now: datetime | None = None) -> list[str]:
    event = event or {}
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    if event.get("day"):
        return [date.fromisoformat(str(event["day"])).isoformat()]
    count = int(event.get("days") or 1)
    if not 1 <= count <= MAX_BACKFILL_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_BACKFILL_DAYS}")
    return [(today - timedelta(days=offset)).isoformat() for offset in range(count, 0, -1)]


def run(event: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    target = analytics_store.table()
    if target is None:
        logger.info("analytics_rollup_skipped reason=table_not_configured")
        return {"status": "skipped", "reason": "table_not_configured"}
    results = [usage_stats.write_rollup(day, target=target, now=now) for day in target_days(event, now=now)]
    logger.info("analytics_rollup_done days=%s", ",".join(result["day"] for result in results))
    return {"status": "completed", "days": results}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Lambda handler for the scheduled analytics rollup."""
    try:
        return run(event)
    except Exception:
        logger.exception("Analytics rollup failed")
        raise
