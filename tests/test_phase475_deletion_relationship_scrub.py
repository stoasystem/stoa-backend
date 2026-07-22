"""Plan 475-26 formal parent relationship deletion proof."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


PARENT_ID = "parent-deleting"
STUDENT_ID = "student-retained"
GENERATION = 9


def _binding(*, forward: bool, status: str = "active", version: int = 4) -> dict[str, object]:
    return {
        "PK": f"USER#{PARENT_ID if forward else STUDENT_ID}",
        "SK": f"{'CHILD' if forward else 'PARENT'}#{STUDENT_ID if forward else PARENT_ID}",
        "entity_type": "parent_student_binding",
        "parent_id": PARENT_ID,
        "student_id": STUDENT_ID,
        "relationship": "child",
        "status": status,
        "version": version,
        "source": "admin_lifecycle",
        "actor": "admin-retained",
    }


def _profile() -> dict[str, object]:
    return {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "PROFILE",
        "entity_type": "user_profile",
        "user_id": STUDENT_ID,
        "role": "student",
        "account_status": "active",
        "version": 8,
        "parent_id": PARENT_ID,
        "relationship": "child",
        "parent_binding_status": "active",
        "preferences": {
            "digest": "weekly",
            "nested": ["byte", "identical", {"retained": True}],
        },
        "locale": "de-CH",
        "display_name": "Retained Student",
    }


class _RelationshipDeletionTable:
    def __init__(self) -> None:
        forward = _binding(forward=True)
        reverse = _binding(forward=False)
        profile = _profile()
        self.rows: dict[tuple[str, str], dict[str, object]] = {
            (str(forward["PK"]), str(forward["SK"])): forward,
            (str(reverse["PK"]), str(reverse["SK"])): reverse,
            (str(profile["PK"]), str(profile["SK"])): profile,
            (f"USER#{PARENT_ID}", "ACCOUNT_FENCE"): {
                "PK": f"USER#{PARENT_ID}",
                "SK": "ACCOUNT_FENCE",
                "status": "deletion_pending",
                "generation": GENERATION,
            },
        }
        self.cas_raced = False
        self.transactions: list[list[dict[str, Any]]] = []

    def scan(self, **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        assert "IndexName" not in kwargs
        return {"Items": [deepcopy(row) for row in self.rows.values()]}

    def get_item(self, *, Key: dict[str, str], **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        item = self.rows.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        self.transactions.append(deepcopy(operations))
        assert len(operations) == 4
        assert operations[0]["ConditionCheck"]["Key"] == {
            "PK": f"USER#{PARENT_ID}",
            "SK": "ACCOUNT_FENCE",
        }

        deletes = [operation["Delete"] for operation in operations[1:3]]
        update = operations[3]["Update"]
        assert [delete["Key"] for delete in deletes] == [
            {"PK": f"USER#{PARENT_ID}", "SK": f"CHILD#{STUDENT_ID}"},
            {"PK": f"USER#{STUDENT_ID}", "SK": f"PARENT#{PARENT_ID}"},
        ]
        assert update["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "PROFILE"}

        if not self.cas_raced:
            self.cas_raced = True
            for delete in deletes:
                current = self.rows[(delete["Key"]["PK"], delete["Key"]["SK"])]
                current["status"] = "inactive"
                current["version"] = 5
            profile = self.rows[(f"USER#{STUDENT_ID}", "PROFILE")]
            profile["parent_binding_status"] = "inactive"
            profile["version"] = 9
            profile["preferences"] = {
                "digest": "daily",
                "nested": ["byte", "identical", {"retained": True}],
                "concurrent": "must survive",
            }
            raise account_deletion_repo.AccountDeletionConflict(
                "conditional relationship cleanup conflict"
            )

        for delete in deletes:
            key = (delete["Key"]["PK"], delete["Key"]["SK"])
            current = self.rows[key]
            values = delete["ExpressionAttributeValues"]
            assert current["PK"] == values[":pk"]
            assert current["SK"] == values[":sk"]
            assert current["entity_type"] == values[":entity"]
            assert current["parent_id"] == values[":parent_id"]
            assert current["student_id"] == values[":student_id"]
            assert current["relationship"] == values[":relationship"]
            assert current["status"] == values[":status"]
            assert current["version"] == values[":version"]

        profile = self.rows[(f"USER#{STUDENT_ID}", "PROFILE")]
        values = update["ExpressionAttributeValues"]
        assert profile["user_id"] == values[":student_id"]
        assert profile["parent_id"] == values[":parent_id"]
        assert profile["relationship"] == values[":relationship"]
        assert profile["parent_binding_status"] == values[":status"]
        assert profile["version"] == values[":version"]

        for delete in deletes:
            self.rows.pop((delete["Key"]["PK"], delete["Key"]["SK"]))
        profile.pop("parent_id")
        profile.pop("relationship")
        profile.pop("parent_binding_status")
        profile["version"] = values[":next_version"]


def _relationship_rows(table: _RelationshipDeletionTable) -> list[dict[str, object]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == "parent_student_binding"
    ]


def test_relationship_identity_scrub_retries_cas_then_requires_two_clean_epochs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _RelationshipDeletionTable()
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
    command = {"user_id": PARENT_ID, "generation": GENERATION}
    branch = account_deletion_service.BRANCH_HANDLERS["account_profile"]

    first = branch(command=command, previous={})
    assert first.status == "retryable"
    assert first.epoch == 0 and first.quiescent is False
    assert first.debt_counts == {"row_conflict": 1, "pass_dirty": 1}
    assert table.cas_raced is True
    assert {(row["status"], row["version"]) for row in _relationship_rows(table)} == {
        ("inactive", 5)
    }
    raced_profile = table.rows[(f"USER#{STUDENT_ID}", "PROFILE")]
    assert raced_profile["parent_id"] == PARENT_ID
    assert raced_profile["parent_binding_status"] == "inactive"
    assert raced_profile["version"] == 9
    retained_after_race = deepcopy(raced_profile["preferences"])

    results = [first]
    previous: dict[str, object] = asdict(first)
    for _ in range(3):
        result = branch(command=command, previous=previous)
        results.append(result)
        previous = asdict(result)

    assert [(result.status, result.epoch) for result in results] == [
        ("retryable", 0),
        ("retryable", 0),
        ("retryable", 1),
        ("complete", 2),
    ]
    assert results[-1].quiescent is True
    assert _relationship_rows(table) == []

    profile = table.rows[(f"USER#{STUDENT_ID}", "PROFILE")]
    assert profile["version"] == 10
    assert "parent_id" not in profile
    assert "relationship" not in profile
    assert "parent_binding_status" not in profile
    assert profile["preferences"] == retained_after_race
    assert profile["locale"] == "de-CH"
    assert profile["display_name"] == "Retained Student"

    cleanup_transaction = table.transactions[-1]
    for delete in (cleanup_transaction[1]["Delete"], cleanup_transaction[2]["Delete"]):
        condition = delete["ConditionExpression"]
        assert all(
            fragment in condition
            for fragment in (
                "PK=:pk",
                "SK=:sk",
                "entity_type=:entity",
                "parent_id=:parent_id",
                "student_id=:student_id",
                "#relationship=:relationship",
                "#status=:status",
                "#version=:version",
            )
        )
    profile_condition = cleanup_transaction[3]["Update"]["ConditionExpression"]
    assert all(
        fragment in profile_condition
        for fragment in (
            "user_id=:student_id",
            "parent_id=:parent_id",
            "#relationship=:relationship",
            "parent_binding_status=:status",
            "#version=:version",
        )
    )
