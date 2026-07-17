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
    if repository is account_deletion_repo:
        page = account_deletion_repo.scan_pending_deletion_commands(limit=limit)
        commands = list(page.items)
    elif callable(scan):
        raw = scan(limit=limit, exclusive_start_key=None)
        commands = list(raw[0] if isinstance(raw, tuple) else raw.items)
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
