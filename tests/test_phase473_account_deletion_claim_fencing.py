"""Plan 473-36 race contracts for the permanent account-deletion proof."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import datetime
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


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
        return {"Attributes": dict(self.attributes)}


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
