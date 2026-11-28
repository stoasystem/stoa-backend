"""The only-once ledger: who a delivery belongs to, and one durable intent per effect.

Inside the notification package only (#686). Every realtime post and push send
first resolves the event's owner from the stored row (never from what the
caller said), then crosses `run_delivery_intent`: register, claim, begin, then
the one provider call, then complete. A retried delivery of the same event to
the same target finds its intent already accepted and sends nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services.notifications._common import now_iso

_SEALED_GLOBAL_NONPRIVATE_TARGETS = frozenset({"system_status"})
_SEALED_GLOBAL_NONPRIVATE_EVENT_TYPES = frozenset(
    {"subscription_request_update", "moderation_case_update"}
)


class DeliveryOwnershipError(Exception):
    """Provider-neutral failure to establish one persisted delivery scope."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


@dataclass(frozen=True, slots=True)
class AuthoritativeDeliveryOwnership:
    kind: str
    digest: str
    owner_id: str | None = None
    generation: int | None = None
    classification_seal: str | None = None

    @classmethod
    def private_owner(
        cls, *, owner_id: str, generation: int
    ) -> AuthoritativeDeliveryOwnership:
        scope = notification_repo.DeliveryIntentScope.private_owner(
            owner_id=owner_id, generation=generation
        )
        return cls(
            kind=scope.kind,
            digest=scope.digest,
            owner_id=scope.owner_id,
            generation=scope.generation,
        )

    @classmethod
    def global_nonprivate(
        cls, *, classification_seal: str
    ) -> AuthoritativeDeliveryOwnership:
        scope = notification_repo.DeliveryIntentScope.global_nonprivate(
            classification_seal=classification_seal
        )
        return cls(
            kind=scope.kind,
            digest=scope.digest,
            classification_seal=scope.classification_seal,
        )

    def intent_scope(self) -> notification_repo.DeliveryIntentScope:
        if self.kind == "private_owner":
            return notification_repo.DeliveryIntentScope.private_owner(
                owner_id=str(self.owner_id or ""), generation=int(self.generation or 0)
            )
        return notification_repo.DeliveryIntentScope.global_nonprivate(
            classification_seal=str(self.classification_seal or "")
        )


@dataclass(frozen=True, slots=True)
class AuthoritativeDeliveryBatch:
    events: tuple[dict[str, Any], ...]
    ownership: AuthoritativeDeliveryOwnership
    event_set_digest: str


LegacyOwnerResolver = Callable[
    [Mapping[str, Any], Any], tuple[str, int | None] | None
]


def _strong_target(
    table: Any, *, pk: str, sk: str
) -> dict[str, Any] | None:
    response = table.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=True)
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(item) if isinstance(item, Mapping) else None


def _unique_owner(
    row: Mapping[str, Any], fields: tuple[str, ...]
) -> str | None:
    owners = {
        value.strip()
        for field in fields
        if isinstance((value := row.get(field)), str) and value.strip()
    }
    return next(iter(owners)) if len(owners) == 1 else None


def _owner_generation(
    row: Mapping[str, Any], *, owner_fields: tuple[str, ...]
) -> tuple[str, int | None] | None:
    owner = _unique_owner(row, owner_fields)
    if not owner:
        return None
    raw_generations = {
        value
        for field in (
            "account_fence_generation",
            "privacy_generation",
            "owner_deletion_generation",
        )
        if (value := row.get(field)) is not None
    }
    generations = {stored_int(value) for value in raw_generations}
    if any(value is None or value <= 0 for value in generations):
        return None
    if len(generations) > 1:
        return None
    return owner, next(iter(generations), None)


def _resolve_question_target(
    event: Mapping[str, Any], table: Any
) -> tuple[str, int | None] | None:
    row = _strong_target(
        table,
        pk=f"QUESTION#{event.get('target_id') or ''}",
        sk="META",
    )
    return _owner_generation(row or {}, owner_fields=("student_id", "owner_id"))


def _resolve_moderation_target(
    event: Mapping[str, Any], table: Any
) -> tuple[str, int | None] | None:
    summary = _strong_target(
        table,
        pk=f"MODERATION#{event.get('target_id') or ''}",
        sk="SUMMARY",
    )
    question_id = str((summary or {}).get("question_id") or "")
    if not question_id:
        return None
    question = _strong_target(table, pk=f"QUESTION#{question_id}", sk="META")
    resolved = _owner_generation(
        question or {}, owner_fields=("student_id", "owner_id")
    )
    declared = _owner_generation(
        summary or {}, owner_fields=("student_id", "owner_id")
    )
    if declared is not None and resolved is not None and declared != resolved:
        return None
    return resolved


def _base_row_resolver(
    *, prefix: str, sk: str, owner_fields: tuple[str, ...]
) -> LegacyOwnerResolver:
    def resolve(
        event: Mapping[str, Any], table: Any
    ) -> tuple[str, int | None] | None:
        row = _strong_target(
            table, pk=f"{prefix}{event.get('target_id') or ''}", sk=sk
        )
        return _owner_generation(row or {}, owner_fields=owner_fields)

    return resolve


LEGACY_NOTIFICATION_OWNER_RESOLVERS: dict[str, LegacyOwnerResolver] = {
    "question": _resolve_question_target,
    "moderation_case": _resolve_moderation_target,
    "report": _base_row_resolver(
        prefix="REPORT#", sk="SUMMARY", owner_fields=("student_id", "owner_id")
    ),
    "weekly_report": _base_row_resolver(
        prefix="REPORT#", sk="SUMMARY", owner_fields=("student_id", "owner_id")
    ),
    "assignment": _base_row_resolver(
        prefix="ASSIGNMENT#", sk="META", owner_fields=("student_id", "owner_id")
    ),
    "learning_profile": _base_row_resolver(
        prefix="LEARNING_PROFILE#",
        sk="META",
        owner_fields=("student_id", "owner_id"),
    ),
    "recommendation": _base_row_resolver(
        prefix="RECOMMENDATION#",
        sk="META",
        owner_fields=("student_id", "owner_id"),
    ),
    "subscription_request": _base_row_resolver(
        prefix="SUBSCRIPTION_REQUEST#",
        sk="SUMMARY",
        owner_fields=("student_id", "parent_id", "owner_id"),
    ),
}


def classify_notification_owner(
    *,
    recipient_id: str | None,
    target_type: str,
    target_id: str,
    metadata: dict[str, Any],
    owner_id: str | None,
    generation: int | None,
    global_nonprivate: bool,
) -> dict[str, Any]:
    """Return the one internal owner envelope or a sealed global classification."""
    candidate = str(
        owner_id
        or metadata.get("owner_id")
        or metadata.get("student_id")
        or recipient_id
        or ""
    ).strip()
    if candidate:
        if type(generation) is not int or generation <= 0:
            raise account_deletion_repo.AccountDeletionConflict(
                "notification fence generation is required"
            )
        return {
            "owner_id": candidate,
            "account_fence_generation": generation,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "private_owner",
        }
    if global_nonprivate and target_type in _SEALED_GLOBAL_NONPRIVATE_TARGETS and not metadata:
        return {
            "owner_id": None,
            "account_fence_generation": None,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "global_nonprivate",
        }
    raise account_deletion_repo.AccountDeletionConflict(
        "private notification owner is unresolved"
    )


def canonical_payload_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_legacy_delivery_owner(
    event: Mapping[str, Any], *, table: Any | None = None
) -> AuthoritativeDeliveryOwnership:
    """Resolve an old event only through its closed authoritative target family."""
    target = table or db_table.table()
    resolver = LEGACY_NOTIFICATION_OWNER_RESOLVERS.get(
        str(event.get("target_type") or "")
    )
    if resolver is None:
        raise DeliveryOwnershipError("delivery_owner_unresolved")
    resolved = resolver(event, target)
    if resolved is None:
        raise DeliveryOwnershipError("delivery_owner_unresolved")
    owner_id, row_generation = resolved
    try:
        fence = account_deletion_repo.require_active_account_fence(
            owner_id, row_generation, table=target
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise DeliveryOwnershipError("canceled_account_deletion") from exc
    current_generation = fence.get("generation")
    if (
        type(current_generation) is not int
        or current_generation <= 0
        or (row_generation is not None and current_generation != row_generation)
    ):
        raise DeliveryOwnershipError("delivery_owner_unresolved")
    return AuthoritativeDeliveryOwnership.private_owner(
        owner_id=owner_id, generation=current_generation
    )


def resolve_delivery_ownership(
    event: Mapping[str, Any], *, table: Any | None = None
) -> AuthoritativeDeliveryOwnership:
    """Return one closed scope derived only from the canonical persisted event."""
    classification = event.get("owner_classification")
    if classification == "private_owner":
        owner_id = event.get("owner_id")
        generation = stored_int(event.get("account_fence_generation"))
        version = stored_int(event.get("event_version"))
        if (
            not isinstance(owner_id, str)
            or not owner_id.strip()
            or generation is None
            or generation <= 0
            or version is None
            or version <= 0
        ):
            raise DeliveryOwnershipError("delivery_scope_mismatch")
        try:
            fence = account_deletion_repo.require_active_account_fence(
                owner_id.strip(), generation, table=table
            )
        except account_deletion_repo.AccountDeletionConflict as exc:
            raise DeliveryOwnershipError("canceled_account_deletion") from exc
        if fence.get("generation") != generation:
            raise DeliveryOwnershipError("delivery_scope_mismatch")
        return AuthoritativeDeliveryOwnership.private_owner(
            owner_id=owner_id.strip(), generation=generation
        )
    if classification == "global_nonprivate":
        if not notification_repo.validate_global_nonprivate_event(event):
            raise DeliveryOwnershipError("delivery_classification_invalid")
        return AuthoritativeDeliveryOwnership.global_nonprivate(
            classification_seal=str(event["classification_digest"])
        )
    if classification not in {None, ""}:
        raise DeliveryOwnershipError("delivery_classification_invalid")
    return resolve_legacy_delivery_owner(event, table=table)


def load_authoritative_delivery_events(
    event_ids: list[str], *, table: Any | None = None
) -> AuthoritativeDeliveryBatch:
    if not event_ids or len(event_ids) != len(set(event_ids)):
        raise DeliveryOwnershipError("delivery_scope_mismatch")
    events: list[dict[str, Any]] = []
    ownership: AuthoritativeDeliveryOwnership | None = None
    facts: list[dict[str, Any]] = []
    for event_id in event_ids:
        event = (
            notification_repo.load_delivery_event_strong(event_id, table=table)
            if table is not None
            else notification_repo.load_delivery_event_strong(event_id)
        )
        if event is None:
            raise DeliveryOwnershipError("delivery_owner_unresolved")
        current = resolve_delivery_ownership(event, table=table)
        if ownership is not None and current.digest != ownership.digest:
            raise DeliveryOwnershipError("delivery_scope_mismatch")
        ownership = current
        events.append(event)
        facts.append(
            {
                "event_id": event_id,
                "event_version": event.get("event_version", 0),
                "classification_digest": current.digest,
            }
        )
    if ownership is None:
        raise DeliveryOwnershipError("delivery_owner_unresolved")
    return AuthoritativeDeliveryBatch(
        events=tuple(events),
        ownership=ownership,
        event_set_digest=canonical_payload_digest(facts),
    )


def authoritative_delivery_operation_id(
    *, channel: str, batch: AuthoritativeDeliveryBatch, discriminator: str = ""
) -> str:
    identity = canonical_payload_digest(
        {
            "domain": "stoa.authoritative-delivery.v1",
            "channel": channel,
            "event_set_digest": batch.event_set_digest,
            "scope_digest": batch.ownership.digest,
            "discriminator": discriminator,
        }
    )
    return f"{channel}-{identity[:40]}"


def run_authoritative_delivery(
    *,
    channel: str,
    batch: AuthoritativeDeliveryBatch,
    payload: Any,
    provider_call: Any,
    discriminator: str = "",
) -> dict[str, Any]:
    """Run one strongly resolved channel effect through the Plan 473-37 CAS."""
    operation_id = authoritative_delivery_operation_id(
        channel=channel, batch=batch, discriminator=discriminator
    )
    result = run_delivery_intent(
        scope=batch.ownership.intent_scope(),
        operation_id=operation_id,
        channel=channel,
        event_ids=[str(event["event_id"]) for event in batch.events],
        payload=payload,
        provider_call=provider_call,
    )
    return {"delivery_id": operation_id, "status": str(result.get("status") or "")}



def run_delivery_intent(
    *,
    scope: notification_repo.DeliveryIntentScope | None = None,
    owner_id: str | None = None,
    generation: int | None = None,
    operation_id: str,
    channel: str,
    event_ids: list[str],
    payload: Any,
    provider_call: Any,
    now_epoch: int | None = None,
    lease_seconds: int = 90,
) -> dict[str, Any]:
    """Cross a durable pre-effect/inflight boundary before one provider mutation."""
    if scope is None:
        scope = notification_repo.DeliveryIntentScope.private_owner(
            owner_id=str(owner_id or ""), generation=int(generation or 0)
        )
    if not isinstance(scope, notification_repo.DeliveryIntentScope):
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery scope is required"
        )
    if type(now_epoch) is not int:
        now_epoch = int(datetime.now(timezone.utc).timestamp())
    if now_epoch < 0 or type(lease_seconds) is not int or lease_seconds <= 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery lease time is invalid"
        )
    created_at = now_iso()
    payload_digest = canonical_payload_digest(payload)
    intent = notification_repo.register_delivery_intent(
        scope=scope,
        operation_id=operation_id,
        channel=channel,
        event_ids=list(event_ids),
        payload_digest=payload_digest,
        now_iso=created_at,
    )
    prior_status = str(intent.get("outcome_status") or intent.get("status") or "")
    if prior_status in {
        "accepted",
        "provider_acceptance_unknown",
        "canceled_account_deletion",
    }:
        return {"status": prior_status}
    try:
        recovered = notification_repo.recover_delivery_intent(
            scope=scope,
            operation_id=operation_id,
            payload_digest=payload_digest,
            now_epoch=now_epoch,
            now_iso=now_iso(),
        )
    except account_deletion_repo.AccountDeletionConflict:
        return {"status": "retryable_claim_conflict"}
    recovered_status = str(
        recovered.get("outcome_status") or recovered.get("status") or ""
    )
    if recovered_status in {
        "accepted",
        "provider_acceptance_unknown",
        "canceled_account_deletion",
    }:
        return {"status": recovered_status}
    claimed = notification_repo.claim_delivery_intent(
        scope=scope,
        operation_id=operation_id,
        payload_digest=payload_digest,
        now_epoch=now_epoch,
        lease_expires_at=now_epoch + lease_seconds,
        now_iso=now_iso(),
    )
    if not claimed:
        return {"status": "retryable_claim_conflict"}
    try:
        sendable = notification_repo.delivery_intent_sendable(
            scope=scope, claim=claimed
        )
    except Exception:
        return {"status": "retryable_dependency"}
    if not sendable:
        return {"status": "retryable_claim_conflict"}
    begin_result = notification_repo.begin_delivery_effect(
        scope=scope,
        claim=claimed,
        now_iso=now_iso(),
    )
    # Preserve compatibility with injected Plan 473 fakes while the repository
    # contract itself always returns DeliveryBeginResult.
    if isinstance(begin_result, notification_repo.DeliveryIntentClaim):
        begin_result = notification_repo.DeliveryBeginResult(
            notification_repo.DeliveryBeginDisposition.BEGUN, begin_result
        )
    if (
        begin_result.disposition
        is notification_repo.DeliveryBeginDisposition.PROVEN_ACCOUNT_DELETED
    ):
        try:
            notification_repo.cancel_delivery_intent(
                scope=scope, claim=claimed, now_iso=now_iso()
            )
        except account_deletion_repo.AccountDeletionConflict:
            return {"status": "retryable_claim_conflict"}
        return {"status": "canceled_account_deletion"}
    if (
        begin_result.disposition
        is notification_repo.DeliveryBeginDisposition.CLAIM_LOST
    ):
        return {"status": "retryable_claim_conflict"}
    if (
        begin_result.disposition
        is notification_repo.DeliveryBeginDisposition.DEPENDENCY_RETRY
    ):
        return {"status": "retryable_dependency"}
    inflight_claim = begin_result.claim
    if inflight_claim is None:
        return {"status": "retryable_dependency"}
    # No call may be inserted between this durable begin and the provider.
    try:
        provider_call()
    except Exception:
        try:
            notification_repo.complete_delivery_intent(
                scope=scope,
                claim=inflight_claim,
                status="provider_acceptance_unknown",
                now_iso=now_iso(),
            )
        except Exception:
            pass
        return {"status": "provider_acceptance_unknown"}
    try:
        notification_repo.complete_delivery_intent(
            scope=scope,
            claim=inflight_claim,
            status="accepted",
            now_iso=now_iso(),
        )
    except Exception:
        return {"status": "provider_acceptance_unknown"}
    return {"status": "accepted"}

