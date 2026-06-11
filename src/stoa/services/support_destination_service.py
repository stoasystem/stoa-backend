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
CONTRACT_DEFINED_REFUSED_DESTINATIONS = {
    "external_write",
    "shared_mailbox",
    "zendesk_ticket",
    "freshdesk_ticket",
    "helpscout_conversation",
}
DELIVERY_STATUSES = {"created", "refused", "queued", "sent", "failed", "retried"}
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
                },
            },
        )
    return _public_record(saved)


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
        "tags": ["stoa", "support-handoff", "internal-queue"],
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
