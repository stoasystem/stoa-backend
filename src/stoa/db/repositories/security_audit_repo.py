"""Append-only, allowlisted security lifecycle evidence."""

from __future__ import annotations

from typing import Any, Mapping

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


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
