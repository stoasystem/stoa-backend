"""Plan 475-28 notification actor and metadata identity deletion proof."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, notification_repo, websocket_repo
from stoa.services import account_deletion_service


IDENTITY = "teacher-deleting"
GENERATION = 9
NOW = "2026-07-22T09:30:00+00:00"


def _event(
    event_id: str,
    *,
    actor_id: str | None = None,
    metadata: object | None = None,
    version: int = 1,
    status: str = "provider_acceptance_unknown",
) -> dict[str, object]:
    return {
        "PK": f"NOTIFICATION#{event_id}",
        "SK": "META",
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": version,
        "event_id": event_id,
        "owner_id": "student-recipient",
        "account_fence_generation": 4,
        "recipient_id": "student-recipient",
        "recipient_role": "student",
        "event_type": "teacher_takeover",
        "target_type": "question",
        "target_id": "question-retained",
        "actor_id": actor_id,
        "actor_role": "teacher",
        "status": status,
        "effect_state": "effect_complete",
        "outcome_status": status,
        "accepted_at": NOW,
        "delivery_receipt": {"channel": "in_app", "attempt": 1},
        "metadata": (
            {"subject": "Algebra", "delivery_decision": {"in_app": "accepted"}}
            if metadata is None
            else metadata
        ),
    }


class _NotificationTable:
    def __init__(self) -> None:
        self.rows = {
            ("NOTIFICATION#direct", "META"): _event("direct", actor_id=IDENTITY),
            ("NOTIFICATION#metadata", "META"): _event(
                "metadata",
                metadata={
                    "teacher_id": IDENTITY,
                    "actor_id": IDENTITY,
                    "subject": "Geometry",
                    "delivery_decision": {"in_app": "accepted"},
                },
                status="accepted",
            ),
        }
        self.scan_count = 0
        self.cas_raced = False
        self.transactions: list[list[dict[str, Any]]] = []

    def scan(self, **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        assert "IndexName" not in kwargs
        self.scan_count += 1
        if self.scan_count == 3:
            late = _event(
                "late",
                metadata={
                    "parent_id": IDENTITY,
                    "subject": "Late retained subject",
                    "delivery_decision": {"in_app": "accepted"},
                },
                version=4,
            )
            self.rows[(str(late["PK"]), str(late["SK"]))] = late
        return {"Items": [deepcopy(row) for row in self.rows.values()]}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        self.transactions.append(deepcopy(operations))
        assert operations[0].get("ConditionCheck") is not None
        update = operations[1]["Update"]
        key = update["Key"]
        row_key = (key["PK"], key["SK"])
        current = self.rows[row_key]
        values = update["ExpressionAttributeValues"]

        if row_key == ("NOTIFICATION#direct", "META") and not self.cas_raced:
            self.cas_raced = True
            event_version = current["event_version"]
            metadata_value = current["metadata"]
            assert isinstance(event_version, int)
            assert isinstance(metadata_value, dict)
            current["event_version"] = event_version + 1
            metadata = dict(metadata_value)
            metadata["concurrent_note"] = "preserve this write"
            current["metadata"] = metadata
            raise account_deletion_repo.AccountDeletionConflict(
                "conditional notification identity conflict"
            )

        assert current["entity_type"] == values[":entity"]
        assert current["schema_version"] == values[":schema"]
        assert current["event_version"] == values[":version"]
        assert current["status"] == values[":status"]
        assert current["metadata"] == values[":metadata"]
        if ":identity" in values:
            assert current.get("actor_id") == values[":identity"]

        current["metadata"] = deepcopy(values[":clean_metadata"])
        current["event_version"] = values[":next_version"]
        if "REMOVE actor_id" in update["UpdateExpression"]:
            current.pop("actor_id", None)


def _retained_snapshot(item: dict[str, object]) -> dict[str, object]:
    return {
        field: deepcopy(item[field])
        for field in (
            "owner_id",
            "recipient_id",
            "recipient_role",
            "event_type",
            "target_type",
            "target_id",
            "status",
            "effect_state",
            "outcome_status",
            "accepted_at",
            "delivery_receipt",
        )
    }


def test_notification_identity_scrub_retries_cas_then_requires_two_clean_epochs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _NotificationTable()
    retained = {key: _retained_snapshot(row) for key, row in table.rows.items()}

    monkeypatch.setattr(notification_repo, "get_table", lambda: table)
    empty_connections = websocket_repo.ConnectionPrivatePage(items=())
    monkeypatch.setattr(
        websocket_repo,
        "scan_account_connections",
        lambda *_args, **_kwargs: empty_connections,
    )

    malformed = _event("malformed", actor_id=IDENTITY, metadata=[IDENTITY])
    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        notification_repo.scrub_notification_private_row(
            malformed,
            owner_id=IDENTITY,
            generation=GENERATION,
            now_iso=NOW,
            table=table,
        )
    assert table.transactions == []

    branch = account_deletion_service.BRANCH_HANDLERS["notification_device_realtime"]
    command = {"user_id": IDENTITY, "generation": GENERATION}
    results = []
    previous: dict[str, object] = {}
    for _ in range(5):
        result = branch(command=command, previous=previous)
        results.append(result)
        previous = asdict(result)

    assert table.cas_raced is True
    assert [(result.status, result.epoch) for result in results] == [
        ("retryable", 0),
        ("retryable", 0),
        ("retryable", 0),
        ("retryable", 1),
        ("complete", 2),
    ]
    assert results[-1].quiescent is True

    for key, row in table.rows.items():
        assert row.get("actor_id") != IDENTITY
        metadata = row["metadata"]
        assert isinstance(metadata, dict)
        assert IDENTITY not in {
            metadata.get("actor_id"),
            metadata.get("teacher_id"),
            metadata.get("parent_id"),
        }
        if key in retained:
            assert _retained_snapshot(row) == retained[key]
    assert table.rows[("NOTIFICATION#direct", "META")]["metadata"] == {
        "subject": "Algebra",
        "delivery_decision": {"in_app": "accepted"},
        "concurrent_note": "preserve this write",
    }
    assert table.rows[("NOTIFICATION#metadata", "META")]["metadata"] == {
        "subject": "Geometry",
        "delivery_decision": {"in_app": "accepted"},
    }
    assert table.rows[("NOTIFICATION#late", "META")]["metadata"] == {
        "subject": "Late retained subject",
        "delivery_decision": {"in_app": "accepted"},
    }

    conditions = [
        transaction[1]["Update"]["ConditionExpression"]
        for transaction in table.transactions
    ]
    assert all(
        "entity_type=:entity" in condition
        and "schema_version=:schema" in condition
        and "event_version=:version" in condition
        and "#status=:status" in condition
        and "metadata=:metadata" in condition
        for condition in conditions
    )
