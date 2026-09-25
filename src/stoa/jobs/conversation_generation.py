"""Generate a committed message's answer outside the request that sent it (#18).

Invoked two ways. The API invokes it asynchronously with one command's
`conversation_id` and `idempotency_key` once that command is committed (E21);
asynchronous invocation may deliver the same event more than once. The
Scheduler invokes it every five minutes with `job=conversation_generation_sweep`
to pick up what the direct invocation missed: a command committed but never
claimed, and an attempt whose lease ran out because its Lambda died.

Either way the work is `conversations.generate_for_command`, which claims the
command's lease conditionally, so a duplicate delivery finds the lease held or
the answer stored and leaves. How an attempt that ran out is recovered - again,
finished from the answer it kept, or `needs_reconciliation` - is decided there
too, the same for the worker and for a student retrying the same message.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from stoa.db.dynamodb import stored_int
from stoa.db.repositories import attachment_repo
from stoa.routers import conversations
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import runtime_budget_service

logger = logging.getLogger(__name__)

SWEEP_JOB = "conversation_generation_sweep"

# How long a committed command may wait for its direct invocation before the
# sweep takes it. The request invokes right after committing, so a minute
# covers a slow start without taking work a delivery is about to do.
_UNCLAIMED_AFTER = timedelta(seconds=60)

# The sweep answers only questions someone may still be waiting for. The chat
# stops waiting after six minutes, and a live lease is recovered within ten; an
# older command is left for the student's own retry with the same key, which
# still resumes it. Without this, switching the sweep on would answer, and
# charge for, every question that ever got stuck.
_SWEEP_MAX_AGE = timedelta(minutes=20)

# The sweep starts another answer only with this much of the Lambda left: the
# model's own budget is 90 seconds, and one cut short by the timeout leaves its
# lease to run out, which costs the student five minutes.
_SWEEP_MIN_REMAINING_SECONDS = 100.0


@dataclass(frozen=True, slots=True)
class SweepSummary:
    scanned_to_end: bool = True
    candidates: int = 0
    completed: int = 0
    failed: int = 0
    held: int = 0
    settled: int = 0
    # Waiting, but asked too long ago for anyone to be waiting for the answer.
    too_old: int = 0
    missing: int = 0
    # Broke in a way nothing expected; logged, and the sweep moved on.
    errored: int = 0
    # Left for the next run: too little of this Lambda remained.
    deferred: int = 0


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    event = event or {}
    try:
        if event.get("job") == SWEEP_JOB:
            return asdict(run_sweep(context))
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
        return {"outcome": generate_one(conversation_id, idempotency_key)}
    finally:
        # A warm Lambda runs the next invocation in the same process; a budget
        # left bound would start that answer already out of time.
        runtime_budget_service.begin_request(started_monotonic=None, remaining_seconds=None)


def generate_one(conversation_id: str, idempotency_key: str) -> str:
    """Take one command to its answer if it still needs one.

    Returns `completed`, `failed` (the command says why), `held` (another
    delivery holds its lease), `settled` (it needs nothing) or `missing`.
    """
    command = attachment_repo.get_message_command(conversation_id, idempotency_key)
    if not isinstance(command, dict):
        return "missing"
    if command.get("status") == "failed":
        # Whether it may be tried again is the student's to act on, with the
        # same key (the request reopens it); a late or repeated delivery must
        # not spend their attempts.
        return "settled"
    fingerprint = command.get("fingerprint")
    owner_id = command.get("owner_id")
    if not isinstance(fingerprint, str) or not isinstance(owner_id, str):
        return "settled"
    state = attachment_repo.classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=int(datetime.now(UTC).timestamp()),
    )
    if state.disposition is attachment_repo.MessageCommandDisposition.LEASE_HELD:
        return "held"
    if state.disposition is not attachment_repo.MessageCommandDisposition.RESUME:
        return "settled"
    try:
        committed = conversations.load_committed_message(command)
        conversations.generate_for_command(committed)
    except AttachmentDecisionError as error:
        if error.code is AttachmentErrorCode.MESSAGE_IN_PROGRESS:
            return "held"
        logger.warning("conversation_generation_failed code=%s", error.code.value)
        return "failed"
    except conversations._ConversationAllowanceFailure as failure:
        logger.warning("conversation_generation_failed code=%s", failure.code)
        return "failed"
    return "completed"


def run_sweep(context: Any) -> SweepSummary:
    """Generate what nobody claimed and what a dead attempt left, oldest first.

    A `failed` command is left alone: a failed answer is the student's to send
    again, and the command already says whether they may.
    """
    now = datetime.now(UTC)
    commands, scanned_to_end = attachment_repo.scan_waiting_generation_commands()
    if not scanned_to_end:
        logger.warning("conversation_generation_sweep_page_limit")
    waiting = [command for command in commands if _waiting_too_long(command, now)]
    candidates = sorted(
        (command for command in waiting if _recent(command, now)),
        key=lambda command: str(command.get("created_at") or ""),
    )
    outcomes = dict.fromkeys(
        ("completed", "failed", "held", "settled", "missing", "errored", "deferred"), 0
    )
    outcomes["too_old"] = len(waiting) - len(candidates)
    for command in candidates:
        remaining = _remaining_seconds(context)
        if remaining is not None and remaining < _SWEEP_MIN_REMAINING_SECONDS:
            outcomes["deferred"] += 1
            continue
        _bind_budget(context)
        try:
            outcome = generate_one(
                str(command.get("conversation_id") or ""),
                str(command.get("idempotency_key") or ""),
            )
        except Exception:
            # One command must not hold up the rest; a raised run would be
            # retried whole by the Scheduler, the same command first.
            logger.exception("conversation_generation_sweep_command_failed")
            outcome = "errored"
        outcomes[outcome] += 1
    return SweepSummary(
        scanned_to_end=scanned_to_end, candidates=len(candidates), **outcomes
    )


def _recent(command: dict[str, Any], now: datetime) -> bool:
    """Asked within `_SWEEP_MAX_AGE`; an unreadable time counts as old."""
    try:
        asked = datetime.fromisoformat(str(command.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if asked.tzinfo is None:
        return False
    return now - asked <= _SWEEP_MAX_AGE


def _waiting_too_long(command: dict[str, Any], now: datetime) -> bool:
    status = command.get("status")
    if status == "ai_running":
        lease_expiry = stored_int(command.get("expiresAt"))
        return lease_expiry is not None and lease_expiry <= int(now.timestamp())
    if status != "message_committed":
        return False
    committed_at = command.get("message_committed_at")
    try:
        committed = datetime.fromisoformat(str(committed_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if committed.tzinfo is None:
        return True
    return now - committed >= _UNCLAIMED_AFTER


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
