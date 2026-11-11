"""Scheduled discovery and continuation for durable account deletion commands.

Discovery has two halves (#397). Every command accepted since the pending
registry exists has a row in `ACCOUNT_DELETION_PENDING`, and one strong query of
that partition finds all of them on every run. Commands accepted before it - the
ones in flight when it was deployed - have none, so the old cursor scan still
runs too, and writes the missing registry row for each command it finds; from
the next run on those are found by the query as well. The scan can go once no
command without a row is left.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping
from uuid import uuid4

from stoa.db.repositories import account_deletion_repo
from stoa.services.account_deletion_service import AccountDeletionService


logger = logging.getLogger(__name__)


# Everything the sweep calls. A repository without one of these is refused
# before anything is read: a double missing the cursor methods used to get the
# old start-from-the-top behaviour silently, which is the bug #7 describes.
_REQUIRED_REPOSITORY_METHODS = (
    "get_deletion_scan_cursor",
    "advance_deletion_scan_cursor",
    "scan_pending_deletion_commands",
    "claim_deletion_command",
)


# How many consecutive runs a failing command may keep the sweep in place. The
# next run after that still tries the slice first, and moves past it if the
# command fails again; the command itself is left exactly as it is, for the
# request-side continuation or a later cycle to finish (ticket 12).
_HOLD_LIMIT = 3


# Below this much remaining Lambda time a run claims no further command.
MIN_REMAINING_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class DeletionJobSummary:
    discovered: int = 0
    claimed: int = 0
    continued: int = 0
    retryable: int = 0


def _registered_commands(repository: Any) -> list[dict[str, Any]]:
    """The commands the pending registry names, each read by its key.

    A row whose command is finished or gone is dropped on the way. A registry
    that cannot be read is logged, not fatal: the scan below still runs.
    """
    lister = getattr(repository, "list_pending_deletions", None)
    loader = getattr(repository, "get_deletion_command", None)
    if not callable(lister) or not callable(loader):
        return []
    try:
        entries = lister()
    except Exception:
        logger.warning("account_deletion_registry_unavailable")
        return []
    commands: list[dict[str, Any]] = []
    for entry in entries:
        try:
            command = loader(entry.user_id, entry.command_id)
        except Exception:
            logger.warning(
                "account_deletion_registry_read_failed command_id=%s", entry.command_id
            )
            continue
        if not command or command.get("status") not in {"pending", "running"}:
            unregister = getattr(repository, "unregister_pending_deletion", None)
            if callable(unregister):
                try:
                    unregister(user_id=entry.user_id, command_id=entry.command_id)
                except Exception:
                    pass
            continue
        commands.append(dict(command))
    return commands


def _backfill_registry(repository: Any, commands: list[dict[str, Any]]) -> None:
    """Register the scanned commands accepted before the registry existed."""
    register = getattr(repository, "register_pending_deletion", None)
    if not callable(register):
        return
    for command in commands:
        user_id = command.get("user_id")
        command_id = command.get("command_id")
        if not isinstance(user_id, str) or not user_id:
            continue
        if not isinstance(command_id, str) or not command_id:
            continue
        try:
            register(
                user_id=user_id,
                command_id=command_id,
                accepted_at=command.get("accepted_at"),
            )
        except Exception:
            logger.warning("account_deletion_registry_backfill_failed command_id=%s", command_id)


def _claim(repository: Any, command: Mapping[str, Any]) -> Any:
    """Claim one command on the clock as it is now, not as the run began.

    A run now lasts minutes; a lease timed from its start would already have
    run out for a command claimed late in it.
    """
    now = datetime.now(UTC)
    return repository.claim_deletion_command(
        command,
        lease_owner=uuid4().hex,
        now_epoch=int(now.timestamp()),
        lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
        now_iso=now.isoformat(),
    )


def run_pending_deletions(
    *,
    repository: Any = account_deletion_repo,
    service_factory: Callable[[], Any] | None = None,
    limit: int = 25,
    remaining_seconds: Callable[[], float] | None = None,
) -> DeletionJobSummary:
    missing = [
        name
        for name in _REQUIRED_REPOSITORY_METHODS
        if not callable(getattr(repository, name, None))
    ]
    if missing:
        raise account_deletion_repo.AccountDeletionConflict(
            f"deletion repository lacks {', '.join(missing)}"
        )
    now = datetime.now(UTC)
    # One run reads a bounded slice of the table, so it starts where the last
    # run stopped. Without this every run read the same first slice, and a
    # command further down was never reached by the schedule (#7).
    place = repository.get_deletion_scan_cursor()
    commands: list[dict[str, Any]] = []
    cursor: dict[str, str] | None = place.cursor
    # The starting place counts as seen: a page that hands it back again is
    # going round in a circle, not moving on.
    seen_cursors: set[tuple[str, str]] = (
        {(cursor["PK"], cursor["SK"])} if cursor is not None else set()
    )
    unfinished = False
    # A continuation key the scan should never hand back; where it points is
    # not a place worth keeping.
    anomalous = False
    pages = 0
    while len(commands) < limit and pages < 100:
        pages += 1
        page_limit = max(limit - len(commands), 1)
        page = repository.scan_pending_deletion_commands(limit=page_limit, cursor=cursor)
        items, next_cursor = list(page.items), page.cursor
        commands.extend(dict(item) for item in items[:page_limit])
        if next_cursor is None:
            cursor = None
            break
        if (
            not isinstance(next_cursor, dict)
            or set(next_cursor) != {"PK", "SK"}
            or not all(
                isinstance(next_cursor.get(field), str) and next_cursor[field]
                for field in ("PK", "SK")
            )
        ):
            unfinished = anomalous = True
            break
        identity = (next_cursor["PK"], next_cursor["SK"])
        if identity in seen_cursors:
            unfinished = anomalous = True
            break
        seen_cursors.add(identity)
        cursor = next_cursor
    # Running out of scan budget is not the same as having nothing to do.
    # `Limit` is applied before the filter, so a page reads that many rows
    # and yields the deletion commands among them - on a table of any size
    # the budget runs out long before twenty-five of them are found. This
    # returned early and threw the commands it had already found away, so
    # every deletion stopped after the one pass the request itself did.
    if len(commands) < limit and cursor is not None and pages >= 100:
        unfinished = True
    _backfill_registry(repository, commands)
    # Registered commands first, then whatever the scan found that is not
    # among them; each command is handled once per run.
    scanned_ids = {str(command.get("command_id") or "") for command in commands}
    registered = [
        command
        for command in _registered_commands(repository)
        if str(command.get("command_id") or "") not in scanned_ids
    ]
    worker = (
        service_factory
        or (lambda: AccountDeletionService(remaining_seconds=remaining_seconds))
    )()
    claimed = continued = retryable = 0
    failed_command_ids: list[str] = []
    for command in registered:
        if remaining_seconds is not None and remaining_seconds() < MIN_REMAINING_SECONDS:
            unfinished = True
            break
        try:
            claim = _claim(repository, command)
            if not claim:
                continue
            claimed += 1
            worker.continue_command(claim)
            continued += 1
        except Exception:
            # Found again by the next run's query; it does not hold the scan.
            unfinished = True
    for command in commands:
        if remaining_seconds is not None and remaining_seconds() < MIN_REMAINING_SECONDS:
            # Not attempted is not failed, and the place need not hold for it:
            # the registry row written above finds it on the next run.
            unfinished = True
            continue
        try:
            claim = _claim(repository, command)
            if not claim:
                # Another run holds it; that is progress, not failure.
                continue
            claimed += 1
            worker.continue_command(claim)
            continued += 1
        except Exception:
            retryable += 1
            failed_command_ids.append(str(command.get("command_id") or ""))
    # Only after every command found here has been dealt with: a run that ends
    # before this line leaves the stored place where it was, and the next run
    # reads the same slice again. A command that failed holds the place too, so
    # the next run retries it in five minutes rather than a whole cycle later.
    # Reaching the end of the table starts the next cycle from the top. A write
    # refused because another run stored a place first is fine; that run's
    # place stands.
    # The cycle started when its first run stored anything; a hold at the very
    # start of a cycle stores the start time too, and later runs keep it.
    cycle_started_at = place.cycle_started_at or now.isoformat()
    if anomalous:
        logger.warning(
            "account_deletion_scan_anomaly version=%s reason=continuation_key",
            place.version,
        )
    elif retryable and place.held_runs < _HOLD_LIMIT:
        # A write lost to another run on the same version is not counted.
        repository.advance_deletion_scan_cursor(
            expected_version=place.version,
            cursor=place.cursor,
            cycle_started_at=cycle_started_at,
            updated_at=now.isoformat(),
            held_runs=place.held_runs + 1,
        )
        logger.warning(
            "account_deletion_scan_held version=%s failed_commands=%s held_runs=%s",
            place.version,
            retryable,
            place.held_runs + 1,
        )
    else:
        if retryable:
            logger.warning(
                "account_deletion_scan_skipped version=%s held_runs=%s command_ids=%s",
                place.version,
                place.held_runs,
                ",".join(failed_command_ids),
            )
        stored = repository.advance_deletion_scan_cursor(
            expected_version=place.version,
            cursor=cursor,
            cycle_started_at=None if cursor is None else cycle_started_at,
            updated_at=now.isoformat(),
            held_runs=0,
        )
        if stored and cursor is None:
            # Taken after the reset is stored, not at entry: the scan and the
            # claims in between are part of the cycle.
            completed = datetime.now(UTC)
            started = datetime.fromisoformat(cycle_started_at)
            logger.info(
                "account_deletion_scan_cycle_completed version=%s completed_at=%s "
                "duration_seconds=%s",
                (place.version or 0) + 1,
                completed.isoformat(),
                int((completed - started).total_seconds()),
            )
    # A sweep that stopped short says so, so the next run knows to come back.
    return DeletionJobSummary(
        len(commands) + len(registered),
        claimed,
        continued,
        retryable + (1 if unfinished else 0),
    )


def _registered_command(repository: Any, command_id: str) -> dict[str, Any] | None:
    """The command named `command_id`, found through the registry, never a scan."""
    lister = getattr(repository, "list_pending_deletions", None)
    loader = getattr(repository, "get_deletion_command", None)
    if not callable(lister) or not callable(loader):
        return None
    for entry in lister():
        if entry.command_id == command_id:
            return loader(entry.user_id, entry.command_id)
    return None


async def continue_deletion_command(
    command_id: str, *, service: Any | None = None
) -> None:
    """The request side's share of a deletion `DELETE /auth/me` just accepted.

    It used to run a whole round of every branch before the response left -
    under Mangum a background task runs inside the request - which took 17.6 s
    against the API's 29 s (#397). It now only tombstones the profile, which
    gives the address back at once, and returns the lease; a few keyed reads
    and writes whatever the size of the table. The provider revoke, the
    identity rows and every scan are the scheduled job's, on the deletion
    function, which alone holds the Cognito admin rights. The command is found
    through the pending registry, by key, never by a scan; one accepted before
    the registry is left to the schedule.
    """
    try:
        worker = service or AccountDeletionService()
        repository = worker.repository
        command = _registered_command(repository, command_id)
        if not command or command.get("status") not in {"pending", "running"}:
            return
        now = datetime.now(UTC)
        claim = repository.claim_deletion_command(
            command,
            lease_owner=uuid4().hex,
            now_epoch=int(now.timestamp()),
            lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
            now_iso=now.isoformat(),
        )
        if not claim:
            return
        run_fast_path = getattr(worker, "run_fast_path", None)
        if callable(run_fast_path):
            await asyncio.to_thread(run_fast_path, claim)
    except Exception:
        # The committed command remains discoverable by the scheduled handler.
        return


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    event = event or {}
    if event.get("job") == "moderation_image_retention":
        # A second, daily schedule on this function, which already holds the
        # table and the images bucket (#139).
        from stoa.jobs import moderation_image_retention

        return moderation_image_retention.handler(event, _context)
    if event.get("job") == "security_audit_retention":
        # A daily schedule on this function (card 129): the allow stream is
        # archived to the evidence bucket and leaves the table 90 days on, so
        # it stops pushing the retention scans over their cap (#127).
        from stoa.jobs import security_audit_retention

        return security_audit_retention.handler(event, _context)
    if event.get("job") == "owner_registry_sweep":
        # Daily, report-only (#397): every account's registry checked in one
        # walk, and anything a deleted account left behind.
        from stoa.jobs import owner_registry_sweep

        return owner_registry_sweep.handler(event, _context)
    if event.get("job") == "upload_cleanup":
        # Every 15 minutes (#250): the upload sweep. This function already
        # cleans uploads when it deletes an account, with the same code.
        from stoa.jobs import upload_cleanup

        return upload_cleanup.handler(event, _context)
    remaining = getattr(_context, "get_remaining_time_in_millis", None)
    remaining_seconds = (
        (lambda: float(remaining()) / 1000.0) if callable(remaining) else None
    )
    summary = run_pending_deletions(
        limit=min(max(int(event.get("limit", 25)), 1), 100),
        remaining_seconds=remaining_seconds,
    )
    return asdict(summary)
