"""Support SLA analytics and controlled CRM/customer messaging."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from stoa.config import Settings
from stoa.db.repositories import report_repo
from stoa.services import release_evidence_service, report_recovery_service, support_destination_service


MESSAGE_TEMPLATES = {
    "support_receipt": {"version": "v1", "trigger": "support_delivery_created"},
    "status_update": {"version": "v1", "trigger": "provider_status_changed"},
    "resolution": {"version": "v1", "trigger": "support_resolved"},
    "escalation": {"version": "v1", "trigger": "support_escalated"},
}
MESSAGE_DESTINATIONS = {"customer_email", "support_crm"}
SLA_TARGET_MINUTES = {
    "created": 30,
    "queued": 30,
    "delivery_pending": 30,
    "delivered": 240,
    "acknowledged": 240,
    "in_progress": 1440,
    "waiting_on_customer": 1440,
    "reopened": 240,
}
FAILED_STATUSES = {"failed", "delivery_failed", "refused"}
FIRST_RESPONSE_STATUSES = {"in_progress", "waiting_on_customer", "resolved"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_support_sla_analytics(
    *,
    settings: Settings,
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Build metadata-only support SLA analytics from recent delivery summaries."""
    result = report_repo.list_support_handoff_delivery_summaries(
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    deliveries = [
        support_destination_service.support_handoff_delivery_response(item)
        for item in result.get("Items", [])
    ]
    messages = [
        support_crm_message_response(item)
        for item in report_repo.list_support_crm_message_events(limit=limit).get("Items", [])
    ]
    now = datetime.now(timezone.utc)
    status_counts: dict[str, int] = {}
    destination_counts: dict[str, int] = {}
    lifecycle_counts = {
        "queued": 0,
        "delivered": 0,
        "acknowledged": 0,
        "first_response": 0,
        "resolved": 0,
        "failed": 0,
        "reopened": 0,
    }
    overdue: list[dict[str, Any]] = []
    third_party_count = 0
    provider_failure_count = 0
    retry_backlog = 0
    sync_conflicts = 0

    for delivery in deliveries:
        status = str(delivery.get("status") or "unknown")
        destination = str(delivery.get("destination_mode") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        destination_counts[destination] = destination_counts.get(destination, 0) + 1
        if status in {"created", "queued", "delivery_pending"}:
            lifecycle_counts["queued"] += 1
        if status == "delivered":
            lifecycle_counts["delivered"] += 1
        if status == "acknowledged":
            lifecycle_counts["acknowledged"] += 1
        if status in FIRST_RESPONSE_STATUSES:
            lifecycle_counts["first_response"] += 1
        if status == "resolved":
            lifecycle_counts["resolved"] += 1
        if status in FAILED_STATUSES:
            lifecycle_counts["failed"] += 1
        if status == "reopened":
            lifecycle_counts["reopened"] += 1
        if destination == support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION:
            third_party_count += 1
        if _is_provider_failure(delivery):
            provider_failure_count += 1
        if bool(delivery.get("retryable")):
            retry_backlog += 1
        if bool(delivery.get("sync_conflict")) or status == "sync_conflict":
            sync_conflicts += 1
        overdue_item = _overdue_summary(delivery, now)
        if overdue_item:
            overdue.append(overdue_item)

    outcome_counts: dict[str, int] = {}
    for message in messages:
        outcome = str(message.get("outcome") or "unknown")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    provider_failure_rate = 0.0 if third_party_count == 0 else round(provider_failure_count / third_party_count, 4)
    response = {
        "generated_at": now_iso(),
        "window": {"date_from": date_from, "date_to": date_to, "limit": limit},
        "sample_size": len(deliveries),
        "status_counts": status_counts,
        "destination_counts": destination_counts,
        "sla": {
            "targets_minutes": SLA_TARGET_MINUTES,
            "lifecycle_counts": lifecycle_counts,
            "overdue_count": len(overdue),
            "overdue_deliveries": overdue[:25],
        },
        "provider": {
            "third_party_count": third_party_count,
            "failure_count": provider_failure_count,
            "failure_rate": provider_failure_rate,
            "sync_conflicts": sync_conflicts,
        },
        "retry": {"backlog_count": retry_backlog},
        "messaging": {
            "approved": bool(settings.support_crm_messaging_approved),
            "destination_approved": bool(settings.support_crm_destination_approved),
            "outcome_counts": outcome_counts,
            "recent": messages[:25],
        },
    }
    release_evidence_service.private_marker_hits(response)
    return response


def send_support_message(
    *,
    delivery_id: str,
    template: str,
    destination: str,
    trigger: str,
    actor: str,
    request_id: str | None,
    settings: Settings,
    customer_opted_out: bool = False,
) -> dict[str, Any] | None:
    """Persist one controlled support message outcome without raw customer text."""
    record = report_repo.get_support_handoff_delivery_record(delivery_id)
    if not record:
        return None
    delivery = support_destination_service.support_handoff_delivery_response(record)
    safe_template = _safe_text(template)
    safe_destination = _safe_text(destination)
    now = now_iso()
    refusal_reasons: list[str] = []
    failure_reasons: list[str] = []

    if not settings.support_crm_messaging_approved:
        refusal_reasons.append("support CRM messaging is not approved")
    if not settings.support_crm_destination_approved:
        refusal_reasons.append("support CRM destination is not approved")
    if safe_destination not in MESSAGE_DESTINATIONS:
        refusal_reasons.append("support CRM destination is unsupported")
    if safe_template not in MESSAGE_TEMPLATES:
        refusal_reasons.append("support CRM template is unsupported")
    elif safe_template not in set(settings.support_crm_approved_templates):
        refusal_reasons.append("support CRM template is not approved")
    if customer_opted_out or delivery_id in set(settings.support_crm_opt_out_delivery_ids):
        refusal_reasons.append("customer opted out of support CRM messaging")

    if refusal_reasons:
        outcome = "refused"
    elif settings.support_crm_fail_delivery:
        outcome = "failed"
        failure_reasons.append("support CRM provider failed: [private-credential]")
    else:
        outcome = "sent"

    message_id = hashlib.sha256(
        f"{delivery_id}:{safe_template}:{safe_destination}:{now}:{request_id or ''}".encode()
    ).hexdigest()[:32]
    template_info = MESSAGE_TEMPLATES.get(safe_template, {"version": "unknown", "trigger": ""})
    event = {
        "message_id": message_id,
        "event_at": now,
        "delivery_id": delivery_id,
        "package_id": delivery.get("package_id"),
        "actor": _safe_text(actor) or "unknown-admin",
        "source": "admin_api",
        "destination": safe_destination,
        "template": safe_template,
        "template_version": template_info.get("version"),
        "trigger": _safe_text(trigger) or template_info.get("trigger"),
        "outcome": outcome,
        "correlation_id": request_id,
        "delivery_status": delivery.get("status"),
        "provider_ticket_id": delivery.get("provider_ticket_id"),
        "provider_status": delivery.get("provider_status"),
        "customer_visible": outcome == "sent" and safe_destination == "customer_email",
        "refusal_reasons": [_safe_text(value) for value in refusal_reasons],
        "failure_reasons": [_safe_text(value) for value in failure_reasons],
    }
    report_repo.put_support_crm_message_event(delivery_id, event)
    return support_crm_message_response(event)


def support_crm_message_response(event: dict[str, Any]) -> dict[str, Any]:
    response = {
        "message_id": _safe_text(event.get("message_id")),
        "event_at": _safe_text(event.get("event_at")),
        "delivery_id": _safe_text(event.get("delivery_id")),
        "package_id": _safe_text(event.get("package_id")),
        "actor": _safe_text(event.get("actor")),
        "source": _safe_text(event.get("source")),
        "destination": _safe_text(event.get("destination")),
        "template": _safe_text(event.get("template")),
        "template_version": _safe_text(event.get("template_version")),
        "trigger": _safe_text(event.get("trigger")),
        "outcome": _safe_text(event.get("outcome")),
        "correlation_id": _safe_text(event.get("correlation_id")),
        "delivery_status": _safe_text(event.get("delivery_status")),
        "provider_ticket_id": _safe_text(event.get("provider_ticket_id")),
        "provider_status": _safe_text(event.get("provider_status")),
        "customer_visible": bool(event.get("customer_visible")),
        "refusal_reasons": [_safe_text(value) for value in event.get("refusal_reasons", [])],
        "failure_reasons": [_safe_text(value) for value in event.get("failure_reasons", [])],
    }
    release_evidence_service.private_marker_hits(response)
    return response


def _overdue_summary(delivery: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    status = str(delivery.get("status") or "")
    target = SLA_TARGET_MINUTES.get(status)
    created = _parse_iso(_safe_text(delivery.get("created_at")))
    if target is None or created is None:
        return None
    age_minutes = int((now - created).total_seconds() // 60)
    if age_minutes <= target:
        return None
    return {
        "delivery_id": _safe_text(delivery.get("delivery_id")),
        "package_id": _safe_text(delivery.get("package_id")),
        "status": status,
        "destination_mode": _safe_text(delivery.get("destination_mode")),
        "age_minutes": age_minutes,
        "target_minutes": target,
        "retryable": bool(delivery.get("retryable")),
        "provider_status": _safe_text(delivery.get("provider_status")),
        "sync_conflict": bool(delivery.get("sync_conflict")),
    }


def _is_provider_failure(delivery: dict[str, Any]) -> bool:
    return (
        str(delivery.get("destination_mode") or "") == support_destination_service.THIRD_PARTY_SUPPORT_DESTINATION
        and (
            str(delivery.get("status") or "") in FAILED_STATUSES
            or bool(delivery.get("provider_error_code"))
            or str(delivery.get("provider_result") or "") in {"failed", "retry_failed"}
        )
    )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    text = report_recovery_service.redact_private_artifact_text(str(value))
    return text[:500]
