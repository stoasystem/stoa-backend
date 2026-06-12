"""Support handoff destination delivery orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from stoa.config import Settings
from stoa.db.repositories import report_repo
from stoa.services import release_evidence_service, report_recovery_service


INTERNAL_QUEUE_DESTINATION = "internal_queue"
THIRD_PARTY_SUPPORT_DESTINATION = "third_party_support"
CONTRACT_DEFINED_REFUSED_DESTINATIONS = {
    "external_write",
    "shared_mailbox",
    "zendesk_ticket",
    "freshdesk_ticket",
    "helpscout_conversation",
}
DELIVERY_STATUSES = {
    "created",
    "refused",
    "queued",
    "sent",
    "failed",
    "retried",
    "delivery_pending",
    "delivered",
    "delivery_failed",
}
MAX_PROVIDER_RETRY_ATTEMPTS = 3
PROVIDER_STATUS_MAP = {
    "new": "acknowledged",
    "open": "acknowledged",
    "pending": "in_progress",
    "in_progress": "in_progress",
    "waiting_on_customer": "waiting_on_customer",
    "solved": "resolved",
    "closed": "resolved",
    "resolved": "resolved",
    "reopened": "reopened",
}
PRIVATE_FREE_TEXT_PATTERN = re.compile(
    r"\b(access_token|id_token|refresh_token|password|secret|cookie|authorization)\b\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def refuse_destination(
    *,
    destination_mode: str,
    actor: str,
    reason: str,
    request_id: str | None,
    refusal_reason: str,
) -> dict[str, Any]:
    """Persist a metadata-only refused delivery without reading evidence."""
    now = now_iso()
    payload = _canonical_payload(
        destination_mode=destination_mode,
        reason=reason,
        actor=actor,
        evidence_reference_ids=[],
        section_summaries=[],
        validation_status="refused",
        privacy={"metadata_only": True, "passed": True, "violation_count": 0, "violations": []},
    )
    return _persist_delivery(
        package_id=None,
        destination_mode=destination_mode,
        status="refused",
        actor=actor,
        reason=reason,
        request_id=request_id,
        now=now,
        payload=payload,
        refusal_reasons=[refusal_reason],
        failure_reasons=[],
        privacy=payload["privacy"],
        evidence_reference_ids=[],
        retryable=False,
    )


def deliver_internal_queue(
    *,
    package: dict[str, Any],
    actor: str,
    reason: str,
    request_id: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Queue or refuse one support handoff package for the internal operator queue."""
    destination_mode = str(package.get("destination", {}).get("mode") or INTERNAL_QUEUE_DESTINATION)
    evidence_reference_ids = [
        safe_id for ref in package.get("evidence_references", []) if (safe_id := _safe_text(ref.get("id")))
    ]
    privacy = _privacy_result(package)
    validation_status = str(package.get("validation", {}).get("status") or "failed")
    section_summaries = _section_summaries(package.get("sections", []))
    payload = _canonical_payload(
        destination_mode=destination_mode,
        reason=reason,
        actor=actor,
        evidence_reference_ids=evidence_reference_ids,
        section_summaries=section_summaries,
        validation_status=validation_status,
        privacy=privacy,
    )

    refusal_reasons: list[str] = []
    if destination_mode != INTERNAL_QUEUE_DESTINATION:
        refusal_reasons.append("destination is not approved for Phase 149 delivery")
    if not settings.support_internal_queue_approved:
        refusal_reasons.append("support internal queue delivery is not approved")
    if validation_status != "passed":
        refusal_reasons.append("support handoff package validation did not pass")
    if not privacy.get("passed", False):
        refusal_reasons.append("privacy denylist check failed")
    if release_evidence_service.private_marker_hits(payload):
        refusal_reasons.append("delivery payload privacy denylist check failed")

    status = "refused" if refusal_reasons else "queued"
    return _persist_delivery(
        package_id=str(package.get("package_id") or ""),
        destination_mode=destination_mode,
        status=status,
        actor=actor,
        reason=reason,
        request_id=request_id,
        now=now_iso(),
        payload=payload,
        refusal_reasons=refusal_reasons,
        failure_reasons=[],
        privacy=privacy,
        evidence_reference_ids=evidence_reference_ids,
        retryable=status == "queued",
    )


def deliver_third_party_support(
    *,
    package: dict[str, Any],
    actor: str,
    reason: str,
    request_id: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """Create or refuse one metadata-only third-party provider delivery."""
    destination_mode = str(package.get("destination", {}).get("mode") or THIRD_PARTY_SUPPORT_DESTINATION)
    evidence_reference_ids = [
        safe_id for ref in package.get("evidence_references", []) if (safe_id := _safe_text(ref.get("id")))
    ]
    privacy = _privacy_result(package)
    validation_status = str(package.get("validation", {}).get("status") or "failed")
    section_summaries = _section_summaries(package.get("sections", []))
    readiness = _third_party_readiness(settings)
    payload = _canonical_payload(
        destination_mode=destination_mode,
        reason=reason,
        actor=actor,
        evidence_reference_ids=evidence_reference_ids,
        section_summaries=section_summaries,
        validation_status=validation_status,
        privacy=privacy,
    )

    refusal_reasons: list[str] = []
    if destination_mode != THIRD_PARTY_SUPPORT_DESTINATION:
        refusal_reasons.append("destination is not approved for third-party provider delivery")
    if readiness["state"] != "verified":
        refusal_reasons.extend(readiness["blockers"])
    if validation_status != "passed":
        refusal_reasons.append("support handoff package validation did not pass")
    if not privacy.get("passed", False):
        refusal_reasons.append("privacy denylist check failed")
    if release_evidence_service.private_marker_hits(payload):
        refusal_reasons.append("delivery payload privacy denylist check failed")

    if refusal_reasons:
        return _persist_delivery(
            package_id=str(package.get("package_id") or ""),
            destination_mode=destination_mode,
            status="refused",
            actor=actor,
            reason=reason,
            request_id=request_id,
            now=now_iso(),
            payload=payload,
            refusal_reasons=refusal_reasons,
            failure_reasons=[],
            privacy=privacy,
            evidence_reference_ids=evidence_reference_ids,
            retryable=False,
            provider_metadata={
                "provider_readiness": readiness,
                "provider_status": "not_ready",
                "provider_attempt_count": 0,
            },
        )

    if settings.support_third_party_provider_fail_delivery:
        return _persist_delivery(
            package_id=str(package.get("package_id") or ""),
            destination_mode=destination_mode,
            status="delivery_failed",
            actor=actor,
            reason=reason,
            request_id=request_id,
            now=now_iso(),
            payload=payload,
            refusal_reasons=[],
            failure_reasons=["provider delivery failed: [private-credential]"],
            privacy=privacy,
            evidence_reference_ids=evidence_reference_ids,
            retryable=True,
            provider_metadata={
                "provider_readiness": readiness,
                "provider_status": "failed",
                "provider_result": "failed",
                "provider_error_code": "provider_delivery_failed",
                "provider_attempt_count": 1,
            },
        )

    return _persist_delivery(
        package_id=str(package.get("package_id") or ""),
        destination_mode=destination_mode,
        status="delivered",
        actor=actor,
        reason=reason,
        request_id=request_id,
        now=now_iso(),
        payload=payload,
        refusal_reasons=[],
        failure_reasons=[],
        privacy=privacy,
        evidence_reference_ids=evidence_reference_ids,
        retryable=False,
        provider_metadata={
            "provider_readiness": readiness,
            "provider_status": "created",
            "provider_result": "created",
            "provider_attempt_count": 1,
        },
    )


def transition_delivery_status(
    *,
    delivery_id: str,
    status: str,
    actor: str,
    request_id: str | None = None,
    retry_count: int | None = None,
    retryable: bool | None = None,
    refusal_reasons: list[str] | None = None,
    failure_reasons: list[str] | None = None,
) -> dict[str, Any] | None:
    """Record an internal delivery lifecycle transition and append audit metadata."""
    if status not in DELIVERY_STATUSES:
        raise ValueError(f"Unsupported delivery status: {status}")
    now = now_iso()
    safe_refusals = [_safe_text(value) for value in refusal_reasons or []]
    safe_failures = [_safe_text(value) for value in failure_reasons or []]
    updated = report_repo.update_support_handoff_delivery_status(
        delivery_id,
        status=status,
        updated_at=now,
        actor=_safe_text(actor) or "unknown-admin",
        correlation_id=request_id,
        retry_count=retry_count,
        retryable=retryable,
        refusal_reasons=safe_refusals,
        failure_reasons=safe_failures,
    )
    if not updated:
        return None
    report_repo.put_support_handoff_delivery_audit_event(
        delivery_id,
        {
            "event_id": hashlib.sha256(f"{delivery_id}:{now}:{status}".encode()).hexdigest()[:32],
            "event_at": now,
            "delivery_id": delivery_id,
            "package_id": updated.get("package_id"),
            "actor": _safe_text(actor) or "unknown-admin",
            "action": "support_handoff_delivery_status_update",
            "source": "internal_lifecycle",
            "result": status,
            "correlation_id": request_id,
            "metadata": {
                "destination_mode": updated.get("destination_mode"),
                "status": status,
                "retry_count": updated.get("retry_count", 0),
                "retryable": bool(updated.get("retryable")),
                "payload_digest": updated.get("payload_digest"),
                "refusal_reasons": safe_refusals,
                "failure_reasons": safe_failures,
            },
        },
    )
    return support_handoff_delivery_response(updated)


def retry_provider_delivery(
    *,
    delivery_id: str,
    actor: str,
    request_id: str | None,
    settings: Settings,
) -> dict[str, Any] | None:
    """Retry a failed provider delivery using bounded attempt metadata."""
    record = report_repo.get_support_handoff_delivery_record(delivery_id)
    if not record:
        return None
    status = str(record.get("status") or "")
    retry_count = int(record.get("retry_count") or 0)
    if (
        record.get("destination_mode") != THIRD_PARTY_SUPPORT_DESTINATION
        or status not in {"delivery_failed", "failed", "retry_pending"}
        or not bool(record.get("retryable"))
    ):
        return support_handoff_delivery_response(record)

    now = now_iso()
    next_count = retry_count + 1
    exhausted = next_count >= MAX_PROVIDER_RETRY_ATTEMPTS
    failure_reasons = [_safe_text(value) for value in record.get("failure_reasons", [])]
    provider_metadata: dict[str, Any] = {
        "retry_count": next_count,
        "provider_attempt_count": next_count,
        "last_retry_at": now,
        "max_retry_attempts": MAX_PROVIDER_RETRY_ATTEMPTS,
        "retry_exhausted": exhausted,
        "next_retry_at": None if exhausted else now,
    }

    if settings.support_third_party_provider_fail_delivery:
        new_status = "delivery_failed"
        retryable = not exhausted
        failure_reasons = [*failure_reasons, "provider retry failed: [private-credential]"]
        provider_metadata.update(
            {
                "provider_status": "failed",
                "provider_result": "retry_failed",
                "provider_error_code": "provider_retry_failed",
            }
        )
    else:
        new_status = "delivered"
        retryable = False
        provider_metadata.update(
            {
                "provider_status": "created",
                "provider_result": "retried",
                "provider_error_code": None,
                "retry_exhausted": False,
                "next_retry_at": None,
            }
        )

    updated = report_repo.update_support_handoff_delivery_status(
        delivery_id,
        status=new_status,
        updated_at=now,
        actor=_safe_text(actor) or "unknown-admin",
        correlation_id=request_id,
        retry_count=next_count,
        retryable=retryable,
        failure_reasons=failure_reasons,
        extra_updates=provider_metadata,
    )
    if not updated:
        return None
    _write_delivery_audit(
        delivery_id,
        updated=updated,
        actor=actor,
        request_id=request_id,
        action="support_handoff_delivery_retry",
        result=new_status,
        now=now,
    )
    return support_handoff_delivery_response(updated)


def sync_provider_ticket(
    *,
    delivery_id: str,
    provider_event_id: str,
    provider_status: str,
    provider_updated_at: str,
    actor: str,
    request_id: str | None,
    provider_assignee: str | None = None,
    provider_priority: str | None = None,
) -> dict[str, Any] | None:
    """Normalize one provider status update without storing raw provider payloads."""
    record = report_repo.get_support_handoff_delivery_record(delivery_id)
    if not record:
        return None
    if record.get("destination_mode") != THIRD_PARTY_SUPPORT_DESTINATION:
        return support_handoff_delivery_response(record)

    safe_event_id = _safe_text(provider_event_id) or ""
    seen_events = [_safe_text(value) for value in record.get("provider_sync_event_ids", [])]
    if safe_event_id in seen_events:
        return support_handoff_delivery_response({**record, "last_sync_result": "duplicate"})

    now = now_iso()
    current_provider_updated = _safe_text(record.get("provider_updated_at"))
    normalized = PROVIDER_STATUS_MAP.get((_safe_text(provider_status) or "").lower())
    extra_updates: dict[str, Any] = {
        "provider_sync_event_ids": [*seen_events, safe_event_id][-20:],
        "last_synced_at": now,
        "provider_last_event_id": safe_event_id,
        "provider_assignee": _safe_text(provider_assignee),
        "provider_priority": _safe_text(provider_priority),
    }
    new_status = str(record.get("status") or "sync_conflict")
    conflict_reason: str | None = None

    if current_provider_updated and provider_updated_at <= current_provider_updated:
        conflict_reason = "stale provider update refused"
    elif not normalized:
        conflict_reason = "provider status could not be mapped"
    elif str(record.get("status") or "") in {"resolved"} and normalized not in {"resolved", "reopened"}:
        conflict_reason = "provider update conflicts with local terminal state"
    else:
        new_status = normalized
        extra_updates.update(
            {
                "provider_status": _safe_text(provider_status),
                "provider_updated_at": _safe_text(provider_updated_at),
                "sync_conflict": False,
                "sync_conflict_reason": None,
                "last_sync_result": "applied",
            }
        )

    if conflict_reason:
        new_status = "sync_conflict"
        extra_updates.update(
            {
                "sync_conflict": True,
                "sync_conflict_reason": conflict_reason,
                "last_sync_result": "refused",
            }
        )

    updated = report_repo.update_support_handoff_delivery_status(
        delivery_id,
        status=new_status,
        updated_at=now,
        actor=_safe_text(actor) or "unknown-admin",
        correlation_id=request_id,
        retryable=bool(record.get("retryable", False)),
        refusal_reasons=record.get("refusal_reasons", []),
        failure_reasons=record.get("failure_reasons", []),
        extra_updates=extra_updates,
    )
    if not updated:
        return None
    _write_delivery_audit(
        delivery_id,
        updated=updated,
        actor=actor,
        request_id=request_id,
        action="support_handoff_delivery_provider_sync",
        result=new_status,
        now=now,
    )
    return support_handoff_delivery_response(updated)


def support_handoff_delivery_response(record: dict[str, Any]) -> dict[str, Any]:
    """Return the metadata-only API shape for one delivery summary."""
    status = str(record.get("status") or record.get("lifecycle_status") or "failed")
    retry_count = int(record.get("retry_count") or 0)
    retryable = bool(record.get("retryable"))
    response = {
        "delivery_id": _safe_text(record.get("delivery_id")),
        "package_id": _safe_text(record.get("package_id")),
        "destination_mode": _safe_text(record.get("destination_mode")),
        "status": status,
        "lifecycle_status": status,
        "actor": _safe_text(record.get("actor")),
        "created_at": _safe_text(record.get("created_at")),
        "updated_at": _safe_text(record.get("updated_at")),
        "correlation_id": _safe_text(record.get("correlation_id")),
        "idempotency_key": _safe_text(record.get("idempotency_key")),
        "retry_count": retry_count,
        "retryable": retryable,
        "retry": _retry_visibility(record, status=status, retry_count=retry_count, retryable=retryable),
        "provider_object_reference": _safe_text(record.get("provider_object_reference")),
        "provider_object_url": _safe_text(record.get("provider_object_url")),
        "provider_ticket_id": _safe_text(record.get("provider_ticket_id")),
        "provider_ticket_url": _safe_text(record.get("provider_ticket_url")),
        "provider_status": _safe_text(record.get("provider_status")),
        "provider_readiness": _provider_readiness_response(record.get("provider_readiness")),
        "provider_result": _safe_text(record.get("provider_result")),
        "provider_error_code": _safe_text(record.get("provider_error_code")),
        "provider_attempt_count": int(record.get("provider_attempt_count") or 0),
        "provider_updated_at": _safe_text(record.get("provider_updated_at")),
        "last_synced_at": _safe_text(record.get("last_synced_at")),
        "provider_assignee": _safe_text(record.get("provider_assignee")),
        "provider_priority": _safe_text(record.get("provider_priority")),
        "sync_conflict": bool(record.get("sync_conflict", False)),
        "sync_conflict_reason": _safe_text(record.get("sync_conflict_reason")),
        "last_sync_result": _safe_text(record.get("last_sync_result")),
        "retry_exhausted": bool(record.get("retry_exhausted", False)),
        "max_retry_attempts": int(record.get("max_retry_attempts") or MAX_PROVIDER_RETRY_ATTEMPTS),
        "next_retry_at": _safe_text(record.get("next_retry_at")),
        "last_retry_at": _safe_text(record.get("last_retry_at")),
        "refusal_reasons": [_safe_text(value) for value in record.get("refusal_reasons", [])],
        "failure_reasons": [_safe_text(value) for value in record.get("failure_reasons", [])],
        "privacy": _privacy_summary(record.get("privacy")),
        "evidence_reference_ids": [
            safe_id for value in record.get("evidence_reference_ids", []) if (safe_id := _safe_text(value))
        ],
        "payload_digest": _safe_text(record.get("payload_digest")),
        "payload_summary": _payload_summary(record.get("payload_summary")),
    }
    release_evidence_service.private_marker_hits(response)
    return response


def _write_delivery_audit(
    delivery_id: str,
    *,
    updated: dict[str, Any],
    actor: str,
    request_id: str | None,
    action: str,
    result: str,
    now: str,
) -> None:
    report_repo.put_support_handoff_delivery_audit_event(
        delivery_id,
        {
            "event_id": hashlib.sha256(f"{delivery_id}:{now}:{action}:{result}".encode()).hexdigest()[:32],
            "event_at": now,
            "delivery_id": delivery_id,
            "package_id": updated.get("package_id"),
            "actor": _safe_text(actor) or "unknown-admin",
            "action": action,
            "source": "admin_api",
            "result": result,
            "correlation_id": request_id,
            "metadata": {
                "destination_mode": updated.get("destination_mode"),
                "status": result,
                "retry_count": updated.get("retry_count", 0),
                "retryable": bool(updated.get("retryable")),
                "payload_digest": updated.get("payload_digest"),
                "privacy_passed": bool(updated.get("privacy", {}).get("passed")),
                "refusal_reasons": [_safe_text(value) for value in updated.get("refusal_reasons", [])],
                "failure_reasons": [_safe_text(value) for value in updated.get("failure_reasons", [])],
                "provider_status": _safe_text(updated.get("provider_status")),
                "last_sync_result": _safe_text(updated.get("last_sync_result")),
                "sync_conflict_reason": _safe_text(updated.get("sync_conflict_reason")),
            },
        },
    )


def support_handoff_delivery_audit_response(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    response = {
        "event_id": _safe_text(event.get("event_id")),
        "event_at": _safe_text(event.get("event_at")),
        "delivery_id": _safe_text(event.get("delivery_id")),
        "package_id": _safe_text(event.get("package_id")),
        "actor": _safe_text(event.get("actor")),
        "action": _safe_text(event.get("action")),
        "source": _safe_text(event.get("source")),
        "result": _safe_text(event.get("result")),
        "correlation_id": _safe_text(event.get("correlation_id")),
        "metadata": {
            "destination_mode": _safe_text(metadata.get("destination_mode")),
            "status": _safe_text(metadata.get("status")),
            "retry_count": int(metadata.get("retry_count") or 0),
            "retryable": bool(metadata.get("retryable", False)),
            "payload_digest": _safe_text(metadata.get("payload_digest")),
            "privacy_passed": bool(metadata.get("privacy_passed", False)),
            "refusal_reasons": [_safe_text(value) for value in metadata.get("refusal_reasons", [])],
            "failure_reasons": [_safe_text(value) for value in metadata.get("failure_reasons", [])],
        },
    }
    release_evidence_service.private_marker_hits(response)
    return response


def _persist_delivery(
    *,
    package_id: str | None,
    destination_mode: str,
    status: str,
    actor: str,
    reason: str,
    request_id: str | None,
    now: str,
    payload: dict[str, Any],
    refusal_reasons: list[str],
    failure_reasons: list[str],
    privacy: dict[str, Any],
    evidence_reference_ids: list[str],
    retryable: bool,
    provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in DELIVERY_STATUSES:
        status = "failed"
        failure_reasons = [*failure_reasons, "invalid delivery status"]

    payload_digest = _digest(payload)
    idempotency_key = _digest(
        {
            "destination_mode": destination_mode,
            "reason": _safe_text(reason),
            "actor": _safe_text(actor),
            "correlation_id": request_id,
            "evidence_reference_ids": evidence_reference_ids,
            "payload_digest": payload_digest,
        }
    )
    delivery_id = f"support-delivery-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}"
    provider_metadata = _provider_metadata(
        provider_metadata,
        delivery_id=delivery_id,
        destination_mode=destination_mode,
    )
    record = {
        "delivery_id": delivery_id,
        "package_id": package_id,
        "destination_mode": destination_mode,
        "status": status,
        "lifecycle_status": status,
        "actor": _safe_text(actor) or "unknown-admin",
        "created_at": now,
        "updated_at": now,
        "correlation_id": request_id,
        "idempotency_key": idempotency_key,
        "retry_count": 0,
        "retryable": retryable,
        "provider_object_reference": delivery_id,
        "provider_object_url": None,
        **provider_metadata,
        "refusal_reasons": [_safe_text(value) for value in refusal_reasons],
        "failure_reasons": [_safe_text(value) for value in failure_reasons],
        "privacy": privacy,
        "evidence_reference_ids": evidence_reference_ids,
        "payload_digest": payload_digest,
        "payload_summary": {
            "schema_version": payload["schema_version"],
            "tags": payload["tags"],
            "section_summaries": payload["section_summaries"],
            "validation_status": payload["validation_status"],
        },
    }
    saved, created = report_repo.put_support_handoff_delivery_record(delivery_id, record)
    if created:
        report_repo.put_support_handoff_delivery_audit_event(
            delivery_id,
            {
                "event_id": hashlib.sha256(f"{delivery_id}:{now}:created".encode()).hexdigest()[:32],
                "event_at": now,
                "delivery_id": delivery_id,
                "package_id": package_id,
                "actor": record["actor"],
                "action": "support_handoff_delivery",
                "source": "admin_api",
                "result": status,
                "correlation_id": request_id,
                "metadata": {
                    "destination_mode": destination_mode,
                    "status": status,
                    "idempotency_key": idempotency_key,
                    "payload_digest": payload_digest,
                    "privacy_passed": bool(privacy.get("passed")),
                    "refusal_reasons": record["refusal_reasons"],
                    "failure_reasons": record["failure_reasons"],
                    "provider_status": record.get("provider_status"),
                    "provider_result": record.get("provider_result"),
                    "provider_error_code": record.get("provider_error_code"),
                },
            },
        )
    return support_handoff_delivery_response(_public_record(saved))


def _provider_metadata(
    value: dict[str, Any] | None,
    *,
    delivery_id: str,
    destination_mode: str,
) -> dict[str, Any]:
    if destination_mode != THIRD_PARTY_SUPPORT_DESTINATION:
        return {}
    if value is None:
        return {}
    safe_value = value if isinstance(value, dict) else {}
    ticket_created = _safe_text(safe_value.get("provider_result")) == "created"
    ticket_id = _safe_text(safe_value.get("provider_ticket_id"))
    if ticket_created and not ticket_id:
        ticket_id = f"stoa-ticket-{delivery_id.removeprefix('support-delivery-')[:16]}"
    ticket_url = _safe_text(safe_value.get("provider_ticket_url"))
    return {
        "provider_ticket_id": ticket_id,
        "provider_ticket_url": ticket_url,
        "provider_object_reference": ticket_id,
        "provider_object_url": ticket_url,
        "provider_status": _safe_text(safe_value.get("provider_status")) or "unknown",
        "provider_readiness": _provider_readiness_response(safe_value.get("provider_readiness")),
        "provider_result": _safe_text(safe_value.get("provider_result")),
        "provider_error_code": _safe_text(safe_value.get("provider_error_code")),
        "provider_attempt_count": int(safe_value.get("provider_attempt_count") or 0),
    }


def _retry_visibility(
    record: dict[str, Any],
    *,
    status: str,
    retry_count: int,
    retryable: bool,
) -> dict[str, Any]:
    if record.get("destination_mode") != INTERNAL_QUEUE_DESTINATION:
        if (
            record.get("destination_mode") == THIRD_PARTY_SUPPORT_DESTINATION
            and status in {"delivery_failed", "failed", "retry_pending"}
            and retryable
        ):
            return {"enabled": True, "reason": None, "count": retry_count}
        return {"enabled": False, "reason": "destination is not approved for retry", "count": retry_count}
    if status in {"refused"}:
        return {"enabled": False, "reason": "refused deliveries are not retryable", "count": retry_count}
    if not bool(record.get("privacy", {}).get("passed", False)):
        return {"enabled": False, "reason": "privacy-failed deliveries are not retryable", "count": retry_count}
    if not retryable:
        return {"enabled": False, "reason": "delivery state is not retryable", "count": retry_count}
    return {"enabled": True, "reason": None, "count": retry_count}


def _payload_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    section_summaries = []
    for section in value.get("section_summaries", []):
        if not isinstance(section, dict):
            continue
        reference = section.get("reference") if isinstance(section.get("reference"), dict) else {}
        section_summaries.append(
            {
                "type": _safe_text(section.get("type")),
                "status": _safe_text(section.get("status")),
                "reference": {
                    "type": _safe_text(reference.get("type")),
                    "id": _safe_text(reference.get("id")),
                }
                if reference
                else None,
            }
        )
    return {
        "schema_version": _safe_text(value.get("schema_version")),
        "tags": [_safe_text(tag) for tag in value.get("tags", [])],
        "section_summaries": section_summaries,
        "validation_status": _safe_text(value.get("validation_status")),
    }


def _privacy_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"metadata_only": True, "passed": False, "violation_count": 1, "violations": ["missing privacy result"]}
    return {
        "metadata_only": bool(value.get("metadata_only", True)),
        "private_artifact_fields_omitted": bool(value.get("private_artifact_fields_omitted", True)),
        "passed": bool(value.get("passed", False)),
        "violation_count": int(value.get("violation_count") or 0),
        "violations": [_safe_text(item) for item in value.get("violations", [])],
    }


def _canonical_payload(
    *,
    destination_mode: str,
    reason: str,
    actor: str,
    evidence_reference_ids: list[str],
    section_summaries: list[dict[str, Any]],
    validation_status: str,
    privacy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "destination_mode": destination_mode,
        "reason": _safe_text(reason),
        "generated_by": _safe_text(actor) or "unknown-admin",
        "evidence_reference_ids": evidence_reference_ids,
        "section_summaries": section_summaries,
        "validation_status": validation_status,
        "privacy": privacy,
        "tags": ["stoa", "support-handoff", destination_mode],
    }


def _third_party_readiness(settings: Settings) -> dict[str, Any]:
    blockers: list[str] = []
    approved = bool(settings.support_third_party_provider_approved)
    api_key = _safe_text(settings.support_third_party_provider_api_key)
    if not approved:
        blockers.append("third-party support provider is not approved")
    if not api_key:
        blockers.append("third-party support provider credentials are missing")
    if settings.support_third_party_provider_fail_delivery:
        state = "failed"
    elif blockers:
        state = "missing" if not api_key else "configured"
    else:
        state = "verified"
    return {
        "state": state,
        "approved": approved,
        "credentials": "configured" if api_key else "missing",
        "endpoint_configured": bool(_safe_text(settings.support_third_party_provider_endpoint_url)),
        "blockers": blockers,
    }


def _provider_readiness_response(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"state": "not_applicable", "approved": False, "credentials": "missing", "blockers": []}
    return {
        "state": _safe_text(value.get("state")) or "missing",
        "approved": bool(value.get("approved", False)),
        "credentials": _safe_text(value.get("credentials")) or "missing",
        "endpoint_configured": bool(value.get("endpoint_configured", False)),
        "blockers": [_safe_text(blocker) for blocker in value.get("blockers", [])],
    }


def _section_summaries(sections: object) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if not isinstance(sections, list):
        return summaries
    for section in sections:
        if not isinstance(section, dict):
            continue
        reference = section.get("reference") if isinstance(section.get("reference"), dict) else {}
        summaries.append(
            {
                "type": _safe_text(section.get("type")),
                "status": _safe_text(section.get("status")),
                "reference": {
                    "type": _safe_text(reference.get("type")),
                    "id": _safe_text(reference.get("id")),
                }
                if reference
                else None,
            }
        )
    return summaries


def _privacy_result(package: dict[str, Any]) -> dict[str, Any]:
    privacy = package.get("validation", {}).get("privacy")
    if not isinstance(privacy, dict):
        return {"metadata_only": True, "passed": False, "violation_count": 1, "violations": ["missing privacy result"]}
    return {
        "metadata_only": bool(privacy.get("metadata_only", True)),
        "private_artifact_fields_omitted": bool(privacy.get("private_artifact_fields_omitted", True)),
        "passed": bool(privacy.get("passed", False)),
        "violation_count": int(privacy.get("violation_count") or 0),
        "violations": [_safe_text(value) for value in privacy.get("violations", [])],
    }


def _digest(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_text(value: object) -> str | None:
    text = report_recovery_service.redact_private_artifact_text(value)
    if text is None:
        return None
    return PRIVATE_FREE_TEXT_PATTERN.sub("[private-credential]", str(text).strip())


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"PK", "SK", "entity_type"}}
