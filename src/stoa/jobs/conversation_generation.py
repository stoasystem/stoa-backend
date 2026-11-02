"""Generate a committed message's answer outside the request that sent it (#18).

Invoked two ways. The API invokes it asynchronously with one command's
`conversation_id` and `idempotency_key` once that command is committed (E21);
asynchronous invocation may deliver the same event more than once. The
Scheduler invokes it every five minutes with `job=conversation_generation_sweep`
to pick up what the direct invocation missed.

This only translates the Lambda event: the first shape goes to
`ask_question.answer`, the second to `ask_question.sweep`, which hold the rules.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

from stoa.services import ask_question, runtime_budget_service

logger = logging.getLogger(__name__)

SWEEP_JOB = "conversation_generation_sweep"


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    try:
        if event.get("job") == SWEEP_JOB:
            return asdict(ask_question.sweep(lambda: _remaining_seconds(context)))
        conversation_id = event.get("conversation_id")
        idempotency_key = event.get("idempotency_key")
        if (
            not isinstance(conversation_id, str)
            or not conversation_id
            or not isinstance(idempotency_key, str)
            or not idempotency_key
        ):
            # Raising would have Lambda deliver it twice more, to the same end.
            logger.error("conversation_generation_invalid_event")
            return {"outcome": "invalid_event"}
        _bind_budget(context)
        return {"outcome": ask_question.answer(conversation_id, idempotency_key)}
    finally:
        # A warm Lambda runs the next invocation in the same process; a budget
        # left bound would start that answer already out of time.
        runtime_budget_service.begin_request(started_monotonic=None, remaining_seconds=None)


def _remaining_seconds(context: Any) -> float | None:
    remaining = getattr(context, "get_remaining_time_in_millis", None)
    if not callable(remaining):
        return None
    return float(remaining()) / 1000.0


def _bind_budget(context: Any) -> None:
    """Give the next answer's deadline this Lambda's remaining time."""
    runtime_budget_service.begin_request(
        started_monotonic=time.monotonic(),
        remaining_seconds=_remaining_seconds(context),
    )
