"""Generate a committed message's answer outside the request that sent it (#18).

Invoked two ways. The API invokes it asynchronously with one command's
`conversation_id` and `idempotency_key` once that command is committed (E21);
asynchronous invocation may deliver the same event more than once. The
Scheduler invokes it every five minutes with `job=conversation_generation_sweep`
to pick up what the direct invocation missed: a command committed but never
claimed, and an attempt whose lease ran out because its Lambda died.

The sweep also settles what a command left reserved and nothing else will
settle: a `needs_reconciliation` command (the model was called, the answer
lost), a reservation kept when no time was left to call (E10) that the student
never sent again (E24), a command whose last attempt died, and one whose lease
ran out with nobody taking it up in the window (E27). It is restored with the
cost recorded at the reservation's ceiling.

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
from stoa.db.repositories import allowance_repo, attachment_repo
from stoa.routers import conversations
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.private_telemetry import emit_private_event
from stoa.services import allowance_service, runtime_budget_service

logger = logging.getLogger(__name__)

SWEEP_JOB = "conversation_generation_sweep"

# How long a committed command may wait for its direct invocation before the
# sweep takes it. The request invokes right after committing, so a minute
# covers a slow start without taking work a delivery is about to do.
_UNCLAIMED_AFTER = timedelta(seconds=60)

# The sweep answers only questions someone may still be waiting for, counted
# from the latest attempt. The chat stops waiting after six minutes, and a live
# lease is recovered within ten; an older command is left for the student's own
# retry with the same key, which still resumes it. Without this, switching the
# sweep on would answer, and charge for, every question that ever got stuck.
_SWEEP_MAX_AGE = timedelta(minutes=20)

# The sweep starts another answer only with this much of the Lambda left: the
# model's own budget is 90 seconds, and one cut short by the timeout leaves its
# lease to run out, which costs the student five minutes.
_SWEEP_MIN_REMAINING_SECONDS = 100.0

# How long a failure's reservation is left before the sweep settles it. A lost
# answer is never tried again, so two sweep runs is enough to be sure no
# attempt still holds it. A reservation kept at admission is the student's
# retry to reuse for as long as the sweep would still answer that retry.
_SETTLE_AFTER = {
    "needs_reconciliation": timedelta(minutes=10),
    "deadline_exceeded": timedelta(minutes=20),
}
assert set(_SETTLE_AFTER) == set(attachment_repo.UNSETTLED_RESERVATION_FAILURES)
# A command whose last attempt died is left two sweep runs after it is marked,
# as a lost answer is, before its reservation is settled (E27).
_SETTLE_TERMINAL_AFTER = timedelta(minutes=10)

# Settling calls no model; this is only enough for its few writes.
_SETTLE_MIN_REMAINING_SECONDS = 10.0


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
    # Of those, attempts whose lease ran out and nobody took up: each still
    # holds its reservation (ticket 15).
    stale_leases: int = 0
    missing: int = 0
    # Broke in a way nothing expected; logged, and the sweep moved on.
    errored: int = 0
    # Left for the next run: too little of this Lambda remained.
    deferred: int = 0
    # Failures whose reservation the sweep released, its cost at the ceiling.
    reconciled: int = 0


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

    A `failed` command is never generated: a failed answer is the student's to
    send again, and the command already says whether they may. Its reservation
    is settled once nothing else will.
    """
    now = datetime.now(UTC)
    commands, scanned_to_end = attachment_repo.scan_generation_sweep_commands()
    if not scanned_to_end:
        logger.warning("conversation_generation_sweep_page_limit")
    waiting = [command for command in commands if _waiting_too_long(command, now)]
    candidates = sorted(
        (command for command in waiting if _recent(command, now)),
        key=lambda command: str(command.get("created_at") or ""),
    )
    outcomes = dict.fromkeys(
        (
            "completed",
            "failed",
            "held",
            "settled",
            "missing",
            "errored",
            "deferred",
            "reconciled",
        ),
        0,
    )
    outcomes["too_old"] = len(waiting) - len(candidates)
    outcomes["stale_leases"] = sum(1 for command in waiting if _stale_lease(command, now))
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
    unsettled = sorted(
        (command for command in commands if _settlement_due(command, now)),
        key=_ended_at,
    )
    for command in unsettled:
        remaining = _remaining_seconds(context)
        if remaining is not None and remaining < _SETTLE_MIN_REMAINING_SECONDS:
            outcomes["deferred"] += 1
            continue
        try:
            outcome = settle_reservation(command)
        except Exception:
            logger.exception("conversation_generation_settlement_failed")
            outcome = "errored"
        outcomes[outcome] += 1
    summary = SweepSummary(
        scanned_to_end=scanned_to_end, candidates=len(candidates), **outcomes
    )
    logger.info(
        "conversation_generation_sweep_summary %s",
        " ".join(f"{name}={value}" for name, value in asdict(summary).items()),
    )
    return summary


def settle_reservation(command: dict[str, Any]) -> str:
    """Restore what a command left reserved, its cost at the reservation's ceiling.

    Returns `reconciled` (a reservation was released), `settled` (there was
    none left to release), `held` (the student sent it again, or another run
    settled it) or `errored` (the ledger could not settle it; the next run
    tries again). The command is first closed to retries, which would reuse the
    reservation: a failure is made not retryable, a stale lease is ended
    `terminal_failed`. It is marked settled last, so a run that stops in
    between is finished by the next.
    """
    conversation_id = command.get("conversation_id")
    idempotency_key = command.get("idempotency_key")
    owner_id = command.get("owner_id")
    read_status = command.get("status")
    if not all(
        isinstance(value, str) and value
        for value in (conversation_id, idempotency_key, owner_id)
    ):
        logger.warning("conversation_generation_settlement_unreadable")
        return "errored"
    identity = {
        "conversation_id": str(conversation_id),
        "idempotency_key": str(idempotency_key),
        "owner_id": str(owner_id),
    }
    if read_status == "ai_running":
        lease_owner = command.get("leaseOwner")
        expires_at = stored_int(command.get("expiresAt"))
        if not isinstance(lease_owner, str) or expires_at is None:
            logger.warning("conversation_generation_settlement_unreadable")
            return "errored"
        now = datetime.now(UTC)
        # Ended here: settled as the command this write makes it.
        ended_status, ended_at = "terminal_failed", now.isoformat()
        if not attachment_repo.close_stale_lease(
            **identity,
            lease_owner=lease_owner,
            expires_at=expires_at,
            now_epoch=int(now.timestamp()),
            now_iso=ended_at,
        ):
            return "held"
    else:
        ended = _ended_at(command)
        if not ended:
            logger.warning("conversation_generation_settlement_unreadable")
            return "errored"
        ended_status, ended_at = str(read_status), ended
        if ended_status == "failed" and not attachment_repo.close_failure_for_settlement(
            **identity, failed_at=ended_at
        ):
            return "held"
    effect_id = command.get("allowance_effect_id")
    released_now = False
    if isinstance(effect_id, str) and effect_id:
        released = allowance_service.release_unknown_cost_allowance(
            beneficiary_id=str(command.get("student_id") or owner_id),
            effect_id=effect_id,
        )
        if released.disposition in {
            allowance_repo.ReleaseDisposition.RETRYABLE,
            allowance_repo.ReleaseDisposition.INVALID_STATE,
        }:
            logger.warning(
                "conversation_generation_settlement_refused disposition=%s",
                released.disposition.value,
            )
            return "errored"
        released_now = released.disposition is allowance_repo.ReleaseDisposition.RELEASED
        if released_now:
            # Before the mark: a repeated alert is better than a missing one.
            emit_private_event(
                "conversation_ai_needs_reconciliation_settled",
                correlation_id=str(command.get("command_id") or ""),
                level=logging.WARNING,
            )
    if not attachment_repo.mark_allowance_settled(
        **identity,
        status=ended_status,
        ended_at=ended_at,
        now_iso=datetime.now(UTC).isoformat(),
    ):
        return "held"
    return "reconciled" if released_now else "settled"


def _settlement_due(command: dict[str, Any], now: datetime) -> bool:
    if "allowance_settled_at" in command:
        return False
    status = command.get("status")
    if status == "ai_running":
        return _stale_lease(command, now)
    if status == "terminal_failed":
        ended = _aware_time(command.get("terminal_at"))
        return ended is not None and now - ended >= _SETTLE_TERMINAL_AFTER
    if status != "failed":
        return False
    after = _SETTLE_AFTER.get(str(command.get("failure_category")))
    failed = _aware_time(command.get("failed_at"))
    return after is not None and failed is not None and now - failed >= after


def _stale_lease(command: dict[str, Any], now: datetime) -> bool:
    """A lease that ran out, and the window closed with nobody taking it up."""
    return (
        command.get("status") == "ai_running"
        and _waiting_too_long(command, now)
        and not _recent(command, now)
    )


def _ended_at(command: dict[str, Any]) -> str:
    """When an ended command reached its end, as written; empty if it has none."""
    field = attachment_repo.SETTLEMENT_ENDED_AT.get(str(command.get("status")))
    ended = command.get(field) if field else None
    return ended if isinstance(ended, str) else ""


def _recent(command: dict[str, Any], now: datetime) -> bool:
    """Last tried within `_SWEEP_MAX_AGE`; an unreadable time counts as old.

    A running attempt is aged from its claim and a waiting command from when it
    was committed (or sent again), so a third attempt claimed late in the
    window is still taken up when its lease runs out. `created_at` is only the
    fallback for a command that carries neither.
    """
    if command.get("status") == "ai_running":
        claimed = stored_int(command.get("claimedAt"))
        if claimed is not None:
            return now - datetime.fromtimestamp(claimed, UTC) <= _SWEEP_MAX_AGE
    elif command.get("message_committed_at") is not None:
        committed = _aware_time(command.get("message_committed_at"))
        return committed is not None and now - committed <= _SWEEP_MAX_AGE
    asked = _aware_time(command.get("created_at"))
    return asked is not None and now - asked <= _SWEEP_MAX_AGE


def _aware_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


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
