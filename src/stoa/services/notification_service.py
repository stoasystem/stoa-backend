"""In-product notification event helpers."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib import request
from uuid import uuid4

import boto3
from fastapi import HTTPException

from stoa.config import settings
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import websocket_service
from stoa.security.identity import Actor


EVENT_TYPES = {
    "teacher_requested",
    "teacher_takeover",
    "teacher_reply",
    "moderation_case_update",
    "subscription_request_update",
    "learning_profile_update",
    "assignment_update",
    "weekly_report_update",
}
STATUSES = {"created", "read", "archived", "failed"}
PREFERENCE_CATEGORIES = {
    "learning_updates",
    "teacher_responses",
    "assignments",
    "weekly_reports",
    "admin_operations",
}
PREFERENCE_CHANNELS = {"in_app", "realtime", "email_digest", "push"}
PUSH_TOKEN_STATUSES = {"active", "revoked"}
PUSH_TOKEN_PLATFORMS = {"ios", "android", "web"}
EVENT_CATEGORY_BY_TYPE = {
    "teacher_requested": "teacher_responses",
    "teacher_takeover": "teacher_responses",
    "teacher_reply": "teacher_responses",
    "moderation_case_update": "admin_operations",
    "subscription_request_update": "admin_operations",
    "learning_profile_update": "learning_updates",
    "assignment_update": "assignments",
    "weekly_report_update": "weekly_reports",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    if any(type(value) is not int or value <= 0 for value in raw_generations):
        return None
    if len(raw_generations) > 1:
        return None
    return owner, next(iter(raw_generations), None)


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


def _canonical_payload_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_legacy_delivery_owner(
    event: Mapping[str, Any], *, table: Any | None = None
) -> AuthoritativeDeliveryOwnership:
    """Resolve an old event only through its closed authoritative target family."""
    target = table or notification_repo.get_table()
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
        generation = event.get("account_fence_generation")
        version = event.get("event_version")
        if (
            not isinstance(owner_id, str)
            or not owner_id.strip()
            or type(generation) is not int
            or generation <= 0
            or type(version) is not int
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
        event_set_digest=_canonical_payload_digest(facts),
    )


def authoritative_delivery_operation_id(
    *, channel: str, batch: AuthoritativeDeliveryBatch, discriminator: str = ""
) -> str:
    identity = _canonical_payload_digest(
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
    payload_digest = _canonical_payload_digest(payload)
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
    if not notification_repo.delivery_intent_sendable(scope=scope, claim=claimed):
        try:
            notification_repo.cancel_delivery_intent(
                scope=scope, claim=claimed, now_iso=now_iso()
            )
        except account_deletion_repo.AccountDeletionConflict:
            return {"status": "retryable_claim_conflict"}
        return {"status": "canceled_account_deletion"}
    try:
        inflight_claim = notification_repo.begin_delivery_effect(
            scope=scope,
            claim=claimed,
            now_iso=now_iso(),
        )
    except account_deletion_repo.AccountDeletionConflict:
        try:
            notification_repo.cancel_delivery_intent(
                scope=scope, claim=claimed, now_iso=now_iso()
            )
        except account_deletion_repo.AccountDeletionConflict:
            return {"status": "retryable_claim_conflict"}
        return {"status": "canceled_account_deletion"}
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


def create_event(
    *,
    recipient_id: str | None,
    recipient_role: str,
    event_type: str,
    target_type: str,
    target_id: str,
    title: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    actor_id: str | None = None,
    actor_role: str | None = None,
    status: str = "created",
    created_at: str | None = None,
    owner_id: str | None = None,
    account_fence_generation: int | None = None,
    global_nonprivate: bool = False,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported notification event type")
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    if not recipient_role:
        raise HTTPException(status_code=400, detail="Notification recipient role is required")

    raw_metadata = dict(metadata or {})
    inferred_owner = str(
        owner_id
        or raw_metadata.get("owner_id")
        or raw_metadata.get("student_id")
        or recipient_id
        or ""
    ).strip()
    raw_generation = (
        account_fence_generation
        if account_fence_generation is not None
        else raw_metadata.get("privacy_generation")
        or raw_metadata.get("account_fence_generation")
    )
    generation = raw_generation if type(raw_generation) is int and raw_generation > 0 else None
    if inferred_owner and generation is not None:
        ownership = classify_notification_owner(
            recipient_id=recipient_id,
            target_type=target_type,
            target_id=target_id,
            metadata=raw_metadata,
            owner_id=inferred_owner,
            generation=generation,
            global_nonprivate=False,
        )
    elif inferred_owner:
        # The repository resolves the current generation on the real atomic
        # table.  This compatibility path exists for older unit fakes only.
        ownership = {
            "owner_id": inferred_owner,
            "account_fence_generation": None,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "private_owner",
        }
    elif global_nonprivate:
        ownership = {
            "owner_id": None,
            "account_fence_generation": None,
            "target_type": target_type,
            "target_id": target_id,
            "classification": "global_nonprivate",
        }
    else:
        raise HTTPException(status_code=409, detail="Notification owner is required")

    category = category_for_event(event_type=event_type, target_type=target_type)
    preferences = get_preferences_for_user(recipient_id) if recipient_id else default_preferences()
    delivery = delivery_decision(
        category=category,
        preferences=preferences,
        realtime_configured=bool(settings.websocket_api_endpoint),
    )
    event_status = status
    if not delivery["channels"]["in_app"]["enabled"] and status == "created":
        event_status = "archived"

    item = {
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "event_id": f"notif-{uuid4().hex}",
        "recipient_id": recipient_id,
        "recipient_role": recipient_role,
        "event_type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "title": _clean_text(title, limit=140),
        "summary": _clean_text(summary, limit=500),
        "status": event_status,
        "created_at": created_at or now_iso(),
        "read_at": now_iso() if event_status == "archived" else None,
        "archived_at": now_iso() if event_status == "archived" else None,
        "metadata": (
            {}
            if ownership["classification"] == "global_nonprivate"
            else {
                **_clean_metadata(raw_metadata),
                "delivery_decision": delivery,
            }
        ),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "category": category,
        "owner_id": ownership["owner_id"],
        "account_fence_generation": ownership["account_fence_generation"],
        "owner_classification": ownership["classification"],
    }
    if ownership["classification"] == "private_owner":
        item.update(
            owner_target_type=ownership["target_type"],
            owner_target_id=ownership["target_id"],
        )
    persisted = notification_repo.put_event(item)
    if isinstance(persisted, dict):
        item = persisted
    if delivery["channels"]["realtime"]["decision"] == "attempted":
        websocket_service.fanout_notification_event_safe(item)
    if delivery["channels"]["push"]["decision"] == "deferred_push":
        attempt_push_delivery_safe(item)
    return event_response(item)


def create_event_safe(**kwargs: Any) -> dict[str, Any] | None:
    if _best_effort_disabled():
        return None
    try:
        return create_event(**kwargs)
    except Exception:
        return None


def emit_teacher_requested(
    *, question_id: str, student_id: str, subject: str, account_fence_generation: int | None = None
) -> None:
    for recipient_role in ("teacher", "admin"):
        create_event_safe(
            recipient_id=None,
            recipient_role=recipient_role,
            event_type="teacher_requested",
            target_type="question",
            target_id=question_id,
            title="Teacher help requested",
            summary=f"A student requested help for a {subject} question.",
            metadata={"student_id": student_id, "subject": subject},
            actor_id=student_id,
            actor_role="student",
            owner_id=student_id,
            account_fence_generation=account_fence_generation,
        )


def emit_teacher_takeover(*, question: dict[str, Any], teacher_id: str) -> None:
    create_event_safe(
        recipient_id=str(question.get("student_id") or ""),
        recipient_role="student",
        event_type="teacher_takeover",
        target_type="question",
        target_id=str(question.get("question_id") or ""),
        title="Teacher joined your question",
        summary="A teacher has started working on your question.",
        metadata={"subject": question.get("subject"), "teacher_id": teacher_id},
        actor_id=teacher_id,
        actor_role="teacher",
        owner_id=str(question.get("student_id") or ""),
        account_fence_generation=question.get("account_fence_generation"),
    )


def emit_teacher_reply(*, question: dict[str, Any], teacher_id: str) -> None:
    create_event_safe(
        recipient_id=str(question.get("student_id") or ""),
        recipient_role="student",
        event_type="teacher_reply",
        target_type="question",
        target_id=str(question.get("question_id") or ""),
        title="Teacher replied",
        summary="Your teacher added a reply to your question.",
        metadata={"subject": question.get("subject"), "teacher_id": teacher_id},
        actor_id=teacher_id,
        actor_role="teacher",
        owner_id=str(question.get("student_id") or ""),
        account_fence_generation=question.get("account_fence_generation"),
    )


def emit_moderation_update(
    *,
    case_item: dict[str, Any],
    actor_id: str,
    actor_role: str,
    owner_id: str,
    privacy_generation: int,
) -> None:
    _require_moderation_owner(owner_id, privacy_generation)
    if case_item.get("reporter_id") and case_item.get("reporter_role") != "admin":
        create_event_safe(
            recipient_id=str(case_item["reporter_id"]),
            recipient_role=str(case_item.get("reporter_role") or "student"),
            event_type="moderation_case_update",
            target_type="moderation_case",
            target_id=str(case_item.get("case_id") or ""),
            title="Moderation case updated",
            summary=f"Moderation case status is {case_item.get('status', 'updated')}.",
            metadata={
                "question_id": case_item.get("question_id"),
                "status": case_item.get("status"),
                "owner_id": owner_id,
                "privacy_generation": privacy_generation,
            },
            actor_id=actor_id,
            actor_role=actor_role,
            owner_id=owner_id,
            account_fence_generation=privacy_generation,
        )


def emit_moderation_created(
    *,
    case_item: dict[str, Any],
    actor_id: str,
    actor_role: str,
    owner_id: str,
    privacy_generation: int,
) -> None:
    _require_moderation_owner(owner_id, privacy_generation)
    create_event_safe(
        recipient_id=None,
        recipient_role="admin",
        event_type="moderation_case_update",
        target_type="moderation_case",
        target_id=str(case_item.get("case_id") or ""),
        title="New moderation case",
        summary=f"{case_item.get('severity', 'medium')} moderation case reported.",
        metadata={
            "question_id": case_item.get("question_id"),
            "reason": case_item.get("reason"),
            "owner_id": owner_id,
            "privacy_generation": privacy_generation,
        },
        actor_id=actor_id,
        actor_role=actor_role,
        owner_id=owner_id,
        account_fence_generation=privacy_generation,
    )


def _require_moderation_owner(owner_id: str, privacy_generation: int) -> None:
    if (
        not isinstance(owner_id, str)
        or not owner_id.strip()
        or isinstance(privacy_generation, bool)
        or not isinstance(privacy_generation, int)
        or privacy_generation <= 0
    ):
        raise HTTPException(
            status_code=409, detail="Moderation notification owner is required"
        )


def emit_subscription_update(
    *,
    request_item: dict[str, Any],
    recipient_id: str | None,
    recipient_role: str,
    actor_id: str,
    actor_role: str,
) -> None:
    owner_id = str(
        request_item.get("student_id")
        or request_item.get("parent_id")
        or recipient_id
        or ""
    )
    create_event_safe(
        recipient_id=recipient_id,
        recipient_role=recipient_role,
        event_type="subscription_request_update",
        target_type="subscription_request",
        target_id=str(request_item.get("request_id") or ""),
        title="Subscription request updated",
        summary=f"Subscription request status is {request_item.get('status', 'updated')}.",
        metadata={
            "requested_tier": request_item.get("requested_tier"),
            "request_type": request_item.get("request_type"),
            "status": request_item.get("status"),
        },
        actor_id=actor_id,
        actor_role=actor_role,
        owner_id=owner_id,
        account_fence_generation=request_item.get("account_fence_generation"),
    )


def list_user_events(
    user: dict[str, Any] | Actor,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    user_id = _user_id(user)
    role = _user_role(user)
    items = [
        item for item in notification_repo.list_events(limit=max(limit, 100))
        if _visible_to_user(item, user_id=user_id, role=role)
        and (status is None and item.get("status") != "archived" or status == item.get("status"))
    ]
    return [event_response(item) for item in _sort_events(items)[:limit]]


def list_admin_events(
    *,
    status: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    if event_type is not None and event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported notification event type")
    items = [
        item for item in notification_repo.list_events(limit=max(limit, 100))
        if (status is None or item.get("status") == status)
        and (event_type is None or item.get("event_type") == event_type)
    ]
    return [event_response(item) for item in _sort_events(items)[:limit]]


def default_preferences() -> dict[str, Any]:
    return {
        category: {
            "in_app": True,
            "realtime": True,
            "email_digest": False,
            "push": False,
        }
        for category in sorted(PREFERENCE_CATEGORIES)
    }


def get_preferences_for_user(user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return default_preferences()
    stored = notification_repo.get_preferences(user_id) or {}
    return _merged_preferences(stored.get("preferences"))


def preferences_response(user_id: str) -> dict[str, Any]:
    stored = notification_repo.get_preferences(user_id) or {}
    return {
        "userId": user_id,
        "preferences": _merged_preferences(stored.get("preferences")),
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": stored.get("updated_at"),
    }


def update_preferences(user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
    merged = _merged_preferences(None)
    for category, channel_updates in preferences.items():
        if category not in PREFERENCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="Unsupported notification preference category")
        if not isinstance(channel_updates, dict):
            raise HTTPException(status_code=400, detail="Notification preference channels must be an object")
        for channel, enabled in channel_updates.items():
            if channel not in PREFERENCE_CHANNELS:
                raise HTTPException(status_code=400, detail="Unsupported notification preference channel")
            if not isinstance(enabled, bool):
                raise HTTPException(status_code=400, detail="Notification preference value must be boolean")
            merged[category][channel] = enabled

    updated_at = now_iso()
    notification_repo.put_preferences(
        {
            "entity_type": notification_repo.PREFERENCE_ENTITY,
            "user_id": user_id,
            "owner_id": user_id,
            "preferences": merged,
            "updated_at": updated_at,
        }
    )
    return {
        "userId": user_id,
        "preferences": merged,
        "supportedCategories": sorted(PREFERENCE_CATEGORIES),
        "supportedChannels": sorted(PREFERENCE_CHANNELS),
        "updatedAt": updated_at,
    }


def category_for_event(*, event_type: str, target_type: str) -> str:
    if event_type in EVENT_CATEGORY_BY_TYPE:
        return EVENT_CATEGORY_BY_TYPE[event_type]
    if target_type in {"assignment", "recommendation"}:
        return "assignments"
    if target_type in {"weekly_report", "report"}:
        return "weekly_reports"
    return "learning_updates"


def delivery_decision(
    *,
    category: str,
    preferences: dict[str, Any],
    realtime_configured: bool,
) -> dict[str, Any]:
    category_prefs = _merged_preferences(preferences).get(category, default_preferences()[category])
    return {
        "category": category,
        "channels": {
            "in_app": {
                "enabled": bool(category_prefs["in_app"]),
                "decision": "stored" if category_prefs["in_app"] else "skipped_preference",
            },
            "realtime": {
                "enabled": bool(category_prefs["realtime"]),
                "decision": (
                    "attempted"
                    if category_prefs["realtime"]
                    else "skipped_preference"
                ),
                "configured": realtime_configured,
            },
            "email_digest": {
                "enabled": bool(category_prefs["email_digest"]),
                "decision": "deferred_digest" if category_prefs["email_digest"] else "skipped_preference",
            },
            "push": {
                "enabled": bool(category_prefs["push"]),
                "decision": "deferred_push" if category_prefs["push"] else "skipped_preference",
            },
        },
    }


def delivery_status(*, limit: int = 100) -> dict[str, Any]:
    items = list_admin_events(limit=limit)
    category_counts: dict[str, int] = {}
    realtime_counts: dict[str, int] = {}
    delivery_attempt_counts: dict[str, int] = {}
    recent_delivery_attempts: list[dict[str, Any]] = []
    for item in items:
        category = str(item.get("deliveryCategory") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        realtime = item.get("deliveryChannels", {}).get("realtime", {})
        decision = str(realtime.get("decision") or "unknown")
        realtime_counts[decision] = realtime_counts.get(decision, 0) + 1
        for attempt in _websocket_delivery_attempts(item):
            result_counts = _delivery_attempt_result_counts(attempt)
            for status, count in result_counts.items():
                delivery_attempt_counts[status] = delivery_attempt_counts.get(status, 0) + count
            recent_delivery_attempts.append(
                {
                    "eventId": item.get("eventId"),
                    "deliveryId": attempt.get("delivery_id"),
                    "attemptedAt": attempt.get("attempted_at"),
                    "targetChannels": attempt.get("target_channels") or [],
                    "targetCount": _safe_int(attempt.get("target_count")),
                    "resultCounts": result_counts,
                }
            )
    websocket_readiness = websocket_service.readiness_status()
    return {
        "websocketConfigured": bool(settings.websocket_api_endpoint),
        "websocketMode": websocket_readiness["mode"],
        "websocketReadiness": websocket_readiness,
        "emailProvider": email_provider_readiness(),
        "pushProvider": push_provider_readiness(),
        "preferenceCategories": sorted(PREFERENCE_CATEGORIES),
        "preferenceChannels": sorted(PREFERENCE_CHANNELS),
        "recentEventCount": len(items),
        "categoryCounts": category_counts,
        "realtimeDecisionCounts": realtime_counts,
        "deliveryAttemptCounts": delivery_attempt_counts,
        "recentDeliveryAttempts": recent_delivery_attempts[-10:],
    }


def digest_preview(
    user: dict[str, Any] | Actor,
    *,
    category: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    if category is not None and category not in PREFERENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Unsupported notification preference category")
    user_id = _user_id(user)
    role = _user_role(user)
    preferences = get_preferences_for_user(user_id)
    items = []
    for item in _sort_events(notification_repo.list_events(limit=max(limit, 100))):
        if not _visible_to_user(item, user_id=user_id, role=role):
            continue
        if item.get("status") != "created":
            continue
        item_category = item.get("category") or category_for_event(
            event_type=str(item.get("event_type") or ""),
            target_type=str(item.get("target_type") or ""),
        )
        if category and item_category != category:
            continue
        created_at = str(item.get("created_at") or "")
        if since and created_at < since:
            continue
        if until and created_at > until:
            continue
        category_prefs = _merged_preferences(preferences)[item_category]
        if not category_prefs["email_digest"]:
            continue
        items.append(digest_item(item, category=item_category))
        if len(items) >= limit:
            break
    return {
        "userId": user_id,
        "category": category,
        "window": {"since": since, "until": until},
        "count": len(items),
        "items": items,
        "deliveryMode": "preview_only",
        "emailProviderConfigured": email_provider_readiness()["configured"],
        "pushProviderConfigured": push_provider_readiness()["configured"],
        "pushPreferencesSupported": True,
    }


def send_digest(
    user: dict[str, Any] | Actor,
    *,
    category: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 25,
    send_func: Any | None = None,
) -> dict[str, Any]:
    preview = digest_preview(user, category=category, since=since, until=until, limit=limit)
    readiness = email_provider_readiness()
    delivery_id = f"email-{uuid4().hex}"
    event_ids = [str(item["eventId"]) for item in preview["items"]]
    recipient_email = _safe_text(_user_value(user, "email"))
    attempt = {
        "delivery_id": delivery_id,
        "attempted_at": now_iso(),
        "channel": "email_digest",
        "provider": readiness["provider"],
        "provider_mode": readiness["mode"],
        "template": settings.notification_email_digest_template,
        "event_ids": event_ids,
        "item_count": len(event_ids),
        "recipient_email_hash": _hash_value(recipient_email) if recipient_email else None,
        "status": "pending",
        "provider_result": {},
    }

    if not event_ids:
        attempt["status"] = "refused_no_digest_items"
    elif not recipient_email:
        attempt["status"] = "refused_missing_recipient_email"
    elif readiness["mode"] == "disabled" or readiness["blockers"]:
        attempt["status"] = "refused_provider_not_ready"
    elif not settings.notification_email_send_enabled and send_func is None:
        attempt["status"] = "refused_provider_send_disabled"
    else:
        try:
            batch = load_authoritative_delivery_events(event_ids)
            if (
                batch.ownership.kind == "private_owner"
                and batch.ownership.owner_id != _user_id(user)
            ):
                raise DeliveryOwnershipError("delivery_scope_mismatch")
        except DeliveryOwnershipError as exc:
            attempt["status"] = exc.status
        else:
            canonical_items = [
                digest_item(
                    event,
                    category=str(
                        event.get("category")
                        or category_for_event(
                            event_type=str(event.get("event_type") or ""),
                            target_type=str(event.get("target_type") or ""),
                        )
                    ),
                )
                for event in batch.events
            ]
            discriminator = _canonical_payload_digest(
                {
                    "recipient_email_hash": attempt["recipient_email_hash"],
                    "template": settings.notification_email_digest_template,
                }
            )
            delivery_id = authoritative_delivery_operation_id(
                channel="email_digest",
                batch=batch,
                discriminator=discriminator,
            )
            attempt["delivery_id"] = delivery_id
            payload = {
                "deliveryId": delivery_id,
                "recipientEmail": recipient_email,
                "subject": "STOA notification digest",
                "html": _digest_email_html(canonical_items),
                "items": canonical_items,
                "template": settings.notification_email_digest_template,
            }
            result = run_authoritative_delivery(
                channel="email_digest",
                batch=batch,
                payload=payload,
                discriminator=discriminator,
                provider_call=lambda: (
                    send_func(payload)
                    if send_func is not None
                    else _send_email_digest_provider(payload)
                ),
            )
            attempt["status"] = {
                "accepted": "sent",
                "provider_acceptance_unknown": "provider_acceptance_unknown",
                "canceled_account_deletion": "canceled_account_deletion",
            }.get(str(result.get("status") or ""), "retryable")

    _record_event_attempts(event_ids, "email_digest_delivery_attempts", attempt)
    return {
        "deliveryId": delivery_id,
        "status": attempt["status"],
        "providerMode": readiness["mode"],
        "template": attempt["template"],
        "itemCount": len(event_ids),
        "eventIds": event_ids,
        "recipient": {"emailHash": attempt["recipient_email_hash"]},
        "providerResult": attempt["provider_result"],
    }


def register_push_token(
    user: dict[str, Any] | Actor,
    *,
    platform: str,
    token: str | None = None,
    provider_token_reference: str | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    normalized_platform = _safe_text(platform).lower()
    if normalized_platform not in PUSH_TOKEN_PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported push token platform")
    clean_token = _safe_text(token)
    clean_provider_reference = _safe_text(provider_token_reference)
    if not clean_token and not clean_provider_reference:
        raise HTTPException(status_code=400, detail="Push token or provider reference is required")
    user_id = _user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user is required")

    token_hash = _hash_value(clean_token or clean_provider_reference)
    token_reference = f"push-{token_hash[:16]}"
    # A provider/body alias is itself an ownership coordinate.  Resolve any
    # existing canonical token before the put so one actor cannot adopt or
    # rotate another actor's device reference.
    for existing in notification_repo.list_push_tokens(limit=100):
        same_material = (
            existing.get("token_hash") == token_hash
            or (
                clean_provider_reference
                and existing.get("provider_token_reference") == clean_provider_reference
            )
        )
        if same_material and existing.get("user_id") != user_id:
            from stoa.security.errors import SecurityDecisionError, SecurityErrorCode

            error = SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
            raise HTTPException(error.status_code, detail=error.public_body()) from error
    now = now_iso()
    item = {
        "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
        "user_id": user_id,
        "role": _user_role(user),
        "platform": normalized_platform,
        "token_reference": token_reference,
        "token_hash": token_hash,
        "provider_token_reference": clean_provider_reference or None,
        "device_id_hash": _hash_value(device_id) if _safe_text(device_id) else None,
        "status": "active",
        "created_at": now,
        "last_seen_at": now,
        "revoked_at": None,
        "owner_id": user_id,
    }
    persisted = notification_repo.put_push_token(item)
    if isinstance(persisted, dict):
        item = persisted
    return push_token_response(item)


def revoke_push_token(user: dict[str, Any], token_reference: str) -> dict[str, Any]:
    user_id = str(user.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user is required")
    updated = notification_repo.update_push_token(
        user_id,
        token_reference,
        {"status": "revoked", "revoked_at": now_iso()},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Push token not found")
    return push_token_response(updated)


def revoke_authorized_push_token(item: dict[str, Any]) -> dict[str, Any]:
    updated = notification_repo.update_push_token(
        str(item.get("user_id") or ""),
        str(item.get("token_reference") or ""),
        {"status": "revoked", "revoked_at": now_iso()},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Push token not found")
    return push_token_response(updated)


def attempt_push_delivery_safe(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return attempt_push_delivery(item)
    except Exception:
        return None


def attempt_push_delivery(
    item: dict[str, Any],
    *,
    send_func: Any | None = None,
) -> dict[str, Any]:
    readiness = push_provider_readiness()
    delivery_id = f"push-{uuid4().hex}"
    event_id = str(item.get("event_id") or "")
    batch: AuthoritativeDeliveryBatch | None = None
    ownership_error: DeliveryOwnershipError | None = None
    try:
        batch = load_authoritative_delivery_events([event_id])
    except DeliveryOwnershipError as exc:
        ownership_error = exc
    canonical = batch.events[0] if batch is not None else {}
    recipient_id = str(canonical.get("recipient_id") or "")
    tokens = (
        notification_repo.list_push_tokens(recipient_id, status="active")
        if batch is not None and recipient_id
        else []
    )
    token_refs = [
        str(token.get("provider_token_reference") or token.get("token_reference") or "")
        for token in tokens
        if str(token.get("provider_token_reference") or token.get("token_reference") or "").strip()
    ]
    attempt = {
        "delivery_id": delivery_id,
        "attempted_at": now_iso(),
        "channel": "push",
        "provider": readiness["provider"],
        "provider_mode": readiness["mode"],
        "template": settings.notification_push_template,
        "token_count": len(token_refs),
        "token_references": [_redacted_reference(token_ref) for token_ref in token_refs],
        "status": "pending",
        "provider_result": {},
    }

    if ownership_error is not None:
        attempt["status"] = ownership_error.status
    elif not recipient_id:
        attempt["status"] = "refused_missing_recipient_id"
    elif not token_refs:
        attempt["status"] = "refused_missing_token"
    elif readiness["mode"] == "disabled" or readiness["blockers"]:
        attempt["status"] = "refused_provider_not_ready"
    elif not settings.notification_push_send_enabled and send_func is None:
        attempt["status"] = "refused_provider_send_disabled"
    else:
        assert batch is not None
        discriminator = _canonical_payload_digest(
            {
                "token_references": token_refs,
                "template": settings.notification_push_template,
            }
        )
        delivery_id = authoritative_delivery_operation_id(
            channel="push", batch=batch, discriminator=discriminator
        )
        attempt["delivery_id"] = delivery_id
        payload = {
            "deliveryId": delivery_id,
            "tokenReferences": token_refs,
            "title": canonical.get("title"),
            "body": canonical.get("summary"),
            "data": {
                "eventId": canonical.get("event_id"),
                "eventType": canonical.get("event_type"),
                "targetType": canonical.get("target_type"),
                "targetId": canonical.get("target_id"),
            },
            "template": settings.notification_push_template,
        }
        result = run_authoritative_delivery(
            channel="push",
            batch=batch,
            payload=payload,
            discriminator=discriminator,
            provider_call=lambda: (
                send_func(payload)
                if send_func is not None
                else _send_push_provider(payload)
            ),
        )
        attempt["status"] = {
            "accepted": "sent",
            "provider_acceptance_unknown": "provider_acceptance_unknown",
            "canceled_account_deletion": "canceled_account_deletion",
        }.get(str(result.get("status") or ""), "retryable")

    _record_event_attempts([event_id], "push_delivery_attempts", attempt)
    return {
        "deliveryId": delivery_id,
        "status": attempt["status"],
        "providerMode": readiness["mode"],
        "tokenCount": len(token_refs),
        "providerResult": attempt["provider_result"],
    }


def email_provider_readiness() -> dict[str, Any]:
    provider = _safe_text(settings.notification_email_provider)
    sender = _safe_text(settings.notification_email_sender)
    template = _safe_text(settings.notification_email_digest_template)
    blockers = []
    if not provider:
        blockers.append("missing_notification_email_provider")
    if provider and not settings.notification_email_provider_approved:
        blockers.append("notification_email_provider_not_approved")
    if provider and not sender:
        blockers.append("missing_notification_email_sender")
    if provider and not template:
        blockers.append("missing_notification_email_digest_template")
    mode = "disabled"
    if provider:
        mode = "provider_ready" if not blockers and settings.notification_email_send_enabled else "configured"
    return {
        "provider": provider or "disabled",
        "mode": mode,
        "configured": bool(provider and not blockers),
        "approved": bool(settings.notification_email_provider_approved),
        "sendEnabled": bool(settings.notification_email_send_enabled),
        "senderConfigured": bool(sender),
        "template": template,
        "blockers": blockers,
    }


def push_provider_readiness() -> dict[str, Any]:
    provider = _safe_text(settings.notification_push_provider)
    template = _safe_text(settings.notification_push_template)
    api_key = _safe_text(settings.notification_push_provider_api_key)
    endpoint = _safe_text(settings.notification_push_provider_endpoint_url)
    blockers = []
    if not provider:
        blockers.append("missing_notification_push_provider")
    if provider and not settings.notification_push_provider_approved:
        blockers.append("notification_push_provider_not_approved")
    if provider and not template:
        blockers.append("missing_notification_push_template")
    if provider and settings.notification_push_send_enabled and not endpoint:
        blockers.append("missing_notification_push_provider_endpoint_url")
    mode = "disabled"
    if provider:
        mode = "provider_ready" if not blockers and settings.notification_push_send_enabled else "configured"
    return {
        "provider": provider or "disabled",
        "mode": mode,
        "configured": bool(provider and not blockers),
        "approved": bool(settings.notification_push_provider_approved),
        "sendEnabled": bool(settings.notification_push_send_enabled),
        "credentials": "configured" if api_key else "missing",
        "endpointConfigured": bool(endpoint),
        "template": template,
        "blockers": blockers,
    }


def _websocket_delivery_attempts(item: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = item.get("metadata") or {}
    attempts = metadata.get("websocket_delivery_attempts") or []
    return [attempt for attempt in attempts if isinstance(attempt, dict)]


def _delivery_attempt_result_counts(attempt: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in attempt.get("results") or []:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def digest_item(item: dict[str, Any], *, category: str) -> dict[str, Any]:
    return {
        "eventId": item.get("event_id"),
        "eventType": item.get("event_type"),
        "category": category,
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "createdAt": item.get("created_at"),
        "metadata": _digest_safe_metadata(item.get("metadata") or {}),
    }


def mark_event(event_id: str, user: dict[str, Any], next_status: str) -> dict[str, Any]:
    if next_status not in {"read", "archived"}:
        raise HTTPException(status_code=400, detail="Unsupported notification transition")
    item = notification_repo.get_event(event_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not _visible_to_user(item, user_id=str(user.get("sub") or ""), role=str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="Notification is not visible to this user")

    now = now_iso()
    updates: dict[str, Any] = {"status": next_status}
    if next_status == "read":
        updates["read_at"] = item.get("read_at") or now
    if next_status == "archived":
        updates["archived_at"] = item.get("archived_at") or now
        updates["read_at"] = item.get("read_at") or now
    updated = notification_repo.update_event(event_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return event_response(updated)


def mark_authorized_event(item: dict[str, Any], next_status: str) -> dict[str, Any]:
    if next_status not in {"read", "archived"}:
        raise HTTPException(status_code=400, detail="Unsupported notification transition")
    event_id = str(item.get("event_id") or "")
    now = now_iso()
    updates: dict[str, Any] = {"status": next_status}
    if next_status == "read":
        updates["read_at"] = item.get("read_at") or now
    else:
        updates["archived_at"] = item.get("archived_at") or now
        updates["read_at"] = item.get("read_at") or now
    updated = notification_repo.update_event(event_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return event_response(updated)


def _user_value(user: dict[str, Any] | Actor, key: str) -> Any:
    if isinstance(user, Actor):
        if key == "sub":
            return user.user_id
        if key == "role":
            return user.role.value
        return dict(user.auth_context).get(key)
    return user.get(key)


def _user_id(user: dict[str, Any] | Actor) -> str:
    return str(user.user_id if isinstance(user, Actor) else user.get("sub") or user.get("user_id") or "")


def _user_role(user: dict[str, Any] | Actor) -> str:
    return user.role.value if isinstance(user, Actor) else str(user.get("role") or "")


def event_response(item: dict[str, Any]) -> dict[str, Any]:
    delivery = (item.get("metadata") or {}).get("delivery_decision") or {}
    return {
        "eventId": item.get("event_id"),
        "recipientId": item.get("recipient_id"),
        "recipientRole": item.get("recipient_role"),
        "eventType": item.get("event_type"),
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "readAt": item.get("read_at"),
        "archivedAt": item.get("archived_at"),
        "metadata": item.get("metadata") or {},
        "actorId": item.get("actor_id"),
        "actorRole": item.get("actor_role"),
        "deliveryCategory": item.get("category") or delivery.get("category"),
        "deliveryChannels": delivery.get("channels") or {},
    }


def push_token_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tokenReference": item.get("token_reference"),
        "platform": item.get("platform"),
        "status": item.get("status"),
        "tokenHashPrefix": str(item.get("token_hash") or "")[:12],
        "hasProviderReference": bool(item.get("provider_token_reference")),
        "createdAt": item.get("created_at"),
        "lastSeenAt": item.get("last_seen_at"),
        "revokedAt": item.get("revoked_at"),
    }


def _record_event_attempts(event_ids: list[str], metadata_key: str, attempt: dict[str, Any]) -> None:
    for event_id in [event_id for event_id in event_ids if event_id]:
        item = notification_repo.get_event(event_id)
        if not item:
            continue
        if item.get("owner_classification") == "global_nonprivate":
            continue
        metadata = dict(item.get("metadata") or {})
        attempts = list(metadata.get(metadata_key) or [])
        attempts.append(attempt)
        metadata[metadata_key] = attempts[-5:]
        notification_repo.update_event(event_id, {"metadata": metadata})


def _send_email_digest_provider(payload: dict[str, Any]) -> dict[str, Any]:
    ses = boto3.client("ses", region_name=settings.aws_region)
    response = ses.send_email(
        Source=settings.notification_email_sender,
        Destination={"ToAddresses": [payload["recipientEmail"]]},
        Message={
            "Subject": {"Data": payload["subject"]},
            "Body": {"Html": {"Data": payload["html"]}},
        },
    )
    return {"messageId": response.get("MessageId")}


def _send_push_provider(payload: dict[str, Any]) -> dict[str, Any]:
    endpoint = _safe_text(settings.notification_push_provider_endpoint_url)
    if not endpoint:
        raise RuntimeError("notification push provider endpoint is not configured")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = _safe_text(settings.notification_push_provider_api_key)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=5) as response:
        raw = response.read().decode("utf-8")
    return {"statusCode": response.status, "bodyHash": _hash_value(raw) if raw else None}


def _digest_email_html(items: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"<li><strong>{_html_escape(item.get('title'))}</strong>: {_html_escape(item.get('summary'))}</li>"
        for item in items
    )
    return f"<h1>STOA notification digest</h1><ul>{rows}</ul>"


def _redacted_provider_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"resultType": type(value).__name__}
    safe: dict[str, Any] = {}
    for key, raw in value.items():
        key_text = str(key)
        lowered = key_text.lower()
        if any(marker in lowered for marker in ("secret", "token", "key", "authorization")):
            safe[key_text] = "configured" if raw else "missing"
            continue
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            safe[key_text] = _redacted_text(raw) if isinstance(raw, str) else raw
    return safe


def _redacted_error_class(exc: Exception) -> str:
    return type(exc).__name__


def _redacted_reference(value: str) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    digest = _hash_value(text)
    return f"ref-{digest[:12]}"


def _hash_value(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _redacted_text(value: str) -> str:
    lowered = value.lower()
    if any(marker in lowered for marker in ("secret", "token", "sk_live", "sk_test", "bearer ")):
        return "[redacted]"
    return value[:200]


def _html_escape(value: Any) -> str:
    text = _safe_text(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _visible_to_user(item: dict[str, Any], *, user_id: str, role: str) -> bool:
    return item.get("recipient_id") == user_id or (
        item.get("recipient_id") in {None, ""} and item.get("recipient_role") == role
    )


def _sort_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def _best_effort_disabled() -> bool:
    if settings.environment.strip().lower() in {"production", "prod"}:
        return False
    return os.getenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS") != "true"


def _clean_text(value: str, *, limit: int) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:limit]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in metadata.items()
        if value is not None and "s3_key" not in str(key).lower()
    }


def _digest_safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    private_markers = ("s3", "artifact", "presigned", "weekly-reports/", "html", "raw")
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        value_text = str(value)
        combined = f"{key_text} {value_text}".lower()
        if any(marker in combined for marker in private_markers):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key_text] = value
    return safe


def _merged_preferences(raw: Any) -> dict[str, dict[str, bool]]:
    merged = default_preferences()
    if not isinstance(raw, dict):
        return merged
    for category, channels in raw.items():
        if category not in PREFERENCE_CATEGORIES or not isinstance(channels, dict):
            continue
        for channel, enabled in channels.items():
            if channel in PREFERENCE_CHANNELS and isinstance(enabled, bool):
                merged[category][channel] = enabled
    return merged
