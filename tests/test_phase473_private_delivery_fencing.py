"""Plan 473-38 authoritative notification-delivery regression matrix."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import pytest

from stoa.config import Settings
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notification_service, websocket_service


OWNER = "student-private-delivery"
GENERATION = 7
EVENT_ID = "event-private-delivery"


def _private_event(**overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"NOTIFICATION#{EVENT_ID}",
        "SK": "META",
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "event_id": EVENT_ID,
        "owner_classification": "private_owner",
        "owner_id": OWNER,
        "account_fence_generation": GENERATION,
        "recipient_id": OWNER,
        "recipient_role": "student",
        "event_type": "teacher_reply",
        "target_type": "question",
        "target_id": "question-private-delivery",
        "title": "Private title canary",
        "summary": "Private summary canary",
        "metadata": {},
        "category": "teacher_responses",
        "status": "created",
        "created_at": "2026-07-18T15:30:00+00:00",
    }
    item.update(overrides)
    return item


class _StrongTable:
    def __init__(self, rows: Mapping[tuple[str, str], Mapping[str, Any]]) -> None:
        self.rows = {key: dict(value) for key, value in rows.items()}
        self.reads: list[dict[str, Any]] = []

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.reads.append(deepcopy(kwargs))
        key = kwargs["Key"]
        item = self.rows.get((key["PK"], key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}


def _ready_settings() -> Settings:
    return Settings(
        notification_email_provider="ses",
        notification_email_provider_approved=True,
        notification_email_send_enabled=True,
        notification_push_provider="native-relay",
        notification_push_provider_approved=True,
        notification_push_provider_endpoint_url="https://push.example.test/send",
        notification_push_send_enabled=True,
    )


def test_strong_event_loader_uses_exact_base_key_and_consistent_read() -> None:
    event = _private_event()
    table = _StrongTable({(event["PK"], event["SK"]): event})

    loaded = notification_repo.load_delivery_event_strong(EVENT_ID, table=table)

    assert loaded == event
    assert table.reads == [
        {
            "Key": {"PK": f"NOTIFICATION#{EVENT_ID}", "SK": "META"},
            "ConsistentRead": True,
        }
    ]


@pytest.mark.parametrize(
    "generation",
    [None, "7", True, 0, -1, GENERATION + 1],
)
def test_private_push_rejects_missing_malformed_or_stale_persisted_generation(
    monkeypatch: pytest.MonkeyPatch,
    generation: Any,
) -> None:
    persisted = _private_event(account_fence_generation=generation)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(notification_service, "settings", _ready_settings())
    monkeypatch.setattr(
        notification_repo,
        "load_delivery_event_strong",
        lambda _event_id: deepcopy(persisted),
        raising=False,
    )
    monkeypatch.setattr(
        notification_repo,
        "list_push_tokens",
        lambda *_args, **_kwargs: [
            {
                "provider_token_reference": "opaque-provider-reference",
                "status": "active",
            }
        ],
    )
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda *_args, **_kwargs: {"status": "active", "generation": GENERATION},
    )

    result = notification_service.attempt_push_delivery(
        {**persisted, "account_fence_generation": GENERATION},
        send_func=lambda payload: calls.append(payload),
    )

    assert result["status"] in {
        "delivery_scope_mismatch",
        "delivery_owner_unresolved",
        "canceled_account_deletion",
    }
    assert calls == []


def test_legacy_question_owner_resolution_uses_closed_strong_target_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _private_event(
        schema_version="notification-event.v1",
        event_version=0,
        owner_classification=None,
        owner_id=None,
        account_fence_generation=None,
        recipient_id="forged-recipient",
        actor_id="forged-actor",
    )
    question = {
        "PK": "QUESTION#question-private-delivery",
        "SK": "META",
        "question_id": "question-private-delivery",
        "student_id": OWNER,
        "account_fence_generation": GENERATION,
    }
    table = _StrongTable({(question["PK"], question["SK"]): question})
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda owner_id, generation=None, **_kwargs: {
            "status": "active",
            "generation": GENERATION,
            "owner": owner_id,
        },
    )

    ownership = notification_service.resolve_delivery_ownership(legacy, table=table)

    assert ownership.kind == "private_owner"
    assert ownership.owner_id == OWNER
    assert ownership.generation == GENERATION
    assert set(notification_service.LEGACY_NOTIFICATION_OWNER_RESOLVERS) >= {
        "question",
        "moderation_case",
        "report",
        "assignment",
        "learning_profile",
        "recommendation",
        "subscription_request",
    }
    assert table.reads[0] == {
        "Key": {"PK": "QUESTION#question-private-delivery", "SK": "META"},
        "ConsistentRead": True,
    }


def test_legacy_metadata_only_owner_fails_closed_without_target() -> None:
    legacy = _private_event(
        schema_version="notification-event.v1",
        event_version=0,
        owner_classification=None,
        owner_id=None,
        account_fence_generation=None,
        metadata={"student_id": OWNER, "privacy_generation": GENERATION},
        recipient_id=OWNER,
        actor_id=OWNER,
    )
    table = _StrongTable({})

    with pytest.raises(notification_service.DeliveryOwnershipError) as caught:
        notification_service.resolve_delivery_ownership(legacy, table=table)

    assert caught.value.status == "delivery_owner_unresolved"
    assert OWNER not in str(caught.value)


def test_global_nonprivate_requires_exact_persisted_contract_digest() -> None:
    raw = _private_event(
        owner_classification="global_nonprivate",
        owner_id=None,
        account_fence_generation=None,
        recipient_id=None,
        recipient_role="admin",
        event_type="moderation_case_update",
        target_type="system_status",
        target_id="privacy-maintenance",
        title="Maintenance complete",
        summary="Service is available.",
        metadata={},
    )
    sealed = notification_repo.seal_global_nonprivate_event(raw)
    ownership = notification_service.resolve_delivery_ownership(sealed)

    assert ownership.kind == "global_nonprivate"
    assert ownership.classification_seal == sealed["classification_digest"]

    for forged in (
        {**sealed, "classification_digest": "0" * 64},
        {**sealed, "metadata": {"student_id": OWNER}},
        {**sealed, "owner_id": OWNER},
        {**raw, "global_nonprivate": True},
    ):
        with pytest.raises(notification_service.DeliveryOwnershipError) as caught:
            notification_service.resolve_delivery_ownership(forged)
        assert caught.value.status == "delivery_classification_invalid"


def test_mixed_owner_digest_is_refused_before_email_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _private_event()
    second = _private_event(
        event_id="event-private-delivery-2",
        PK="NOTIFICATION#event-private-delivery-2",
        owner_id="student-foreign",
    )
    events = {first["event_id"]: first, second["event_id"]: second}
    calls: list[dict[str, Any]] = []
    preferences = notification_service.default_preferences()
    preferences["teacher_responses"]["email_digest"] = True
    monkeypatch.setattr(notification_service, "settings", _ready_settings())
    monkeypatch.setattr(notification_repo, "list_events", lambda **_kwargs: list(events.values()))
    monkeypatch.setattr(notification_repo, "get_preferences", lambda _user_id: {"preferences": preferences})
    monkeypatch.setattr(notification_repo, "update_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        notification_repo,
        "load_delivery_event_strong",
        lambda event_id: deepcopy(events[event_id]),
        raising=False,
    )
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda owner_id, *_args, **_kwargs: {
            "status": "active",
            "generation": GENERATION,
            "owner": owner_id,
        },
    )

    result = notification_service.send_digest(
        {"sub": OWNER, "role": "student", "email": "student@example.test"},
        send_func=lambda payload: calls.append(payload),
    )

    assert result["status"] == "delivery_scope_mismatch"
    assert calls == []


def test_websocket_invalid_persisted_scope_lists_no_connections_and_posts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = _private_event(account_fence_generation=None)
    listed: list[str] = []
    posted: list[tuple[dict[str, Any], dict[str, Any]]] = []
    monkeypatch.setattr(
        notification_repo,
        "load_delivery_event_strong",
        lambda _event_id: deepcopy(persisted),
        raising=False,
    )
    monkeypatch.setattr(
        websocket_service.websocket_repo,
        "list_connections",
        lambda **_kwargs: listed.append("listed") or [],
    )

    result = websocket_service.fanout_notification_event(
        {**persisted, "account_fence_generation": GENERATION},
        post_func=lambda connection, envelope: posted.append((connection, envelope)),
    )

    assert result["status"] in {
        "delivery_scope_mismatch",
        "delivery_owner_unresolved",
    }
    assert listed == []
    assert posted == []
