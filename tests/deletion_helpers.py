"""Run one account deletion the way production does, for tests outside the flow's own (#642).

The 17 deletion branches each had a handler a test could call on its own; they
went with #642. A test that pins what deleting an account does to its rows now
accepts the deletion and lets the scheduled job carry it through the catalog's
three steps (`stoa.services.account_deletion_flow`), against whatever table the
gateway holds (the `FakeTable` every test starts with, unless it installs another).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo
from stoa.jobs import account_deletion as job
from stoa.services import account_deletion_service, owner_registry_sweep


def vouch_for_the_registry(table: Any | None = None) -> None:
    """The daily registry sweep's last result: a whole walk, nothing missing."""
    db_table.put(
        table=table,
        Item={
            **owner_registry_sweep.RUN_MARKER_KEY,
            "complete": True,
            "missing_registrations": 0,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )


def register(table: Any, *rows: Mapping[str, Any]) -> None:
    """File each row's partition under every account it names, as its writer would have."""
    for row in rows:
        for account, role in data_catalog.mentions(row).items():
            if not owner_registry.is_derived_for(str(row["PK"]), account):
                db_table.put(
                    table=table, Item=owner_registry.registry_item(account, str(row["PK"]), role)
                )


def active_fence(table: Any, user_id: str, *, generation: int = 1) -> None:
    db_table.put(
        table=table,
        Item={
            **account_deletion_repo.account_fence_key(user_id),
            "entity_type": "account_fence",
            "user_id": user_id,
            "status": "active",
            "generation": generation,
            "version": 1,
        },
    )


def accept(user_id: str, *, table: Any | None = None) -> str:
    """Accept `user_id`'s deletion as an operator would; its command id.

    The account needs its fence (`active_fence`, or the one its provisioning wrote).
    A fence a test seeded without a `version` gets the first one, as every
    production fence has.
    """
    vouch_for_the_registry(table)
    fence = account_deletion_repo.get_account_fence(user_id, table=table)
    if fence is not None and "version" not in fence:
        db_table.put(table=table, Item={**fence, "version": 1})
    return account_deletion_service.accept_account_deletion(
        user_id=user_id,
        initiator=account_deletion_service.OperatorInitiated(
            initiated_by="operator:test", reason="a test deletes this account"
        ),
        now_iso=datetime.now(UTC).isoformat(),
        table=table,
    ).command_id


def run_once(user_id: str, command_id: str, *, table: Any | None = None) -> dict[str, Any]:
    """One scheduled run of the deletion job; the command as it stands after it."""
    summary = job.run_pending_deletions()
    assert summary.paused == 0, summary
    command = account_deletion_repo.get_deletion_command(user_id, command_id, table=table)
    assert command is not None
    return command


def delete_account(user_id: str, *, table: Any | None = None, runs: int = 10) -> dict[str, Any]:
    """Accept `user_id`'s deletion and run the job until it completes; the finished command."""
    command_id = accept(user_id, table=table)
    for _ in range(runs):
        command = run_once(user_id, command_id, table=table)
        if command.get("status") == "complete":
            return command
    raise AssertionError(f"deletion of {user_id} not complete after {runs} runs")
