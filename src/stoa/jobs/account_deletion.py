"""Scheduled discovery and continuation for durable account deletion commands."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from stoa.db.repositories import account_deletion_repo
from stoa.services.account_deletion_service import AccountDeletionService


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
    now = datetime.now(UTC)
    scan = getattr(repository, "scan_pending_deletion_commands", None)
    # One run reads a bounded slice of the table, so it starts where the last
    # run stopped. Without this every run read the same first slice, and a
    # command further down was never reached by the schedule (#7).
    read_place = getattr(repository, "get_deletion_scan_cursor", None)
    store_place = getattr(repository, "advance_deletion_scan_cursor", None)
    place = read_place() if callable(read_place) and callable(store_place) else None
    commands: list[dict[str, Any]] = []
    cursor: dict[str, str] | None = place.cursor if place is not None else None
    seen_cursors: set[tuple[str, str]] = set()
    unfinished = False
    # A continuation key the scan should never hand back; where it points is
    # not a place worth keeping.
    anomalous = False
    if repository is account_deletion_repo or callable(scan):
        pages = 0
        while len(commands) < limit and pages < 100:
            pages += 1
            page_limit = max(limit - len(commands), 1)
            if repository is account_deletion_repo:
                page = account_deletion_repo.scan_pending_deletion_commands(
                    limit=page_limit, cursor=cursor
                )
                items, next_cursor = list(page.items), page.cursor
            else:
                assert callable(scan)
                raw = scan(limit=page_limit, exclusive_start_key=cursor)
                if isinstance(raw, tuple):
                    items, next_cursor = list(raw[0]), raw[1]
                else:
                    items, next_cursor = list(raw.items), raw.cursor
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
    else:
        return DeletionJobSummary(retryable=1)
    worker = (service_factory or (lambda: AccountDeletionService()))()
    claimed = continued = retryable = 0
    for command in commands:
        try:
            if repository is account_deletion_repo:
                claim = account_deletion_repo.claim_deletion_command(
                    command,
                    lease_owner=uuid4().hex,
                    now_epoch=int(now.timestamp()),
                    lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
                    now_iso=now.isoformat(),
                )
            else:
                claim = repository.claim_deletion_command(
                    command,
                    lease_owner=uuid4().hex,
                    now_epoch=int(now.timestamp()),
                    lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
                    now_iso=now.isoformat(),
                )
            if not claim:
                continue
            claimed += 1
            worker.continue_command(claim)
            continued += 1
        except Exception:
            retryable += 1
    # Only after every command found here has been attempted: a run that ends
    # before this line leaves the stored place where it was, and the next run
    # reads the same slice again. Reaching the end of the table starts the next
    # cycle from the top. A write refused because another run stored a place
    # first is fine; that run's place stands.
    if place is not None and not anomalous:
        assert callable(store_place)
        store_place(
            expected_version=place.version,
            cursor=cursor,
            cycle_started_at=(
                None
                if cursor is None
                else (
                    place.cycle_started_at
                    if place.cursor is not None and place.cycle_started_at
                    else now.isoformat()
                )
            ),
            updated_at=now.isoformat(),
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
