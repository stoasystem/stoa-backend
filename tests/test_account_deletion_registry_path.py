"""Account deletion on the owner registry path: no full-table scan (#397, PR 3).

A command sealed with the v2 inventory reads only the account's derived
partitions and the partitions registered under `USER#{id}` - strongly, by key,
never through an index - and proves completeness the way v1 did: two clean
passes, now over those partitions. A command sealed with v1, including any in
flight when the switch is turned on, keeps the full-table scan to its end.
"""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

import test_account_deletion_quick_fix as quick
import test_chat_help_request_lifecycle as lifecycle
from fakes.dynamodb import FakeTable
from stoa import config
from stoa.aws import Kind
from stoa.db import owner_registry
from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service as service
from stoa.services import owner_registry_sweep

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"
V2 = ROOT / "docs" / "security" / "phase-473-private-store-inventory.v2.json"
GENERATOR = ROOT / "scripts" / "generate_phase473_private_store_inventory_v2.py"

table = quick.table
providers = quick.providers


def _generator():
    spec = importlib.util.spec_from_file_location("phase473_inventory_v2", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry_path(monkeypatch: pytest.MonkeyPatch):
    config.install(config.settings().model_copy(update={"account_deletion_registry_path": True}))
    yield
    config.install(None)


def _sign_in(table: FakeTable, user_id: str) -> tuple[str, str]:
    key = (f"USER#{user_id}", "SIGNIN#jti-1")
    table.seed({"PK": key[0], "SK": key[1], "entity_type": "auth_sign_in_session",
                "origin_jti": "jti-1", "refresh_token": "refresh-secret", "expires_at": 9999999999})
    return key


def _run(command_id: str, user_id: str, table: FakeTable) -> dict[str, Any]:
    command = quick._command(table, user_id, command_id)
    claim = quick._claim(command)
    service.AccountDeletionService(remaining_seconds=lambda: 500.0).continue_command(claim)
    return quick._command(table, user_id, command_id)


# -- the inventories -------------------------------------------------------------------


def test_v1_is_untouched_and_v2_is_derived_from_it_deterministically():
    assert sha256(V1.read_bytes()).hexdigest() == quick.SEALED_INVENTORY_SHA256
    module = _generator()
    assert module.main(["--check"]) == 0
    v1, v2 = json.loads(V1.read_bytes()), json.loads(V2.read_bytes())
    assert v2["schema_version"] == "phase-473-private-store-inventory.v2"
    assert v2["supersedes"] == {
        "inventory_sha256": quick.SEALED_INVENTORY_SHA256,
        "schema_version": "phase-473-private-store-inventory.v1",
    }
    assert v2["branch_ids"] == v1["branch_ids"]
    assert {b["handler_version"] for b in v2["branch_registry"]} == {"473-36.v2"}
    assert {json.dumps(r["cursor_schema"], sort_keys=True) for r in v2["rows"]} == {
        json.dumps(module.CURSOR_SCHEMA, sort_keys=True)
    }
    assert all(r["cursor_schema"]["complete_scan_required"] is False for r in v2["rows"])
    # Nothing else moved: same rows, same allowlists, same quiescence.
    def strip(row: dict) -> dict:
        return {k: v for k, v in row.items() if k != "cursor_schema"}

    assert [strip(r) for r in v2["rows"]] == [strip(r) for r in v1["rows"]]
    assert all(r["quiescence"]["authoritative_zero_epochs"] == 2 for r in v2["rows"])


def test_acceptance_seals_v1_unless_the_switch_is_on(small_table, monkeypatch):
    assert service.acceptance_seal()["inventory_sha256"] == quick.SEALED_INVENTORY_SHA256
    config.install(config.settings().model_copy(update={"account_deletion_registry_path": True}))
    try:
        seal = service.acceptance_seal()
    finally:
        config.install(None)
    assert seal["registry_path"] is True
    assert seal["inventory_sha256"] == sha256(V2.read_bytes()).hexdigest()


small_table = quick.small_table


# -- the registry path -----------------------------------------------------------------


def test_a_registry_path_deletion_completes_without_scanning_the_table(
    table: FakeTable, providers: dict[Kind, Any], registry_path
) -> None:
    student = lifecycle.STUDENT
    sign_in = _sign_in(table, student)
    # The migration order: the backfill has given the pre-existing rows their
    # registry rows before the switch was turned on.
    assert owner_registry_sweep.run(table=table, write=True).complete
    assert owner_registry_sweep.run(table=table).registry_complete
    command_id = quick._accept(student)
    scans_before = table.calls["scan"]

    command = _run(command_id, student, table)

    assert command["status"] == "complete", command.get("branch_results")
    assert command["inventory_sha256"] == sha256(V2.read_bytes()).hexdigest()
    assert table.calls["scan"] == scans_before
    reads = [request for name, request in table.requests if name in {"query", "scan"}]
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
    # Finalized means `validate_deletion_seal` held against v2: every branch
    # complete, quiescent after two clean passes, stamped `473-36.v2`.


def test_the_registry_path_needs_the_registry(
    table: FakeTable, providers: dict[Kind, Any], registry_path
) -> None:
    """Without the backfill a pre-existing row is out of reach: why the switch waits for the sweep."""
    student = lifecycle.STUDENT
    command_id = quick._accept(student)

    _run(command_id, student, table)

    left = quick._private_left(table)
    assert left, "an unregistered partition is not read on the registry path"
    report = owner_registry_sweep.run(table=table)
    assert report.leftovers or report.unregistered


def test_each_pass_reads_the_registry_strongly_and_queries_each_partition(
    table: FakeTable, providers: dict[Kind, Any], registry_path
) -> None:
    student = lifecycle.STUDENT
    owner_registry_sweep.run(table=table, write=True)
    with account_deletion_repo.registry_scope(student) as scope:
        pass
    registered = {
        row["registered_pk"] for key, row in table.rows.items()
        if key[0] == f"USER#{student}" and owner_registry.is_registry_row(row)
    }
    assert registered
    assert set(scope.partitions) == set(owner_registry.derived_partitions(student)) | registered
    assert list(scope.partitions) == sorted(scope.partitions)


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


def test_a_v1_command_keeps_the_scan_path_after_the_switch(
    table: FakeTable, providers: dict[Kind, Any]
) -> None:
    student = lifecycle.STUDENT
    command_id = quick._accept(student)  # sealed with v1, switch off
    config.install(config.settings().model_copy(update={"account_deletion_registry_path": True}))
    try:
        command = _run(command_id, student, table)
    finally:
        config.install(None)

    assert command["status"] == "complete"
    assert command["inventory_sha256"] == quick.SEALED_INVENTORY_SHA256
    assert table.calls["scan"] > 0
    assert quick._private_left(table) == []


def test_a_command_under_neither_inventory_is_seal_drift(small_table: FakeTable) -> None:
    worker = service.AccountDeletionService()
    assert len(worker.seals) == 2
    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match="seal drift"):
        worker._require_sealed_command({"inventory_sha256": "0" * 64})


def test_a_v2_command_does_not_validate_against_v1_or_the_reverse() -> None:
    worker = service.AccountDeletionService()
    v1, v2 = (worker.seals[sha] for sha in sorted(worker.seals, key=lambda s: s != quick.SEALED_INVENTORY_SHA256))
    assert v1["branch_contracts"] != v2["branch_contracts"]
    command = {"inventory_sha256": v2["inventory_sha256"], "branch_ids": list(service.ACCOUNT_DELETION_BRANCH_IDS),
               "branch_contracts": v1["branch_contracts"]}
    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match="seal drift"):
        worker._require_sealed_command(command)


def test_a_v2_rounds_results_carry_the_v2_handler_version_and_registry_cursors(
    table: FakeTable, providers: dict[Kind, Any], registry_path
) -> None:
    student = lifecycle.STUDENT
    owner_registry_sweep.run(table=table, write=True)
    command_id = quick._accept(student)
    claim = quick._claim(quick._command(table, student, command_id))

    # One unbudgeted round: one page per branch, nothing finalized yet.
    service.AccountDeletionService().continue_command(claim)

    command = quick._command(table, student, command_id)
    results = command["branch_results"]
    assert {r["handler_version"] for r in results.values()} == {"473-36.v2"}
    cursors = [r["cursor"] for r in results.values() if r.get("cursor")]
    partitions = set(account_deletion_repo.owner_partitions(student))
    assert all(set(c) == {"PK", "SK"} and c["PK"] in partitions for c in cursors)
