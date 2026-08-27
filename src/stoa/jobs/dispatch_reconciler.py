"""Keep every student who asked for a teacher attached to one.

Asking for a human teacher dispatches the question inside the request. When
that fails, or when the teacher it reached never accepts, nothing else was
watching and the student waited on nobody. This runs on a schedule and puts
those questions back in front of a teacher.
"""

from __future__ import annotations

import logging
from typing import Any

from stoa.services import teacher_dispatch_service

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Lambda handler for the scheduled dispatch sweep."""
    try:
        outcome = teacher_dispatch_service.reconcile_dispatches()
    except Exception:  # noqa: BLE001
        # A failed sweep must be visible; the schedule will try again, but a
        # silent failure here is how the gap it closes went unnoticed.
        logger.exception("Dispatch reconciliation failed")
        raise

    logger.info(
        "Dispatch reconciliation: %s reassigned, %s questions waiting, "
        "%s re-offered, %s chats waiting, %s chats re-offered",
        outcome["reassigned"],
        outcome["waiting"],
        len(outcome["dispatched"]),
        outcome.get("conversationsWaiting", 0),
        len(outcome.get("conversationsDispatched", [])),
    )
    return {
        "status": "completed",
        "reassigned": outcome["reassigned"],
        "waiting": outcome["waiting"],
        "dispatched": len(outcome["dispatched"]),
        "conversationsWaiting": outcome.get("conversationsWaiting", 0),
        "conversationsDispatched": len(outcome.get("conversationsDispatched", [])),
        "generatedAt": outcome["generatedAt"],
    }
