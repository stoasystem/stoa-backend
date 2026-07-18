from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notification_service


OWNER = "student-delivery-owner"
GENERATION = 7
OPERATION = "delivery-operation-opaque"
PAYLOAD = {"title": "private-canary", "endpoint": "must-not-persist"}
PAYLOAD_DIGEST = notification_service._canonical_payload_digest(PAYLOAD)


def _scope() -> Any:
    return notification_repo.DeliveryIntentScope.private_owner(
        owner_id=OWNER,
        generation=GENERATION,
    )


class _ExpressionTable:
    def __init__(self, item: dict[str, Any]) -> None:
        self.item = dict(item)
        self.update_kwargs: dict[str, Any] | None = None

    def get_item(self, **_kwargs: Any) -> dict[str, Any]:
        return {"Item": dict(self.item)}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.update_kwargs = kwargs
        claimed = {
            **self.item,
            "effect_state": "claimed_pre_effect",
            "status": "claimed_pre_effect",
            "intent_version": int(self.item["intent_version"]) + 1,
            "lease_owner": kwargs["ExpressionAttributeValues"][":lease"],
            "lease_expires_at": kwargs["ExpressionAttributeValues"][":expiry"],
        }
        self.item = claimed
        return {"Attributes": claimed}


def test_repository_claim_uses_explicit_current_time_not_proposed_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = _scope()
    table = _ExpressionTable(
        {
            "PK": f"NOTIFICATION_DELIVERY#{OWNER}",
            "SK": f"INTENT#{OPERATION}",
            "operation_id": OPERATION,
            "scope_kind": "private_owner",
            "scope_digest": scope.digest,
            "payload_digest": PAYLOAD_DIGEST,
            "owner_id": OWNER,
            "account_fence_generation": GENERATION,
            "effect_state": "claimed_pre_effect",
            "status": "claimed_pre_effect",
            "intent_version": 4,
            "lease_owner": "old-opaque-owner",
            "lease_expires_at": 99,
        }
    )
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda *_args, **_kwargs: {"status": "active", "generation": GENERATION},
    )

    claim = notification_repo.claim_delivery_intent(
        scope=scope,
        operation_id=OPERATION,
        payload_digest=PAYLOAD_DIGEST,
        now_epoch=100,
        lease_expires_at=9_999,
        table=table,
    )

    assert claim.intent_version == 5
    assert table.update_kwargs is not None
    expression = table.update_kwargs["ConditionExpression"]
    values = table.update_kwargs["ExpressionAttributeValues"]
    assert "#effect=:registered OR (#effect=:pre_effect AND lease_expires_at < :now_epoch)" in expression
    assert values[":now_epoch"] == 100
    assert values[":expiry"] == 9_999


def test_unexpired_pre_effect_claim_and_inflight_are_never_takeover_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = _scope()
    monkeypatch.setattr(
        account_deletion_repo,
        "require_active_account_fence",
        lambda *_args, **_kwargs: {"status": "active", "generation": GENERATION},
    )
    for state, expiry in (("claimed_pre_effect", 101), ("effect_inflight", 0)):
        table = _ExpressionTable(
            {
                "PK": f"NOTIFICATION_DELIVERY#{OWNER}",
                "SK": f"INTENT#{OPERATION}",
                "operation_id": OPERATION,
                "scope_kind": "private_owner",
                "scope_digest": scope.digest,
                "payload_digest": PAYLOAD_DIGEST,
                "owner_id": OWNER,
                "account_fence_generation": GENERATION,
                "effect_state": state,
                "status": state,
                "intent_version": 4,
                "lease_owner": "old-owner",
                "lease_expires_at": expiry,
            }
        )
        table.update_item = lambda **_kwargs: (_ for _ in ()).throw(
            account_deletion_repo.AccountDeletionConflict("conditional loss")
        )
        assert (
            notification_repo.claim_delivery_intent(
                scope=scope,
                operation_id=OPERATION,
                payload_digest=PAYLOAD_DIGEST,
                now_epoch=100,
                lease_expires_at=190,
                table=table,
            )
            is None
        )


def test_begin_private_claim_is_one_fence_plus_exact_version_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = _scope()
    claim = notification_repo.DeliveryIntentClaim(
        operation_id=OPERATION,
        lease_owner="opaque-begin-owner",
        intent_version=8,
        lease_expires_at=190,
        scope_digest=scope.digest,
        payload_digest=PAYLOAD_DIGEST,
    )
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        account_deletion_repo,
        "transact",
        lambda operations, **_kwargs: captured.extend(operations),
    )

    begun = notification_repo.begin_delivery_effect(
        scope=scope,
        claim=claim,
        now_iso="2026-07-18T15:00:00+00:00",
        table=object(),
    )

    assert begun.intent_version == 9
    assert len(captured) == 2
    fence = captured[0]["ConditionCheck"]
    assert fence["ConditionExpression"] == "#status=:active AND generation=:generation"
    assert fence["ExpressionAttributeValues"][":generation"] == GENERATION
    update = captured[1]["Update"]
    assert "#effect=:pre_effect" in update["ConditionExpression"]
    assert "lease_owner=:lease" in update["ConditionExpression"]
    assert "intent_version=:version" in update["ConditionExpression"]
    assert "scope_digest=:scope" in update["ConditionExpression"]
    assert "payload_digest=:payload" in update["ConditionExpression"]


class _MemoryIntentStore:
    def __init__(self) -> None:
        self.item: dict[str, Any] | None = None
        self.provider_calls = 0
        self.order: list[str] = []
        self.fail_begin_after_commit = False
        self.fail_complete_after_commit = False

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(notification_repo, "register_delivery_intent", self.register)
        monkeypatch.setattr(notification_repo, "recover_delivery_intent", self.recover)
        monkeypatch.setattr(notification_repo, "claim_delivery_intent", self.claim)
        monkeypatch.setattr(notification_repo, "delivery_intent_sendable", self.sendable)
        monkeypatch.setattr(notification_repo, "begin_delivery_effect", self.begin)
        monkeypatch.setattr(notification_repo, "cancel_delivery_intent", self.cancel)
        monkeypatch.setattr(notification_repo, "complete_delivery_intent", self.complete)

    def register(self, **kwargs: Any) -> dict[str, Any]:
        self.order.append("register")
        scope = kwargs["scope"]
        if self.item is None:
            self.item = {
                "status": "registered",
                "effect_state": "registered",
                "outcome_status": None,
                "intent_version": 1,
                "scope_digest": scope.digest,
                "payload_digest": kwargs["payload_digest"],
            }
        return dict(self.item)

    def recover(self, **kwargs: Any) -> dict[str, Any]:
        self.order.append("recover")
        assert self.item is not None
        expected = kwargs.get("expected_claim")
        if expected is not None and (
            self.item.get("intent_version") != expected.intent_version
            or self.item.get("lease_owner") != expected.lease_owner
        ):
            raise account_deletion_repo.AccountDeletionConflict("stale claim")
        if self.item["effect_state"] == "effect_inflight":
            self.item.update(
                effect_state="provider_acceptance_unknown",
                status="provider_acceptance_unknown",
                outcome_status="provider_acceptance_unknown",
                intent_version=self.item["intent_version"] + 1,
            )
        return dict(self.item)

    def claim(self, **kwargs: Any) -> Any:
        self.order.append("claim")
        assert self.item is not None
        now = kwargs["now_epoch"]
        if self.item["effect_state"] == "registered" or (
            self.item["effect_state"] == "claimed_pre_effect"
            and self.item["lease_expires_at"] < now
        ):
            self.item.update(
                effect_state="claimed_pre_effect",
                status="claimed_pre_effect",
                intent_version=self.item["intent_version"] + 1,
                lease_owner=f"lease-{self.item['intent_version'] + 1}",
                lease_expires_at=kwargs["lease_expires_at"],
            )
            return notification_repo.DeliveryIntentClaim(
                operation_id=OPERATION,
                lease_owner=self.item["lease_owner"],
                intent_version=self.item["intent_version"],
                lease_expires_at=self.item["lease_expires_at"],
                scope_digest=self.item["scope_digest"],
                payload_digest=self.item["payload_digest"],
            )
        return None

    def sendable(self, **_kwargs: Any) -> bool:
        self.order.append("check")
        return True

    def begin(self, **kwargs: Any) -> Any:
        self.order.append("begin")
        claim = kwargs["claim"]
        assert self.item is not None
        if (
            self.item["effect_state"] != "claimed_pre_effect"
            or self.item["intent_version"] != claim.intent_version
            or self.item["lease_owner"] != claim.lease_owner
        ):
            raise account_deletion_repo.AccountDeletionConflict("stale claim")
        self.item.update(
            effect_state="effect_inflight",
            status="effect_inflight",
            intent_version=self.item["intent_version"] + 1,
        )
        begun = replace(claim, intent_version=self.item["intent_version"])
        if self.fail_begin_after_commit:
            self.fail_begin_after_commit = False
            raise RuntimeError("crash after durable begin")
        return begun

    def cancel(self, **kwargs: Any) -> dict[str, Any]:
        self.order.append("cancel")
        claim = kwargs["claim"]
        assert self.item is not None
        if self.item["intent_version"] != claim.intent_version:
            raise account_deletion_repo.AccountDeletionConflict("stale claim")
        self.item.update(
            effect_state="canceled_account_deletion",
            status="canceled_account_deletion",
            outcome_status="canceled_account_deletion",
            intent_version=self.item["intent_version"] + 1,
        )
        return dict(self.item)

    def complete(self, **kwargs: Any) -> dict[str, Any]:
        self.order.append("complete")
        claim = kwargs["claim"]
        assert self.item is not None
        if (
            self.item["effect_state"] != "effect_inflight"
            or self.item["intent_version"] != claim.intent_version
            or self.item["lease_owner"] != claim.lease_owner
        ):
            raise account_deletion_repo.AccountDeletionConflict("stale claim")
        status = kwargs["status"]
        self.item.update(
            effect_state=status,
            status=status,
            outcome_status=status,
            intent_version=self.item["intent_version"] + 1,
        )
        if self.fail_complete_after_commit:
            self.fail_complete_after_commit = False
            raise RuntimeError("lost completion acknowledgement")
        return dict(self.item)

    def provider(self, *, accept_then_raise: bool = False) -> dict[str, bool]:
        self.order.append("provider")
        self.provider_calls += 1
        if accept_then_raise:
            raise TimeoutError("private provider response was lost")
        return {"accepted": True, "provider_payload": "must-not-return"}


def _run(store: _MemoryIntentStore, *, now_epoch: int, provider: Any | None = None) -> dict[str, Any]:
    return notification_service.run_delivery_intent(
        scope=_scope(),
        operation_id=OPERATION,
        channel="push",
        event_ids=["event-opaque"],
        payload=PAYLOAD,
        provider_call=provider or store.provider,
        now_epoch=now_epoch,
        lease_seconds=10,
    )


def test_crash_pre_effect_recovers_only_after_actual_time_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    original_begin = store.begin
    crashed = False

    def crash_before_begin(**kwargs: Any) -> Any:
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("crash before begin")
        return original_begin(**kwargs)

    monkeypatch.setattr(notification_repo, "begin_delivery_effect", crash_before_begin)
    with pytest.raises(RuntimeError, match="crash before begin"):
        _run(store, now_epoch=100)
    assert _run(store, now_epoch=110) == {"status": "retryable_claim_conflict"}
    assert _run(store, now_epoch=111) == {"status": "accepted"}
    assert store.provider_calls == 1


def test_crash_after_durable_transition_terminalizes_unknown_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    store.fail_begin_after_commit = True
    with pytest.raises(RuntimeError, match="crash after durable begin"):
        _run(store, now_epoch=100)
    assert store.provider_calls == 0
    assert _run(store, now_epoch=1_000) == {"status": "provider_acceptance_unknown"}
    assert store.provider_calls == 0


def test_provider_acceptance_lost_response_replays_unknown_without_blind_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    first = _run(store, now_epoch=100, provider=lambda: store.provider(accept_then_raise=True))
    second = _run(store, now_epoch=200)
    assert first == second == {"status": "provider_acceptance_unknown"}
    assert store.provider_calls == 1
    assert "private provider" not in repr(first)


def test_terminal_completion_lost_response_replays_accepted_without_provider_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    store.fail_complete_after_commit = True
    assert _run(store, now_epoch=100) == {"status": "provider_acceptance_unknown"}
    assert _run(store, now_epoch=200) == {"status": "accepted"}
    assert store.provider_calls == 1


def test_stale_claim_version_cannot_begin_complete_cancel_or_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    store.register(scope=_scope(), payload_digest=PAYLOAD_DIGEST)
    first = store.claim(now_epoch=100, lease_expires_at=110)
    second = store.claim(now_epoch=111, lease_expires_at=121)
    assert second.intent_version > first.intent_version
    for operation in (
        lambda: store.begin(claim=first),
        lambda: store.complete(claim=first, status="accepted"),
        lambda: store.cancel(claim=first),
        lambda: notification_repo.recover_delivery_intent(
            scope=_scope(),
            operation_id=OPERATION,
            payload_digest=PAYLOAD_DIGEST,
            now_epoch=122,
            expected_claim=first,
        ),
    ):
        with pytest.raises(account_deletion_repo.AccountDeletionConflict):
            operation()


def test_private_and_sealed_global_scopes_are_closed_digest_only_contracts() -> None:
    private = _scope()
    global_scope = notification_repo.DeliveryIntentScope.global_nonprivate(
        classification_seal="seal-opaque-473-37"
    )
    assert private.kind == "private_owner"
    assert global_scope.kind == "global_nonprivate"
    assert private.digest != global_scope.digest
    claim = notification_repo.DeliveryIntentClaim(
        operation_id=OPERATION,
        lease_owner="opaque-lease",
        intent_version=2,
        lease_expires_at=100,
        scope_digest=private.digest,
        payload_digest=PAYLOAD_DIGEST,
    )
    serialized = repr(claim)
    assert "private-canary" not in serialized
    assert "endpoint" not in serialized
    assert "student-delivery-owner" not in serialized


def test_provider_effect_order_is_recover_fence_transition_call_and_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _MemoryIntentStore()
    store.install(monkeypatch)
    assert _run(store, now_epoch=100) == {"status": "accepted"}
    assert store.order == [
        "register",
        "recover",
        "claim",
        "check",
        "begin",
        "provider",
        "complete",
    ]
