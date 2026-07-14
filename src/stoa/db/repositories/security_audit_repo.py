"""Append-only, allowlisted security lifecycle evidence."""

from __future__ import annotations

from typing import Any, Mapping

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


AUTHORIZATION_EVENT_TYPES = frozenset(
    {
        "authorization_denied",
        "authorization_sensitive_allowed",
        "authorization_probe_aggregated",
        "break_glass_notification_recorded",
        "break_glass_review_required",
    }
)


SAFE_AUDIT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "actor_id",
        "actor_role",
        "target_id",
        "target_type",
        "resource_type",
        "action",
        "purpose",
        "result_code",
        "version",
        "reason_code",
        "evidence_reference",
        "correlation_id",
        "command_id",
        "created_at",
    }
)


class DuplicateSecurityAuditEvent(RuntimeError):
    """An immutable audit event identifier has already been used."""


def project_audit_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Construct an audit row from safe scalar fields, never by redacting a payload."""
    projected = {
        key: event[key]
        for key in SAFE_AUDIT_FIELDS
        if key in event and event[key] is not None
    }
    if not str(projected.get("event_id") or "").strip():
        raise ValueError("event_id is required")
    if not str(projected.get("event_type") or "").strip():
        raise ValueError("event_type is required")
    return projected


def append_event(stream_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    safe = project_audit_event(event)
    row = {
        "PK": f"SECURITY_AUDIT#{stream_id}",
        "SK": f"EVENT#{safe['event_id']}",
        "entity_type": "security_audit_event",
        **safe,
    }
    try:
        get_table().put_item(
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise DuplicateSecurityAuditEvent("security audit event already exists") from exc
        raise
    return row


def append_authorization_event(stream_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    """Append one allowlisted policy decision or aggregate probe event."""
    if event.get("event_type") not in AUTHORIZATION_EVENT_TYPES:
        raise ValueError("unsupported authorization event type")
    return append_event(stream_id, event)


def append_break_glass_evidence(
    *,
    stream_id: str,
    event_id: str,
    actor_id: str,
    resource_type: str,
    action: str,
    purpose: str,
    incident_id: str,
    notification_reference: str,
    review_reference: str,
    correlation_id: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record immediate notification and independent-review obligations safely."""
    required = (
        event_id,
        actor_id,
        resource_type,
        action,
        purpose,
        incident_id,
        notification_reference,
        review_reference,
        correlation_id,
        created_at,
    )
    if any(not str(value).strip() for value in required):
        raise ValueError("complete break-glass evidence is required")
    common = {
        "actor_id": actor_id,
        "resource_type": resource_type,
        "action": action,
        "purpose": purpose,
        "reason_code": "incident_break_glass",
        "correlation_id": correlation_id,
        "created_at": created_at,
    }
    notification = append_authorization_event(
        stream_id,
        {
            **common,
            "event_id": f"{event_id}:notification",
            "event_type": "break_glass_notification_recorded",
            "target_id": incident_id,
            "evidence_reference": notification_reference,
        },
    )
    review = append_authorization_event(
        stream_id,
        {
            **common,
            "event_id": f"{event_id}:review",
            "event_type": "break_glass_review_required",
            "target_id": incident_id,
            "evidence_reference": review_reference,
        },
    )
    return notification, review
