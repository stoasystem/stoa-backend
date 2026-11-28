"""Plan 475-28 notification actor and metadata identity deletion proof, through the catalog flow (#642)."""

from __future__ import annotations

from copy import deepcopy

import pytest

import deletion_helpers
from fakes.dynamodb import as_stored as _as_stored
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notifications


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
    return _as_stored({
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
    })


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


def test_a_malformed_mention_is_refused_before_anything_is_written(fake_table) -> None:
    malformed = _event("malformed", actor_id=IDENTITY, metadata=[IDENTITY])
    fake_table.seed(
        malformed,
        {**account_deletion_repo.account_fence_key(IDENTITY), "status": "deletion_pending",
         "generation": GENERATION},
    )
    before = deepcopy(fake_table.rows)

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        notifications.scrub_notification_identity_references(
            malformed, owner_id=IDENTITY, generation=GENERATION
        )

    assert fake_table.rows == before


def test_notification_identity_scrub_retries_a_moved_event_and_keeps_its_write(
    fake_table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The teacher's whole deletion, as production runs it (#642)."""
    rows = [
        _event("direct", actor_id=IDENTITY),
        _event(
            "metadata",
            metadata={
                "teacher_id": IDENTITY,
                "actor_id": IDENTITY,
                "subject": "Geometry",
                "delivery_decision": {"in_app": "accepted"},
            },
            status="accepted",
        ),
        _event(
            "parent",
            metadata={
                "parent_id": IDENTITY,
                "subject": "Retained subject",
                "delivery_decision": {"in_app": "accepted"},
            },
            version=4,
        ),
    ]
    fake_table.seed(*rows)
    deletion_helpers.register(fake_table, *rows)
    deletion_helpers.active_fence(fake_table, IDENTITY, generation=GENERATION)
    retained = {(row["PK"], row["SK"]): _retained_snapshot(row) for row in rows}

    real_transact = db_table.transact
    raced: list[bool] = []
    conditions: list[str] = []

    def transact(operations, *, table=None):
        for op in operations:
            update = op.get("Update") or {}
            if str((update.get("Key") or {}).get("PK", "")).startswith("NOTIFICATION#"):
                conditions.append(update["ConditionExpression"])
                if update["Key"]["PK"] == "NOTIFICATION#direct" and not raced:
                    raced.append(True)
                    current = fake_table.rows[("NOTIFICATION#direct", "META")]
                    current["event_version"] = _as_stored(int(current["event_version"]) + 1)
                    current["metadata"] = {
                        **current["metadata"], "concurrent_note": "preserve this write"
                    }
        return real_transact(operations, table=table)

    monkeypatch.setattr(db_table, "transact", transact)

    command = deletion_helpers.delete_account(IDENTITY)

    assert raced
    assert command["status"] == "complete"
    for key, row in fake_table.rows.items():
        if key not in retained:
            continue
        assert row.get("actor_id") != IDENTITY
        metadata = row["metadata"]
        assert isinstance(metadata, dict)
        assert IDENTITY not in {
            metadata.get("actor_id"),
            metadata.get("teacher_id"),
            metadata.get("parent_id"),
        }
        assert _retained_snapshot(row) == retained[key]
    assert fake_table.rows[("NOTIFICATION#direct", "META")]["metadata"] == {
        "subject": "Algebra",
        "delivery_decision": {"in_app": "accepted"},
        "concurrent_note": "preserve this write",
    }
    assert fake_table.rows[("NOTIFICATION#metadata", "META")]["metadata"] == {
        "subject": "Geometry",
        "delivery_decision": {"in_app": "accepted"},
    }
    assert fake_table.rows[("NOTIFICATION#parent", "META")]["metadata"] == {
        "subject": "Retained subject",
        "delivery_decision": {"in_app": "accepted"},
    }
    assert conditions and all(
        "entity_type=:entity" in condition
        and "schema_version=:schema" in condition
        and "event_version=:version" in condition
        and "#status=:status" in condition
        and "metadata=:metadata" in condition
        for condition in conditions
    )
