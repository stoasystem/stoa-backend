"""Plan 473-36 race contracts for the permanent account-deletion proof."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


NOW = "2026-07-18T12:00:00+00:00"
NOW_EPOCH = 1_784_376_000
INVENTORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "security"
    / "phase-473-private-store-inventory.json"
)


def _command(**overrides: Any) -> dict[str, Any]:
    value = {
        "PK": "USER#student-1",
        "SK": "DELETE_COMMAND#command-1",
        "entity_type": "account_deletion_command",
        "command_id": "command-1",
        "user_id": "student-1",
        "generation": 7,
        "status": "running",
        "version": 4,
        "command_version": 4,
        "branch_results": {},
        "branch_results_digest": account_deletion_repo.branch_results_digest({}),
        "lease_owner": "worker-a",
        "lease_expires_at": NOW_EPOCH + 60,
    }
    value.update(overrides)
    return value


class _ClaimExpressionTable:
    def __init__(self, attributes: dict[str, Any]) -> None:
        self.attributes = attributes
        self.request: dict[str, Any] | None = None

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return {"Attributes": dict(self.attributes)}


def _conditional_failure() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )


class _LeaseStateTable:
    """Evaluate the claim/renew/persist predicates against one durable command."""

    def __init__(self, command: dict[str, Any]) -> None:
        self.command = dict(command)

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        values = kwargs["ExpressionAttributeValues"]
        current = self.command
        matches = (
            current["generation"] == values[":generation"]
            and current["status"] == "running"
        )
        if ":pending" in values:
            matches = current["status"] == "pending" or (
                matches and current["lease_expires_at"] < values[":now_epoch"]
            )
            if not matches:
                raise _conditional_failure()
            current.update(
                status="running",
                lease_owner=values[":owner"],
                lease_expires_at=values[":expiry"],
                command_version=int(current["command_version"]) + 1,
                version=int(current["version"]) + 1,
            )
            return {"Attributes": dict(current)}
        matches = matches and all(
            (
                current["lease_owner"] == values[":owner"],
                current["command_version"] == values[":command_version"],
                current["branch_results_digest"]
                == values[":branch_results_digest"],
                current["lease_expires_at"] >= values[":now_epoch"],
            )
        )
        if not matches:
            raise _conditional_failure()
        current["command_version"] += 1
        current["version"] += 1
        if ":result" in values:
            current["branch_results"] = {
                **current["branch_results"],
                kwargs["ExpressionAttributeNames"]["#branch"]: values[":result"],
            }
            current["branch_results_digest"] = values[":next_digest"]
        else:
            current["lease_expires_at"] = values[":expiry"]
        return {}


def test_claim_compares_stored_expiry_with_distinct_current_epoch() -> None:
    command = _command(status="pending", lease_owner=None, lease_expires_at=0)
    table = _ClaimExpressionTable(
        _command(
            command_version=5,
            version=5,
            lease_owner="worker-b",
            lease_expires_at=NOW_EPOCH + 120,
        )
    )
    claim = account_deletion_repo.claim_deletion_command(
        command,
        lease_owner="worker-b",
        now_epoch=NOW_EPOCH,
        lease_expires_at=NOW_EPOCH + 120,
        now_iso=NOW,
        table=table,
    )

    assert is_dataclass(claim) and claim.lease_owner == "worker-b"
    assert table.request is not None
    assert "lease_expires_at<:now_epoch" in table.request["ConditionExpression"]
    values = table.request["ExpressionAttributeValues"]
    assert values[":now_epoch"] == NOW_EPOCH
    assert values[":expiry"] == NOW_EPOCH + 120
    assert values[":now_epoch"] != values[":expiry"]


def test_two_workers_cannot_steal_active_lease_and_only_one_wins_after_expiry() -> None:
    table = _LeaseStateTable(_command())
    active_snapshot = dict(table.command)
    rejected = account_deletion_repo.claim_deletion_command(
        active_snapshot,
        lease_owner="worker-b",
        now_epoch=NOW_EPOCH,
        lease_expires_at=NOW_EPOCH + 120,
        now_iso=NOW,
        table=table,
    )
    assert rejected is None

    takeover_epoch = NOW_EPOCH + 61
    winner = account_deletion_repo.claim_deletion_command(
        dict(table.command),
        lease_owner="worker-b",
        now_epoch=takeover_epoch,
        lease_expires_at=takeover_epoch + 120,
        now_iso=NOW,
        table=table,
    )
    loser = account_deletion_repo.claim_deletion_command(
        dict(table.command),
        lease_owner="worker-c",
        now_epoch=takeover_epoch,
        lease_expires_at=takeover_epoch + 120,
        now_iso=NOW,
        table=table,
    )
    assert winner is not None and winner.lease_owner == "worker-b"
    assert winner.command_version == 5
    assert loser is None

    stale = account_deletion_repo.DeletionCommandClaim(
        command_id="command-1",
        generation=7,
        lease_owner="worker-a",
        lease_expires_at=NOW_EPOCH + 60,
        command_version=4,
        branch_results_digest=account_deletion_repo.branch_results_digest({}),
    )
    with pytest.raises(account_deletion_repo.DeletionCommandClaimLost):
        account_deletion_repo.renew_deletion_command_claim(
            active_snapshot,
            claim=stale,
            now_epoch=takeover_epoch,
            lease_expires_at=takeover_epoch + 120,
            now_iso=NOW,
            table=table,
        )
    with pytest.raises(account_deletion_repo.DeletionCommandClaimLost):
        account_deletion_repo.persist_branch_result(
            active_snapshot,
            "account_profile",
            {"status": "retryable", "updated_at": NOW},
            claim=stale,
            expected_branch_results_digest=stale.branch_results_digest,
            now_epoch=takeover_epoch,
            table=table,
        )


def test_branch_result_cas_requires_owner_version_digest_and_returns_next_claim() -> None:
    claim_type = getattr(account_deletion_repo, "DeletionCommandClaim")
    claim = claim_type(
        command_id="command-1",
        generation=7,
        lease_owner="worker-a",
        lease_expires_at=NOW_EPOCH + 60,
        command_version=4,
        branch_results_digest=account_deletion_repo.branch_results_digest({}),
    )
    command = _command()
    table = _ClaimExpressionTable(
        _command(
            command_version=5,
            version=5,
            branch_results={
                "account_profile": {
                    "status": "retryable",
                    "result_version": 1,
                }
            },
            branch_results_digest="f" * 64,
        )
    )
    next_claim = account_deletion_repo.persist_branch_result(
        command,
        "account_profile",
        {"status": "retryable", "updated_at": NOW},
        claim=claim,
        expected_branch_results_digest=claim.branch_results_digest,
        now_epoch=NOW_EPOCH,
        table=table,
    )

    assert next_claim.command_version == claim.command_version + 1
    assert next_claim.branch_results_digest != claim.branch_results_digest
    assert table.request is not None
    condition = table.request["ConditionExpression"]
    assert "lease_owner=:owner" in condition
    assert "command_version=:command_version" in condition
    assert "branch_results_digest=:branch_results_digest" in condition
    assert "lease_expires_at>=:now_epoch" in condition


@pytest.mark.parametrize(
    "value",
    ["", "not-a-time", "2026-07-18T12:00:00", 123, None],
)
def test_repository_rejects_invalid_lifecycle_timestamps(value: object) -> None:
    validator = getattr(account_deletion_repo, "_valid_lifecycle_timestamp")
    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        validator(value)


def test_production_service_clock_is_nonblank_timezone_aware_utc() -> None:
    worker = account_deletion_service.AccountDeletionService()
    value = worker.now()
    parsed = datetime.fromisoformat(value)
    assert value and parsed.tzinfo is not None
    assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def test_service_invokes_no_branch_or_later_write_after_claim_renewal_loss() -> None:
    seal = account_deletion_service.load_private_store_seal(INVENTORY_PATH)
    command = _command(
        inventory_sha256=seal["inventory_sha256"],
        branch_ids=list(account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS),
        branch_contracts=seal["branch_contracts"],
    )
    claim = account_deletion_repo._claim_from_command(command)
    calls: list[str] = []

    class _LostRepository:
        def get_command_by_id(self, _command_id: str) -> dict[str, Any]:
            calls.append("load")
            return dict(command)

        def renew_deletion_command_claim(self, *_args: Any, **_kwargs: Any) -> None:
            calls.append("renew")
            raise account_deletion_repo.DeletionCommandClaimLost("taken over")

        def persist_branch_result(self, *_args: Any, **_kwargs: Any) -> None:
            calls.append("persist")

        def finalize_account_deletion(self, *_args: Any, **_kwargs: Any) -> None:
            calls.append("finalize")

    handlers = {
        branch_id: (
            lambda *, command, previous, branch_id=branch_id: (
                calls.append(f"handler:{branch_id}")
                or account_deletion_service.BranchResult("retryable")
            )
        )
        for branch_id in account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS
    }
    worker = account_deletion_service.AccountDeletionService(
        repository=_LostRepository(),
        branch_handlers=handlers,
        now=lambda: NOW,
        now_epoch=lambda: NOW_EPOCH,
        inventory_path=INVENTORY_PATH,
    )
    with pytest.raises(account_deletion_repo.DeletionCommandClaimLost):
        worker.continue_command(claim)
    assert calls == ["load", "load", "renew"]


def test_forged_in_memory_complete_map_cannot_terminalize_durable_incomplete_set() -> None:
    seal = account_deletion_service.load_private_store_seal(INVENTORY_PATH)
    results = {
        branch["branch_id"]: {
            "status": "complete",
            "quiescent": True,
            "epoch": 2,
            "generation": 7,
            "handler_version": branch["handler_version"],
            "subfamilies": list(branch["subfamilies"]),
            "cursor": None,
            "debt_counts": {},
            "legal_retention_blocked": 0,
        }
        for branch in seal["branches"]
    }
    forged = _command(
        branch_results=results,
        branch_results_digest=account_deletion_repo.branch_results_digest(results),
        inventory_sha256=seal["inventory_sha256"],
        branch_ids=list(account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS),
        branch_contracts=seal["branch_contracts"],
    )
    durable = dict(forged)
    durable_results = dict(results)
    durable_results.pop("account_profile")
    durable["branch_results"] = durable_results
    durable["branch_results_digest"] = account_deletion_repo.branch_results_digest(
        durable_results
    )
    finalized: list[bool] = []

    class _DurableTable:
        def get_deletion_command(
            self, _user_id: str, _command_id: str
        ) -> dict[str, Any]:
            return dict(durable)

        def finalize_account_deletion(self, *_args: Any) -> None:
            finalized.append(True)

    fence = {
        "PK": "USER#student-1",
        "SK": "ACCOUNT_FENCE",
        "status": "deletion_pending",
        "generation": 7,
        "version": 2,
        "command_id": "command-1",
    }
    with pytest.raises(account_deletion_repo.DeletionCommandClaimLost):
        account_deletion_repo.finalize_account_deletion(
            command=forged,
            fence=fence,
            seal=seal,
            claim=account_deletion_repo._claim_from_command(forged),
            now_epoch=NOW_EPOCH,
            now_iso=NOW,
            table=_DurableTable(),
        )
    assert finalized == []


def test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences() -> None:
    scanned = {
        "PK": "USER#parent-1",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": "parent-1",
        "version": 3,
        "preferences": {"digest": "weekly"},
        "child_summaries": [{"student_id": "student-1", "name": "private"}],
    }

    class _ConcurrentParent:
        def __init__(self) -> None:
            self.current = {
                **scanned,
                "version": 4,
                "preferences": {"digest": "daily"},
            }

        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
            if Key["SK"] == "ACCOUNT_FENCE":
                user_id = Key["PK"].removeprefix("USER#")
                status = "active" if user_id == "parent-1" else "deletion_pending"
                return {"Item": {**Key, "status": status, "generation": 7}}
            return {"Item": dict(self.current)}

        def scrub_parent_profile_child(self, *_args: Any, **kwargs: Any) -> None:
            assert kwargs["expected_version"] == 3
            if self.current["version"] != kwargs["expected_version"]:
                raise account_deletion_repo.AccountDeletionRowConflict(
                    "parent profile changed"
                )

    table = _ConcurrentParent()
    with pytest.raises(account_deletion_repo.AccountDeletionRowConflict):
        account_deletion_repo.scrub_parent_profile_child(
            scanned,
            child_user_id="student-1",
            generation=7,
            table=table,
        )
    assert table.current["preferences"] == {"digest": "daily"}
    assert table.current["child_summaries"][0]["student_id"] == "student-1"


def test_fresh_parent_rescan_removes_only_child_and_advances_row_version() -> None:
    profile = {
        "PK": "USER#parent-1",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": "parent-1",
        "version": 4,
        "preferences": {"digest": "daily"},
        "subscription": {"status": "active"},
        "child_summaries": [
            {"student_id": "student-1", "name": "private"},
            {"student_id": "student-2", "name": "sibling"},
        ],
    }

    class _CurrentParent:
        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
            return {
                "Item": {
                    **Key,
                    "status": "active",
                    "generation": 9,
                }
            }

        def scrub_parent_profile_child(
            self,
            _scanned: dict[str, Any],
            scrubbed: dict[str, Any],
            _child_id: str,
            _generation: int,
            _parent_generation: int,
            *,
            expected_version: int,
        ) -> None:
            assert expected_version == profile["version"]
            scrubbed["version"] = expected_version + 1
            profile.clear()
            profile.update(scrubbed)

    account_deletion_repo.scrub_parent_profile_child(
        dict(profile),
        child_user_id="student-1",
        generation=7,
        table=_CurrentParent(),
    )
    assert profile["version"] == 5
    assert profile["preferences"] == {"digest": "daily"}
    assert profile["subscription"] == {"status": "active"}
    assert [row["student_id"] for row in profile["child_summaries"]] == [
        "student-2"
    ]


def test_account_profile_row_conflict_stays_retryable_debt(monkeypatch: Any) -> None:
    page = account_deletion_repo.OwnedPrivatePage(
        (
            {
                "PK": "USER#parent-1",
                "SK": "PROFILE",
                "user_id": "parent-1",
                "version": 3,
                "child_summaries": [{"student_id": "student-1"}],
            },
        ),
        None,
    )
    monkeypatch.setattr(
        account_deletion_repo, "scan_owned_private_rows", lambda *_args, **_kwargs: page
    )
    monkeypatch.setattr(
        account_deletion_repo,
        "scrub_parent_profile_child",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            account_deletion_repo.AccountDeletionRowConflict("changed")
        ),
    )
    result = account_deletion_service._account_profile_branch(
        command={"user_id": "student-1", "generation": 7}, previous={}
    )
    assert result.status == "retryable"
    assert result.epoch == 0 and result.quiescent is False
    assert result.debt_counts == {"row_conflict": 1, "pass_dirty": 1}
