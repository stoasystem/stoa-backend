from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from botocore.exceptions import ClientError

from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notification_service


OWNER = "student-delivery-begin"
GENERATION = 11
OPERATION = "opaque-delivery-begin-operation"
PAYLOAD = {"title": "private payload must not escape"}
PAYLOAD_DIGEST = notification_service._canonical_payload_digest(PAYLOAD)


def _scope() -> notification_repo.DeliveryIntentScope:
    return notification_repo.DeliveryIntentScope.private_owner(
        owner_id=OWNER, generation=GENERATION
    )


def _claim() -> notification_repo.DeliveryIntentClaim:
    scope = _scope()
    return notification_repo.DeliveryIntentClaim(
        operation_id=OPERATION,
        lease_owner="opaque-delivery-lease",
        intent_version=2,
        lease_expires_at=190,
        scope_digest=scope.digest,
        payload_digest=PAYLOAD_DIGEST,
    )


def _client_error(code: str, reasons: list[Any] | None = None) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "private"},
            "CancellationReasons": reasons or [],
        },
        "TransactWriteItems",
    )


class _BeginTable:
    def __init__(self) -> None:
        claim = _claim()
        self.fence: dict[str, Any] = {
            "PK": f"USER#{OWNER}",
            "SK": "ACCOUNT_FENCE",
            "entity_type": "account_fence",
            "user_id": OWNER,
            "status": "active",
            "generation": GENERATION,
        }
        self.intent: dict[str, Any] = {
            "PK": f"NOTIFICATION_DELIVERY#{OWNER}",
            "SK": f"INTENT#{OPERATION}",
            "operation_id": OPERATION,
            "scope_kind": "private_owner",
            "scope_digest": claim.scope_digest,
            "payload_digest": claim.payload_digest,
            "owner_id": OWNER,
            "account_fence_generation": GENERATION,
            "effect_state": "claimed_pre_effect",
            "status": "claimed_pre_effect",
            "intent_version": claim.intent_version,
            "lease_owner": claim.lease_owner,
            "lease_expires_at": claim.lease_expires_at,
        }
        self.failure: BaseException | None = None

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool) -> dict[str, Any]:
        assert ConsistentRead is True
        if Key["SK"] == "ACCOUNT_FENCE":
            return {"Item": dict(self.fence)}
        return {"Item": dict(self.intent)}

    def transact_account_deletion(self, _operations: list[dict[str, Any]]) -> None:
        if self.failure is not None:
            raise self.failure
        self.intent.update(
            effect_state="effect_inflight",
            status="effect_inflight",
            intent_version=int(self.intent["intent_version"]) + 1,
        )


def _wrapped(error: ClientError) -> account_deletion_repo.AccountDeletionConflict:
    try:
        raise account_deletion_repo.AccountDeletionConflict(
            "redacted transaction failure"
        ) from error
    except account_deletion_repo.AccountDeletionConflict as exc:
        return exc


def _install_service_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    table: _BeginTable,
    cancellations: list[str],
    completions: list[str],
) -> None:
    claim = _claim()
    monkeypatch.setattr(notification_repo, "get_table", lambda: table)
    monkeypatch.setattr(
        notification_repo,
        "register_delivery_intent",
        lambda **_kwargs: {"status": "registered"},
    )
    monkeypatch.setattr(
        notification_repo,
        "recover_delivery_intent",
        lambda **_kwargs: {"status": "registered"},
    )
    monkeypatch.setattr(
        notification_repo, "claim_delivery_intent", lambda **_kwargs: claim
    )
    monkeypatch.setattr(
        notification_repo, "delivery_intent_sendable", lambda **_kwargs: True
    )

    def cancel(**_kwargs: Any) -> dict[str, str]:
        cancellations.append("cancel")
        return {"status": "canceled"}

    def complete(**kwargs: Any) -> dict[str, Any]:
        status = str(kwargs["status"])
        completions.append(status)
        return {"status": status}

    monkeypatch.setattr(
        notification_repo,
        "cancel_delivery_intent",
        cancel,
    )
    monkeypatch.setattr(
        notification_repo,
        "complete_delivery_intent",
        complete,
    )


def _run(provider_calls: list[str]) -> dict[str, Any]:
    return notification_service.run_delivery_intent(
        scope=_scope(),
        operation_id=OPERATION,
        channel="push",
        event_ids=["opaque-event"],
        payload=PAYLOAD,
        provider_call=lambda: provider_calls.append("provider"),
        now_epoch=100,
    )


def test_dependency_failure_remains_recoverable_then_healthy_retry_delivers_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _BeginTable()
    table.failure = _wrapped(_client_error("InternalServerError"))
    cancellations: list[str] = []
    completions: list[str] = []
    provider_calls: list[str] = []
    _install_service_boundary(
        monkeypatch,
        table=table,
        cancellations=cancellations,
        completions=completions,
    )

    assert _run(provider_calls) == {"status": "retryable_dependency"}
    assert table.intent["effect_state"] == "claimed_pre_effect"
    assert cancellations == []
    assert provider_calls == []

    table.failure = None
    assert _run(provider_calls) == {"status": "accepted"}
    assert provider_calls == ["provider"]
    assert completions == ["accepted"]
    assert cancellations == []


def test_ordered_fence_failure_plus_strong_deleted_fence_cancels_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _BeginTable()
    table.fence["status"] = "deletion_pending"
    table.failure = _wrapped(
        _client_error(
            "TransactionCanceledException",
            [{"Code": "ConditionalCheckFailed"}, {"Code": "None"}],
        )
    )
    cancellations: list[str] = []
    provider_calls: list[str] = []
    _install_service_boundary(
        monkeypatch,
        table=table,
        cancellations=cancellations,
        completions=[],
    )

    assert _run(provider_calls) == {"status": "canceled_account_deletion"}
    assert cancellations == ["cancel"]
    assert provider_calls == []


def test_ordered_intent_condition_loss_is_retryable_and_never_mislabeled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _BeginTable()
    table.failure = _wrapped(
        _client_error(
            "TransactionCanceledException",
            [{"Code": "None"}, {"Code": "ConditionalCheckFailed"}],
        )
    )
    cancellations: list[str] = []
    provider_calls: list[str] = []
    _install_service_boundary(
        monkeypatch,
        table=table,
        cancellations=cancellations,
        completions=[],
    )

    assert _run(provider_calls) == {"status": "retryable_claim_conflict"}
    assert cancellations == []
    assert provider_calls == []


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("private dependency timeout"),
        _wrapped(_client_error("TransactionCanceledException", [])),
        _wrapped(
            _client_error(
                "TransactionCanceledException",
                [{"Code": "ThrottlingError"}, {"Code": "None"}],
            )
        ),
    ],
)
def test_unclassified_timeout_malformed_or_throttled_failure_is_dependency_retry(
    failure: BaseException,
) -> None:
    table = _BeginTable()
    result = notification_repo.classify_delivery_transaction_failure(
        failure if isinstance(failure, Exception) else RuntimeError(),
        scope=_scope(),
        claim=_claim(),
        operation_count=2,
        fence_operation_index=0,
        intent_operation_index=1,
        table=table,
    )
    assert result.disposition is notification_repo.DeliveryBeginDisposition.DEPENDENCY_RETRY
    assert "private" not in repr(result)


def test_ambiguous_commit_is_reconciled_as_begun_from_exact_strong_intent() -> None:
    table = _BeginTable()
    table.intent.update(effect_state="effect_inflight", intent_version=3)
    result = notification_repo.classify_delivery_transaction_failure(
        TimeoutError("lost transaction response"),
        scope=_scope(),
        claim=_claim(),
        operation_count=2,
        fence_operation_index=0,
        intent_operation_index=1,
        table=table,
    )
    assert result.disposition is notification_repo.DeliveryBeginDisposition.BEGUN
    assert result.claim == replace(_claim(), intent_version=3)
