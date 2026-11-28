"""Plan 473-34 notification, assistance, device, and realtime deletion contracts."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import notification_repo, websocket_repo
from stoa.services.notifications import _ledger
from fakes.dynamodb import from_wire


STUDENT_ID = "student-notification-delete"
GENERATION = 7
NOW = "2026-07-18T11:00:00+00:00"


def _contract(module: Any, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"Plan 473-34 contract {module.__name__}.{name} is not implemented")
    return value


def _event(**overrides: Any) -> dict[str, Any]:
    item = {
        "PK": "NOTIFICATION#event-private",
        "SK": "META",
        "entity_type": "notification_event",
        "schema_version": "notification-event.v2",
        "event_id": "event-private",
        "owner_id": STUDENT_ID,
        "account_fence_generation": GENERATION,
        "recipient_id": None,
        "recipient_role": "teacher",
        "event_type": "teacher_requested",
        "target_type": "question",
        "target_id": "question-private",
        "title": "private title canary",
        "summary": "private summary canary",
        "metadata": {
            "student_id": STUDENT_ID,
            "subject": "private subject canary",
            "push_delivery_attempts": [{"token_references": ["private-token"]}],
        },
        "actor_id": STUDENT_ID,
        "category": "teacher_responses",
        "status": "created",
        "created_at": NOW,
    }
    item.update(overrides)
    return item


def test_source_registry_closes_rows_writers_private_fields_and_external_boundary() -> None:
    rows = _contract(notification_repo, "NOTIFICATION_PRIVATE_ROW_REGISTRY")
    writers = _contract(notification_repo, "NOTIFICATION_WRITER_REGISTRY")
    private = _contract(notification_repo, "NOTIFICATION_PRIVATE_FIELDS")
    connection_writers = _contract(websocket_repo, "WEBSOCKET_WRITER_REGISTRY")
    assert {
        "notification_event",
        "teacher_assistance_summary_seed",
        "notification_preference",
        "notification_push_token",
        "notification_delivery_intent",
    } <= set(rows)
    assert {
        "put_event",
        "update_event",
        "put_preferences",
        "put_push_token",
        "update_push_token",
        "register_delivery_intent",
        "claim_delivery_intent",
        "begin_delivery_effect",
        "recover_delivery_intent",
        "complete_delivery_intent",
    } <= set(writers)
    assert {
        "title",
        "summary",
        "target_id",
        "metadata",
        "question_summary",
        "ai_answer_summary",
        "student_context_summary",
        "weak_topics",
        "suggested_focus",
        "token_hash",
        "provider_token_reference",
        "device_id_hash",
        "endpoint_url",
        "subscribed_channels",
    } <= set(private)
    assert {
        "put_connection",
        "refresh_connection",
        "subscribe_connection",
        "fanout_notification_event",
    } <= set(connection_writers)
    assert _contract(notification_repo, "EXTERNAL_DELIVERY_RETENTION_BOUNDARY") == {
        "provider_accepted_or_unknown": "outside_backend_deletion_control"
    }


def test_private_event_and_connection_write_builders_start_with_exact_fence() -> None:
    event_ops = _contract(notification_repo, "build_notification_write_transaction")(
        item=_event(), owner_id=STUDENT_ID, generation=GENERATION, mode="put"
    )
    connection_ops = _contract(websocket_repo, "build_connection_write_transaction")(
        item={
            "PK": "WS_CONN#connection-private",
            "SK": "META",
            "entity_type": "websocket_connection",
            "connection_id": "connection-private",
            "user_id": STUDENT_ID,
            "endpoint_url": "https://private-endpoint.example",
        },
        owner_id=STUDENT_ID,
        generation=GENERATION,
        mode="put",
    )
    for built in (event_ops, connection_ops):
        assert all("ConditionCheck" not in operation for operation in built)
        sent: list[list[dict[str, Any]]] = []

        class _Table:
            def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
                sent.append(from_wire(TransactItems))

        db_table.fenced(STUDENT_ID, built, generation=GENERATION, table=_Table())
        operations = sent[0]
        fence = operations[0]["ConditionCheck"]
        assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
        assert fence["ExpressionAttributeValues"][":generation"] == GENERATION
        stored = operations[1]["Put"]["Item"]
        assert stored["owner_id"] == STUDENT_ID
        assert stored["account_fence_generation"] == GENERATION


def test_private_role_broadcast_requires_authoritative_owner_or_sealed_global_classification() -> None:
    classify = _contract(_ledger, "classify_notification_owner")
    owner = classify(
        recipient_id=None,
        target_type="question",
        target_id="question-private",
        metadata={"student_id": STUDENT_ID},
        owner_id=STUDENT_ID,
        generation=GENERATION,
        global_nonprivate=False,
    )
    assert owner == {
        "owner_id": STUDENT_ID,
        "account_fence_generation": GENERATION,
        "target_type": "question",
        "target_id": "question-private",
        "classification": "private_owner",
    }
    with pytest.raises(Exception):
        classify(
            recipient_id=None,
            target_type="question",
            target_id="question-private",
            metadata={"student_id": STUDENT_ID},
            owner_id=None,
            generation=None,
            global_nonprivate=True,
        )


def test_delivery_claim_rechecks_fence_immediately_before_provider_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(notification_repo, "register_delivery_intent", lambda **_kw: {"status": "registered"})
    monkeypatch.setattr(notification_repo, "recover_delivery_intent", lambda **_kw: {"status": "registered"})

    def claim(**kwargs: Any) -> Any:
        return notification_repo.DeliveryIntentClaim(
            operation_id=kwargs["operation_id"],
            lease_owner="opaque-fence-claim",
            intent_version=2,
            lease_expires_at=kwargs["lease_expires_at"],
            scope_digest=kwargs["scope"].digest,
            payload_digest=kwargs["payload_digest"],
        )

    monkeypatch.setattr(notification_repo, "claim_delivery_intent", claim)
    monkeypatch.setattr(notification_repo, "delivery_intent_sendable", lambda **_kw: True)
    monkeypatch.setattr(
        notification_repo,
        "begin_delivery_effect",
        lambda **_kw: notification_repo.DeliveryBeginResult(
            notification_repo.DeliveryBeginDisposition.PROVEN_ACCOUNT_DELETED
        ),
    )
    def cancel_delivery_intent(**kwargs: Any) -> dict[str, Any]:
        calls.append("canceled_account_deletion")
        return dict(kwargs)

    def provider_call() -> dict[str, bool]:
        calls.append("provider")
        return {"accepted": True}

    monkeypatch.setattr(
        notification_repo, "cancel_delivery_intent", cancel_delivery_intent
    )
    result = _contract(_ledger, "run_delivery_intent")(
        owner_id=STUDENT_ID,
        generation=GENERATION,
        operation_id="delivery-private",
        channel="push",
        event_ids=["event-private"],
        payload={"title": "private title canary"},
        provider_call=provider_call,
    )
    assert "provider" not in calls
    assert result["status"] == "canceled_account_deletion"


def test_commit_then_raise_is_unknown_and_same_operation_is_not_blindly_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[str] = []
    completions: list[str] = []
    monkeypatch.setattr(notification_repo, "register_delivery_intent", lambda **_kw: {"status": "registered"})
    monkeypatch.setattr(notification_repo, "recover_delivery_intent", lambda **_kw: {"status": "registered"})

    def claim(**kwargs: Any) -> Any:
        return notification_repo.DeliveryIntentClaim(
            operation_id=kwargs["operation_id"],
            lease_owner="opaque-provider-claim",
            intent_version=2,
            lease_expires_at=kwargs["lease_expires_at"],
            scope_digest=kwargs["scope"].digest,
            payload_digest=kwargs["payload_digest"],
        )

    monkeypatch.setattr(notification_repo, "claim_delivery_intent", claim)
    monkeypatch.setattr(notification_repo, "delivery_intent_sendable", lambda **_kw: True)
    monkeypatch.setattr(
        notification_repo,
        "begin_delivery_effect",
        lambda **kw: replace(kw["claim"], intent_version=3),
    )
    def complete_delivery_intent(**kwargs: Any) -> dict[str, Any]:
        completions.append(str(kwargs["status"]))
        return dict(kwargs)

    monkeypatch.setattr(
        notification_repo, "complete_delivery_intent", complete_delivery_intent
    )

    def ambiguous() -> None:
        provider_calls.append("accepted")
        raise TimeoutError("lost provider response with private diagnostics")

    result = _contract(_ledger, "run_delivery_intent")(
        owner_id=STUDENT_ID,
        generation=GENERATION,
        operation_id="delivery-ambiguous",
        channel="push",
        event_ids=["event-private"],
        payload={"summary": "private summary canary"},
        provider_call=ambiguous,
    )
    assert provider_calls == ["accepted"]
    assert completions == ["provider_acceptance_unknown"]
    assert result == {"status": "provider_acceptance_unknown"}
    assert "private diagnostics" not in repr(result)


def test_connection_update_keeps_the_generation_the_row_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale connection must be rewritten under its own fence generation.

    The resource interface returns the stored generation as `Decimal`, so a
    guard written against `int` misses it and falls through to the live fence -
    which is how a row left behind by an earlier account silently adopts the
    generation of the current one.
    """
    connection = {
        "PK": "WS_CONN#connection-private",
        "SK": "META",
        "entity_type": "websocket_connection",
        "connection_id": "connection-private",
        "owner_id": STUDENT_ID,
        "user_id": STUDENT_ID,
        "account_fence_generation": Decimal(GENERATION),
        "endpoint_url": "https://private-endpoint.example",
    }
    transactions: list[list[dict[str, Any]]] = []

    class _Table:
        def get_item(self, *, Key: dict[str, str], **_kwargs: Any) -> dict[str, Any]:
            if Key["SK"] == "ACCOUNT_FENCE":
                return {
                    "Item": {
                        **Key,
                        "status": "active",
                        "generation": Decimal(GENERATION + 1),
                    }
                }
            if Key["PK"] == connection["PK"]:
                return {"Item": dict(connection)}
            return {}

        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            operations = from_wire(TransactItems)
            transactions.append(operations)

    db_table.install(_Table())
    updated = websocket_repo.update_connection(
        "connection-private", {"subscribed_channels": ["notifications"]}
    )

    assert updated is not None
    assert len(transactions) == 1
    fence = transactions[0][0]["ConditionCheck"]
    assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert fence["ExpressionAttributeValues"][":generation"] == GENERATION

    # Negative control: widening the read to Decimal must not widen it to
    # everything. A value the table could never have stored as a number still
    # falls through to the live fence.
    for malformed in ("7", True, Decimal("7.5"), None):
        transactions.clear()
        connection["account_fence_generation"] = malformed
        websocket_repo.update_connection(
            "connection-private", {"subscribed_channels": ["notifications"]}
        )
        assert transactions[0][0]["ConditionCheck"]["ExpressionAttributeValues"][
            ":generation"
        ] == GENERATION + 1


# -- one answer to "whom does this notification name" (#574) ------------------------


def test_the_catalog_says_whose_a_notification_is_and_the_registry_agrees() -> None:
    """Whose a notification is comes from the data type catalog (#574, #588).

    For each field a notification could name an account in, asked of each
    side: the owner registry files it for the same accounts in the same role
    the catalog gives (#589), and the notification module tombstones it for an
    owner and scrubs a mention out of it. (The family scans that were asked too
    went with the old deletion branches, #642.)
    """
    owners = {"owner_id", "student_id"}
    references = {"actor_id", "teacher_id", "parent_id"}
    other = "account-named"
    candidates = owners | references | {
        "user_id", "child_id", "recipient_id", "created_by", "beneficiary_id", "subject"
    }
    for field in sorted(candidates):
        row = {
            "PK": "NOTIFICATION#parity", "SK": "META", "entity_type": "notification_event",
            "owner_id": STUDENT_ID, "metadata": {field: other},
        }
        role = data_catalog.role_of(row, other)
        assert role == (
            data_catalog.OWNER if field in owners
            else data_catalog.REFERENCE if field in references
            else None
        ), field
        assert _registered(row).get(other) == role, field
        assert notification_repo._targets_owner(row, other) == (role == data_catalog.OWNER)
        assert notification_repo._targets_identity_reference(row, other) == (
            role == data_catalog.REFERENCE
        ), field

    row = {
        "PK": "NOTIFICATION#parity", "SK": "META", "entity_type": "notification_event",
        "owner_id": STUDENT_ID, "actor_id": other, "metadata": {},
    }
    assert data_catalog.role_of(row, other) == data_catalog.REFERENCE
    assert notification_repo._targets_identity_reference(row, other)
    assert _registered(row)[other] == "reference"


def _registered(row: dict) -> dict[str, str]:
    """Whom the owner registry files `row` under, and in which role, when it is written."""
    return {
        put["Put"]["Item"]["registry_account"]: put["Put"]["Item"]["role"]
        for put in owner_registry.registry_operations(None, (), [{"Put": {"Item": row}}])
    }
