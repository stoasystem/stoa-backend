"""Plan 473-36 race contracts for the permanent account-deletion proof."""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any, Mapping

import pytest
from botocore.exceptions import ClientError
from fakes.dynamodb import as_stored as _as_stored

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo


NOW = "2026-07-18T12:00:00+00:00"


NOW_EPOCH = 1_784_376_000


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
        return {"Attributes": _as_stored(dict(self.attributes))}


def _conditional_failure() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )


class _LeaseStateTable:
    """Evaluate the claim and renewal predicates against one durable command."""

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
            return {"Attributes": _as_stored(dict(current))}
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


def test_lease_renewal_requires_owner_version_digest_and_returns_next_claim() -> None:
    claim = account_deletion_repo.DeletionCommandClaim(
        command_id="command-1",
        generation=7,
        lease_owner="worker-a",
        lease_expires_at=NOW_EPOCH + 60,
        command_version=4,
        branch_results_digest=account_deletion_repo.branch_results_digest({}),
    )
    table = _ClaimExpressionTable(_command())

    next_claim = account_deletion_repo.renew_deletion_command_claim(
        _command(),
        claim=claim,
        now_epoch=NOW_EPOCH,
        lease_expires_at=NOW_EPOCH + 120,
        now_iso=NOW,
        table=table,
    )

    assert next_claim.command_version == claim.command_version + 1
    assert next_claim.lease_expires_at == NOW_EPOCH + 120
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


def test_parent_scrub_retries_version_cas_and_never_replaces_concurrent_preferences(
    fake_table, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanned = {
        "PK": "USER#parent-1",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": "parent-1",
        "version": 3,
        "preferences": {"digest": "weekly"},
        "child_summaries": [{"student_id": "student-1", "name": "private"}],
    }
    fake_table.seed(
        # The parent changed a preference after the deletion read the profile.
        {**scanned, "version": 4, "preferences": {"digest": "daily"}},
        {"PK": "USER#parent-1", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 7},
        {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE", "status": "deletion_pending",
         "generation": 7},
    )
    real_transact = db_table.transact
    attempts: list[int] = []

    def transact(operations, *, table=None):
        for operation in operations:
            update = operation.get("Update") or operation.get("Put") or {}
            if (update.get("Key") or update.get("Item", {})).get("SK") == "PROFILE":
                attempts.append(update["ExpressionAttributeValues"][":expected_version"])
        return real_transact(operations, table=table)

    monkeypatch.setattr(db_table, "transact", transact)

    account_deletion_repo.scrub_parent_profile_child(
        scanned, child_user_id="student-1", generation=7
    )

    current = fake_table.rows[("USER#parent-1", "PROFILE")]
    assert attempts == [3, 4]
    assert current["version"] == 5
    assert current["preferences"] == {"digest": "daily"}
    assert current["child_summaries"] == []


def test_fresh_parent_rescan_removes_only_child_and_advances_row_version(fake_table) -> None:
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
    fake_table.seed(
        profile,
        {"PK": "USER#parent-1", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 9},
        {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE", "status": "deletion_pending",
         "generation": 7},
    )

    account_deletion_repo.scrub_parent_profile_child(
        dict(profile), child_user_id="student-1", generation=7
    )

    current = fake_table.rows[("USER#parent-1", "PROFILE")]
    assert current["version"] == 5
    assert current["preferences"] == {"digest": "daily"}
    assert current["subscription"] == {"status": "active"}
    child_summaries = current["child_summaries"]
    assert isinstance(child_summaries, list)
    student_ids: list[str] = []
    for row in child_summaries:
        assert isinstance(row, Mapping)
        student_id = row.get("student_id")
        assert isinstance(student_id, str)
        student_ids.append(student_id)
    assert student_ids == ["student-2"]


