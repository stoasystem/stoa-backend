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
    commands: list[dict[str, Any]] = []
    cursor: dict[str, str] | None = None
    seen_cursors: set[tuple[str, str]] = set()
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
                return DeletionJobSummary(
                    discovered=len(commands), retryable=1
                )
            identity = (next_cursor["PK"], next_cursor["SK"])
            if identity in seen_cursors:
                return DeletionJobSummary(
                    discovered=len(commands), retryable=1
                )
            seen_cursors.add(identity)
            cursor = next_cursor
        if len(commands) < limit and cursor is not None and pages >= 100:
            return DeletionJobSummary(discovered=len(commands), retryable=1)
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
                    lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
                    now_iso=now.isoformat(),
                )
            else:
                claim = repository.claim_deletion_command(
                    str(command["command_id"]),
                    int(command["generation"]),
                    lease_owner=uuid4().hex,
                    lease_expires_at=int((now + timedelta(minutes=2)).timestamp()),
                    now_iso=now.isoformat(),
                )
            if not claim:
                continue
            claimed += 1
            worker.continue_command(str(command["command_id"]))
            continued += 1
        except Exception:
            retryable += 1
    return DeletionJobSummary(len(commands), claimed, continued, retryable)


async def continue_deletion_command(
    command_id: str, *, service: Any | None = None
) -> None:
    worker = service or AccountDeletionService()
    try:
        await asyncio.to_thread(worker.continue_command, command_id)
    except Exception:
        # The committed command remains discoverable by the scheduled handler.
        return


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, int]:
    event = event or {}
    summary = run_pending_deletions(limit=min(max(int(event.get("limit", 25)), 1), 100))
    return asdict(summary)
