"""Account deletion on the owner registry path: no full-table scan (#397, PR 3; #641).

A deletion reads only the account's derived partitions and the partitions
registered under `USER#{id}` - strongly, by key, never through an index - and
is done when a whole pass over them finds nothing to handle. Since #641 every
new deletion takes this path (the catalog's three steps), and only while the
daily sweep vouches for the registry; the v1/v2 inventories, their acceptance
switch and the full-table path went with #642.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pytest

import test_account_deletion_quick_fix as quick
import test_chat_help_request_lifecycle as lifecycle
from fakes.dynamodb import FakeTable
from stoa.aws import Kind
from stoa.db import data_catalog, owner_registry
from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_flow as flow
from stoa.services import account_deletion_service as service
from stoa.services import owner_registry_sweep

ROOT = Path(__file__).resolve().parents[1]

table = quick.table
providers = quick.providers


def _sign_in(table: FakeTable, user_id: str) -> tuple[str, str]:
    key = (f"USER#{user_id}", "SIGNIN#jti-1")
    table.seed({"PK": key[0], "SK": key[1], "entity_type": "auth_sign_in_session",
                "origin_jti": "jti-1", "refresh_token": "refresh-secret", "expires_at": 9999999999})
    return key


def _vouch(table: FakeTable) -> owner_registry_sweep.SweepReport:
    """What the daily job does: sweep, and leave its result for acceptance."""
    report = owner_registry_sweep.run(table=table)
    owner_registry_sweep.record_run(report, now_iso=datetime.now(UTC).isoformat(), table=table)
    return report


def _run(command_id: str, user_id: str, table: FakeTable) -> dict[str, Any]:
    command = quick._command(table, user_id, command_id)
    claim = quick._claim(command)
    flow.CatalogDeletion(remaining_seconds=lambda: 500.0).continue_command(claim)
    return quick._command(table, user_id, command_id)


# -- acceptance waits for the sweep ---------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        None,
        {"complete": False, "missing_registrations": 0},
        {"complete": True, "missing_registrations": 3},
        {"complete": True, "missing_registrations": 0, "completed_at": "2026-01-01T00:00:00+00:00"},
        {"complete": True, "missing_registrations": 0, "completed_at": "not a time"},
    ],
)
def test_without_a_clean_recent_sweep_no_new_deletion_is_accepted(small_table, marker):
    small_table.rows.pop(
        (owner_registry_sweep.RUN_MARKER_KEY["PK"], owner_registry_sweep.RUN_MARKER_KEY["SK"])
    )
    if marker is not None:
        small_table.seed({**owner_registry_sweep.RUN_MARKER_KEY,
                          "completed_at": datetime.now(UTC).isoformat(), **marker})

    assert not service.registry_path_ready()
    with pytest.raises(service.DeletionNotReady):
        quick._accept("student-small")
    fence = small_table.rows[("USER#student-small", "ACCOUNT_FENCE")]
    assert fence["status"] == "active"


small_table = quick.small_table


# -- the registry path -----------------------------------------------------------------


def test_a_registry_path_deletion_completes_without_scanning_the_table(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    student = lifecycle.STUDENT
    sign_in = _sign_in(table, student)
    # The migration order: the backfill has given the pre-existing rows their
    # registry rows before the switch was turned on.
    assert owner_registry_sweep.run(table=table, write=True).complete
    assert _vouch(table).registry_complete
    # The table was built by offering a help request, which lists the teachers
    # through an index (#609); what is held to no index is the deletion.
    requests_before = len(table.requests)
    command_id = quick._accept(student)
    scans_before = table.calls["scan"]

    command = _run(command_id, student, table)

    assert command["status"] == "complete", command.get("deletion_progress")
    assert command["catalog_sha256"] == data_catalog.catalog_sha256()
    assert table.calls["scan"] == scans_before
    reads = [
        request
        for name, request in table.requests[requests_before:]
        if name in {"query", "scan"}
    ]
    assert reads
    assert not any("IndexName" in request for request in reads)
    assert all(request.get("ConsistentRead") is True for name, request in table.requests
               if name == "query" and "IndexName" not in request)
    assert table.rows[(f"USER#{student}", "ACCOUNT_FENCE")]["status"] == "deleted"
    assert quick._private_left(table) == []
    # Covered now: the stored refresh token is gone, not left to its TTL.
    assert sign_in not in table.rows
    # The registry itself goes once the deletion is final.
    assert not [
        key for key, row in table.rows.items()
        if key[0] == f"USER#{student}" and owner_registry.is_registry_row(row)
    ]
    # Finalized means a whole pass over those partitions found nothing left.


def test_a_registry_path_deletion_of_a_parent_scrubs_the_recovery_audit_event_naming_it(
    small_table: FakeTable, providers: dict[Kind, Any]
) -> None:
    """A parent named only as a recovery target, in an event's metadata (#573).

    No backfill: the event's own write registers the parent, so the sweep
    vouches for the table and the v2 deletion reads the job's partition.
    """
    from stoa.db.repositories import report_repo

    parent = "parent-573"
    small_table.seed(
        {"PK": f"USER#{parent}", "SK": "PROFILE", "user_id": parent, "role": "parent",
         "account_status": "active", "version": 1},
        {"PK": f"USER#{parent}", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
         "user_id": parent, "status": "active", "generation": 1, "version": 1},
    )
    report_repo.put_recovery_job_audit_event(
        "job-573",
        {
            "event_id": "event-1",
            "event_at": "2026-11-21T10:00:00+00:00",
            "job_id": "job-573",
            "action": "resend_email_target",
            "result": "success",
            "metadata": {"target_id": "t1", "parent_id": parent, "student_id": "student-small"},
        },
    )
    event_key = ("REPORT_RECOVERY_JOB#job-573", "AUDIT#2026-11-21T10:00:00+00:00#event-1")
    assert _vouch(small_table).registry_complete
    command_id = quick._accept(parent)
    scans_before = small_table.calls["scan"]

    command = _run(command_id, parent, small_table)

    assert command["status"] == "complete", command.get("deletion_progress")
    assert command["catalog_sha256"] == data_catalog.catalog_sha256()
    assert small_table.calls["scan"] == scans_before
    event = small_table.rows[event_key]
    assert event["privacy_deleted"] is True
    assert parent not in json.dumps(event, default=str)


def test_without_the_backfill_a_new_deletion_is_refused(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    student = lifecycle.STUDENT
    assert not _vouch(table).registry_complete

    with pytest.raises(service.DeletionNotReady):
        quick._accept(student)

    assert table.rows[(f"USER#{student}", "ACCOUNT_FENCE")]["status"] == "active"
    assert not [key for key in table.rows if key[0] == account_deletion_repo.PENDING_REGISTRY_PK]


def test_the_registry_path_needs_the_registry(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    """What the guard prevents: a v2 deletion over an unbackfilled table misses rows."""
    student = lifecycle.STUDENT
    table.seed({**owner_registry_sweep.RUN_MARKER_KEY, "complete": True,
                "missing_registrations": 0, "completed_at": datetime.now(UTC).isoformat()})
    command_id = quick._accept(student)

    _run(command_id, student, table)

    left = quick._private_left(table)
    assert left, "an unregistered partition is not read on the registry path"
    report = owner_registry_sweep.run(table=table)
    assert report.leftovers or report.unregistered


def test_each_pass_reads_the_registry_strongly_and_queries_each_partition(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    student = lifecycle.STUDENT
    owner_registry_sweep.run(table=table, write=True)
    partitions = account_deletion_repo.owner_partitions(student)
    registered = {
        row["registered_pk"] for key, row in table.rows.items()
        if key[0] == f"USER#{student}" and owner_registry.is_registry_row(row)
    }
    assert registered
    assert set(partitions) == set(owner_registry.derived_partitions(student)) | registered
    assert list(partitions) == sorted(partitions)


def test_a_registry_pass_pages_and_resumes_by_partition_position():
    double = FakeTable()
    rows = [{"PK": f"CONV#c{i}", "SK": f"MSG#{j}", "owner_id": "u"} for i in range(3) for j in range(4)]
    double.seed(*rows, {"PK": "OTHER#x", "SK": "A", "owner_id": "u"})
    scope = account_deletion_repo.RegistryScope("u", ("CONV#c0", "CONV#c1", "CONV#c2"))
    seen: list[tuple[str, str]] = []
    cursor = None
    while True:
        (page,) = list(account_deletion_repo.registry_pages(
            scope, start=cursor, table=double, Limit=5
        ))[:1]
        seen.extend((item["PK"], item["SK"]) for item in page.items)
        if page.last_key is None:
            break
        cursor = page.last_key
    assert sorted(seen) == sorted((r["PK"], r["SK"]) for r in rows)
    assert len(seen) == len(set(seen))
    assert double.calls["scan"] == 0


def test_a_run_stops_at_a_position_in_the_accounts_own_partitions(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    student = lifecycle.STUDENT
    owner_registry_sweep.run(table=table, write=True)
    _vouch(table)
    command_id = quick._accept(student)
    claim = quick._claim(quick._command(table, student, command_id))

    # One page, then it stops and says where.
    flow.CatalogDeletion(page_rows=5, max_pages=1).continue_command(claim)

    progress = quick._command(table, student, command_id)["deletion_progress"]
    assert progress["open"] is False
    assert set(progress["cursor"]) == {"PK", "SK"}
    assert progress["cursor"]["PK"] in set(account_deletion_repo.owner_partitions(student))


# -- a notification that only mentions the account (#574) ------------------------------

PARENT_574 = "parent-574"


def _open_parent(table: FakeTable) -> None:
    table.seed(
        {"PK": f"USER#{PARENT_574}", "SK": "PROFILE", "user_id": PARENT_574,
         "role": "parent", "account_status": "active", "version": 1},
        {"PK": f"USER#{PARENT_574}", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
         "user_id": PARENT_574, "status": "active", "generation": 1, "version": 1},
    )


def _mentioning_event(field: str) -> dict[str, Any]:
    return {
        "event_id": "e-574", "entity_type": "notification_event",
        "schema_version": "notification-event.v2", "owner_id": "student-small",
        "account_fence_generation": 1, "status": "created", "event_version": 1,
        "title": "Ihr Kind hat eine Frage gestellt",
        "metadata": {field: PARENT_574, "subject": "math"},
    }


@pytest.mark.parametrize("field", ["parent_id", "actor_id"])
def test_a_registry_path_deletion_scrubs_the_account_out_of_a_notification_it_is_named_in(
    small_table: FakeTable, providers: dict[Kind, Any], field: str
) -> None:
    from stoa.db.repositories import notification_repo

    _open_parent(small_table)
    notification_repo.put_event(_mentioning_event(field))
    key = ("NOTIFICATION#e-574", "META")

    # The write registered the mentioned account, so the sweep finds nothing
    # missing and leaves the registry path open.
    report = _vouch(small_table)
    assert report.complete and not report.unregistered, report.unregistered_samples
    assert service.registry_path_ready(table=small_table)
    command_id = quick._accept(PARENT_574)
    scans_before = small_table.calls["scan"]

    command = _run(command_id, PARENT_574, small_table)

    assert command["status"] == "complete", command.get("deletion_progress")
    assert command["catalog_sha256"] == data_catalog.catalog_sha256()
    assert small_table.calls["scan"] == scans_before
    # Scrubbed the way the notification family scrubs a reference: the account
    # is gone from it, the student's notification stays theirs, nothing else
    # changed. No other branch tombstoned or deleted it.
    row = small_table.rows[key]
    assert row["entity_type"] == "notification_event"
    assert row["owner_id"] == "student-small"
    assert row["metadata"] == {"subject": "math"}
    assert row["title"] == "Ihr Kind hat eine Frage gestellt"
    assert int(row["event_version"]) == 2
    assert not data_catalog.names(row, PARENT_574)


def test_the_sweep_counts_an_unregistered_mention_and_backfills_what_the_write_registers(
    small_table: FakeTable,
) -> None:
    """A notification stored before #574 lacks the row; the backfill writes the same one."""
    from stoa.db.repositories import notification_repo

    _open_parent(small_table)
    stored = {**_mentioning_event("parent_id"), "PK": "NOTIFICATION#e-574", "SK": "META"}
    small_table.seed(stored)

    report = owner_registry_sweep.run(table=small_table, write=True)

    # Its owner's row is missing too, seeded as it is; the mention is the point.
    assert {(sample["account"], sample["role"]) for sample in report.unregistered_samples} == {
        ("student-small", "owner"), (PARENT_574, "reference"),
    }
    reference = owner_registry.registry_key(
        PARENT_574, "NOTIFICATION#e-574", owner_registry.ROLE_REFERENCE
    )
    backfilled = small_table.rows.pop((reference["PK"], reference["SK"]))
    # The write path, given the same event, registers the very same row.
    small_table.rows.pop(("NOTIFICATION#e-574", "META"))
    notification_repo.put_event(_mentioning_event("parent_id"))
    assert small_table.rows[(reference["PK"], reference["SK"])] == backfilled
    assert not owner_registry_sweep.run(table=small_table).unregistered
