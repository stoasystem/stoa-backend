"""Scheduled discovery and continuation for durable account deletion commands."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
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


@dataclass(frozen=True, slots=True)
class DeletionJobSummary:
    discovered: int = 0
    claimed: int = 0
    continued: int = 0
    retryable: int = 0


def run_pending_deletions(
    *,
    repository: Any = account_deletion_repo,
    service_factory: Callable[[], Any] | None = None,
    limit: int = 25,
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
    worker = (service_factory or (lambda: AccountDeletionService()))()
    claimed = continued = retryable = 0
    for command in commands:
        try:
            claim = repository.claim_deletion_command(
                command,
                lease_owner=uuid4().hex,
                now_epoch=int(now.timestamp()),
                lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
                now_iso=now.isoformat(),
            )
            if not claim:
                # Another run holds it; that is progress, not failure.
                continue
            claimed += 1
            worker.continue_command(claim)
            continued += 1
        except Exception:
            retryable += 1
    # Only after every command found here has been dealt with: a run that ends
    # before this line leaves the stored place where it was, and the next run
    # reads the same slice again. A command that failed holds the place too, so
    # the next run retries it in five minutes rather than a whole cycle later.
    # Reaching the end of the table starts the next cycle from the top. A write
    # refused because another run stored a place first is fine; that run's
    # place stands.
    if anomalous:
        logger.warning(
            "account_deletion_scan_anomaly version=%s reason=continuation_key",
            place.version,
        )
    elif retryable:
        logger.warning(
            "account_deletion_scan_held version=%s failed_commands=%s",
            place.version,
            retryable,
        )
    else:
        cycle_started_at = (
            place.cycle_started_at
            if place.cursor is not None and place.cycle_started_at
            else now.isoformat()
        )
        stored = repository.advance_deletion_scan_cursor(
            expected_version=place.version,
            cursor=cursor,
            cycle_started_at=None if cursor is None else cycle_started_at,
            updated_at=now.isoformat(),
        )
        if stored and cursor is None:
            started = datetime.fromisoformat(cycle_started_at)
            logger.info(
                "account_deletion_scan_cycle_completed version=%s completed_at=%s "
                "duration_seconds=%s",
                (place.version or 0) + 1,
                now.isoformat(),
                int((now - started).total_seconds()),
            )
    # A sweep that stopped short says so, so the next run knows to come back.
    return DeletionJobSummary(
        len(commands), claimed, continued, retryable + (1 if unfinished else 0)
    )


async def continue_deletion_command(
    command_id: str, *, service: Any | None = None
) -> None:
    worker = service or AccountDeletionService()
    try:
        repository = worker.repository
        loader = getattr(repository, "get_command_by_id", None)
        command = loader(command_id) if callable(loader) else None
        if not command:
            return
        now = datetime.now(UTC)
        claim = repository.claim_deletion_command(
            command,
            lease_owner=uuid4().hex,
            now_epoch=int(now.timestamp()),
            lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
            now_iso=now.isoformat(),
        )
        if claim:
            await asyncio.to_thread(worker.continue_command, claim)
    except Exception:
        # The committed command remains discoverable by the scheduled handler.
        return


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, int]:
    event = event or {}
    summary = run_pending_deletions(limit=min(max(int(event.get("limit", 25)), 1), 100))
    return asdict(summary)
