"""Daily owner registry sweep: report-only (#397).

Runs on the account-deletion function, which already holds the table; its
schedule sends `{"job": "owner_registry_sweep"}`. One walk over the table checks
every account at once - rows that name an account in a partition it has not
registered, and rows a deleted account left behind - and logs what it found.
It never writes, deletes or re-queues anything, and no single deletion waits
for it. A finding is logged at WARNING as `owner_registry_sweep_findings`, the
line an alarm can match.
"""

from __future__ import annotations

import logging
from typing import Any

from stoa.services import owner_registry_sweep

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    remaining = getattr(context, "get_remaining_time_in_millis", None)
    report = owner_registry_sweep.run(
        write=False,
        remaining_seconds=(lambda: float(remaining()) / 1000.0) if callable(remaining) else None,
    )
    summary = report.as_dict()
    if not report.complete:
        logger.warning("owner_registry_sweep_incomplete rows=%d", report.rows_scanned)
    if report.unregistered or report.leftovers:
        logger.warning(
            "owner_registry_sweep_findings missing_registrations=%d leftovers=%d families=%s",
            summary["missing_registrations"],
            summary["leftover_rows"],
            sorted({*report.unregistered, *report.leftovers}),
        )
    return summary
