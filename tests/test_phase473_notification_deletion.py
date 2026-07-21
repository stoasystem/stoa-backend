"""Plan 473-34 notification, assistance, device, and realtime deletion contracts."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, notification_repo, websocket_repo
from stoa.services import account_deletion_service, notification_service


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
        "put_summary_seed",
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
    for operations in (event_ops, connection_ops):
        fence = operations[0]["ConditionCheck"]
        assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
        assert fence["ExpressionAttributeValues"][":generation"] == GENERATION
        stored = operations[1]["Put"]["Item"]
        assert stored["owner_id"] == STUDENT_ID
        assert stored["account_fence_generation"] == GENERATION


def test_private_role_broadcast_requires_authoritative_owner_or_sealed_global_classification() -> None:
    classify = _contract(notification_service, "classify_notification_owner")
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
    monkeypatch.setattr(
        notification_repo,
        "cancel_delivery_intent",
        lambda **kw: calls.append("canceled_account_deletion") or dict(kw),
    )
    result = _contract(notification_service, "run_delivery_intent")(
        owner_id=STUDENT_ID,
        generation=GENERATION,
        operation_id="delivery-private",
        channel="push",
        event_ids=["event-private"],
        payload={"title": "private title canary"},
        provider_call=lambda: calls.append("provider") or {"accepted": True},
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
    monkeypatch.setattr(
        notification_repo,
        "complete_delivery_intent",
        lambda **kw: completions.append(str(kw["status"])) or dict(kw),
    )

    def ambiguous() -> None:
        provider_calls.append("accepted")
        raise TimeoutError("lost provider response with private diagnostics")

    result = _contract(notification_service, "run_delivery_intent")(
        owner_id=STUDENT_ID,
        generation=GENERATION,
        operation_id="delivery-ambiguous",
        channel="email_digest",
        event_ids=["event-private"],
        payload={"summary": "private summary canary"},
        provider_call=ambiguous,
    )
    assert provider_calls == ["accepted"]
    assert completions == ["provider_acceptance_unknown"]
    assert result == {"status": "provider_acceptance_unknown"}
    assert "private diagnostics" not in repr(result)


def test_strong_paginated_scans_and_scrubs_leave_only_strict_tombstones() -> None:
    notification_pages = [
        {
            "Items": [_event()],
            "LastEvaluatedKey": {"PK": "NOTIFICATION#event-private", "SK": "META"},
        },
        {
            "Items": [
                {
                    "PK": "ASSISTANCE_SUMMARY#late",
                    "SK": "META",
                    "entity_type": "teacher_assistance_summary_seed",
                    "summary_id": "late",
                    "student_id": STUDENT_ID,
                    "question_summary": "late private canary",
                }
            ]
        },
    ]
    connection_pages = [
        {
            "Items": [
                {
                    "PK": "WS_CONN#private",
                    "SK": "META",
                    "entity_type": "websocket_connection",
                    "connection_id": "private",
                    "user_id": STUDENT_ID,
                    "owner_id": STUDENT_ID,
                    "endpoint_url": "https://private-endpoint.example",
                    "subscribed_channels": [f"user:{STUDENT_ID}"],
                }
            ]
        }
    ]
    calls: list[dict[str, Any]] = []
    tombstones: list[dict[str, Any]] = []

    class _Table:
        def __init__(self, pages: list[dict[str, Any]]) -> None:
            self.pages = pages

        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return self.pages.pop(0)

        def replace_notification_tombstone(self, _old: Any, new: Any, *_args: Any) -> None:
            tombstones.append(new)

        def delete_connection_for_account(self, *_args: Any, **_kwargs: Any) -> None:
            tombstones.append({"deleted_connection": True})

    notifications = _Table(notification_pages)
    scan = _contract(notification_repo, "scan_notification_private_rows")
    first = scan(STUDENT_ID, table=notifications, maximum_pages=1)
    second = scan(STUDENT_ID, table=notifications, cursor=first.cursor, maximum_pages=1)
    for item in (*first.items, *second.items):
        _contract(notification_repo, "scrub_notification_private_row")(
            item,
            owner_id=STUDENT_ID,
            generation=GENERATION,
            now_iso=NOW,
            table=notifications,
        )

    connections = _Table(connection_pages)
    page = _contract(websocket_repo, "scan_account_connections")(
        STUDENT_ID, table=connections, maximum_pages=1
    )
    for item in page.items:
        _contract(websocket_repo, "revoke_account_connection")(
            item,
            owner_id=STUDENT_ID,
            generation=GENERATION,
            table=connections,
        )

    assert all(call.get("ConsistentRead") is True and "IndexName" not in call for call in calls)
    allowlist = _contract(notification_repo, "NOTIFICATION_TOMBSTONE_ALLOWLIST")
    assert all(
        set(item) <= allowlist
        for item in tombstones
        if "deleted_connection" not in item
    )
    assert "private canary" not in repr(tombstones)
    assert "private-endpoint" not in repr(tombstones)


def test_notification_branch_is_registered_and_requires_two_later_clean_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "notification_device_realtime" in account_deletion_service.BRANCH_HANDLERS
    page_type = _contract(notification_repo, "NotificationPrivatePage")
    connection_page_type = _contract(websocket_repo, "ConnectionPrivatePage")
    notification_pages = [
        page_type(items=(_event(),)),
        page_type(items=()),
        page_type(items=()),
    ]
    connection_pages = [connection_page_type(items=()) for _ in range(3)]
    monkeypatch.setattr(
        notification_repo,
        "scan_notification_private_rows",
        lambda *_a, **_kw: notification_pages.pop(0),
    )
    monkeypatch.setattr(
        websocket_repo,
        "scan_account_connections",
        lambda *_a, **_kw: connection_pages.pop(0),
    )
    monkeypatch.setattr(notification_repo, "scrub_notification_private_row", lambda *_a, **_kw: None)
    monkeypatch.setattr(websocket_repo, "revoke_account_connection", lambda *_a, **_kw: None)
    branch = account_deletion_service.BRANCH_HANDLERS["notification_device_realtime"]
    command = {"user_id": STUDENT_ID, "generation": GENERATION}
    first = branch(command=command, previous={})
    second = branch(command=command, previous=asdict(first))
    third = branch(command=command, previous=asdict(second))
    assert first.status == "retryable" and first.epoch == 0
    assert second.status == "retryable" and second.epoch == 1
    assert third.status == "complete" and third.quiescent is True and third.epoch == 2
