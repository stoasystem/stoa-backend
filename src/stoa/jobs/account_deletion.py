"""Scheduled discovery and continuation for durable account deletion commands.

Every accepted command has a row in `ACCOUNT_DELETION_PENDING`, written in the
transaction that accepts it (#397), and one strong query of that partition
finds all of them on every run. The cursor scan of the whole table that found
the commands accepted before that registry existed is gone (#611): production
held none on 2026-11-24, and what a run reads no longer follows the table.
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


# Everything a run calls. A repository without one of these is refused before
# anything is read: a double missing a method used to get a quieter behaviour
# silently (#7), and a run that could not list the registry would find nothing
# and report an empty success.
_REQUIRED_REPOSITORY_METHODS = (
    "list_pending_deletions",
    "get_deletion_command",
    "claim_deletion_command",
)


# Below this much remaining Lambda time a run claims no further command.
MIN_REMAINING_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class DeletionJobSummary:
    discovered: int = 0
    claimed: int = 0
    continued: int = 0
    retryable: int = 0


def _registered_commands(repository: Any) -> tuple[list[dict[str, Any]], bool]:
    """The commands the pending registry names, each read by its key, and whether all were read.

    A row whose command is finished or gone is dropped on the way. A registry
    that cannot be read, or a command that cannot, is logged and makes the
    answer incomplete: the run reports it, and the next run asks again.
    """
    try:
        entries = repository.list_pending_deletions()
    except Exception:
        logger.warning("account_deletion_registry_unavailable")
        return [], False
    commands: list[dict[str, Any]] = []
    complete = True
    for entry in entries:
        try:
            command = repository.get_deletion_command(entry.user_id, entry.command_id)
        except Exception:
            logger.warning(
                "account_deletion_registry_read_failed command_id=%s", entry.command_id
            )
            complete = False
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
    return commands, complete


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
    registered, complete = _registered_commands(repository)
    unfinished = not complete
    worker = (
        service_factory
        or (lambda: AccountDeletionService(remaining_seconds=remaining_seconds))
    )()
    claimed = continued = retryable = 0
    # The registry is small and read whole; `limit` bounds what one run takes on.
    for command in registered[:limit]:
        if remaining_seconds is not None and remaining_seconds() < MIN_REMAINING_SECONDS:
            # Not attempted is not failed: the next run's query finds it again.
            unfinished = True
            break
        try:
            claim = _claim(repository, command)
            if not claim:
                # Another run holds it; that is progress, not failure.
                continue
            claimed += 1
            worker.continue_command(claim)
            continued += 1
        except Exception:
            # Found again by the next run's query, five minutes on.
            retryable += 1
            logger.warning(
                "account_deletion_command_failed command_id=%s",
                str(command.get("command_id") or ""),
            )
    if len(registered) > limit:
        unfinished = True
    # A run that stopped short says so, so the next run knows to come back.
    return DeletionJobSummary(
        len(registered),
        claimed,
        continued,
        retryable + (1 if unfinished else 0),
    )


def _registered_command(repository: Any, command_id: str) -> dict[str, Any] | None:
    """The command named `command_id`, found through the registry, by key."""
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
    identity rows and every branch are the scheduled job's, on the deletion
    function, which alone holds the Cognito admin rights. The command is found
    through the pending registry, by key.
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
