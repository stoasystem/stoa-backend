"""Authoritative versioned local capability grants.

Capability state is read consistently for every request.  Token claims, profiles,
roles, and metadata are deliberately outside this repository boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


TEACHER_IDENTITY_REVIEWER = "teacher_identity_reviewer"
ADMIN_IDENTITY_MANAGER = "admin_identity_manager"
STUDENT_SUPPORT_LOOKUP = "student_support_lookup"
STUDENT_CONTENT_REVIEW = "student_content_review"
STUDENT_SAFETY_REVIEW = "student_safety_review"
STUDENT_DATA_BREAK_GLASS = "student_data_break_glass"
CURRICULUM_AUTHOR = "curriculum_author"
CURRICULUM_REVIEWER = "curriculum_reviewer"
CURRICULUM_PUBLISHER = "curriculum_publisher"
MIGRATION_OPERATOR = "migration_operator"

KNOWN_CAPABILITIES = frozenset(
    {
        TEACHER_IDENTITY_REVIEWER,
        ADMIN_IDENTITY_MANAGER,
        STUDENT_SUPPORT_LOOKUP,
        STUDENT_CONTENT_REVIEW,
        STUDENT_SAFETY_REVIEW,
        STUDENT_DATA_BREAK_GLASS,
        CURRICULUM_AUTHOR,
        CURRICULUM_REVIEWER,
        CURRICULUM_PUBLISHER,
        MIGRATION_OPERATOR,
    }
)


class CapabilityVersionConflict(RuntimeError):
    """A capability transition was based on stale grant state."""


def _scope_key(scope: str) -> str:
    return sha256(scope.strip().encode("utf-8")).hexdigest()[:24]


def _grant_key(user_id: str, capability: str, scope: str, grant_id: str) -> dict[str, str]:
    return {
        "PK": f"USER#{user_id.strip()}",
        "SK": f"CAPABILITY#{capability.strip()}#{_scope_key(scope)}#{grant_id.strip()}",
    }


def grant_capability(
    *,
    user_id: str,
    grant_id: str,
    capability: str,
    scope: str,
    grantor_id: str,
    reason: str,
    effective_at: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Create one explicit grant. Reusing its identity is a conflict, never elevation."""
    values = [user_id, grant_id, capability, scope, grantor_id, reason, effective_at]
    if any(not str(value).strip() for value in values):
        raise ValueError("capability grant fields are required")
    if capability not in KNOWN_CAPABILITIES:
        raise ValueError("unknown capability")
    if capability == STUDENT_DATA_BREAK_GLASS and not expires_at:
        raise ValueError("break-glass grants must expire")
    row = {
        **_grant_key(user_id, capability, scope, grant_id),
        "entity_type": "capability_grant",
        "user_id": user_id,
        "grant_id": grant_id,
        "capability": capability,
        "scope": scope,
        "grantor_id": grantor_id,
        "reason": reason,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "status": "active",
        "version": 1,
        "updated_at": effective_at,
    }
    try:
        get_table().put_item(
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise CapabilityVersionConflict("capability grant already exists") from exc
        raise
    return row


def revoke_capability(**kwargs: Any) -> dict[str, Any]:
    return _transition(status="revoked", **kwargs)


def restore_capability(**kwargs: Any) -> dict[str, Any]:
    return _transition(status="active", **kwargs)


def _transition(
    *,
    user_id: str,
    grant_id: str,
    capability: str,
    scope: str,
    expected_version: int,
    actor_id: str,
    reason: str,
    changed_at: str,
    status: str,
) -> dict[str, Any]:
    if expected_version < 1 or not actor_id.strip() or not reason.strip():
        raise ValueError("expected_version, actor_id and reason are required")
    try:
        response = get_table().update_item(
            Key=_grant_key(user_id, capability, scope, grant_id),
            UpdateExpression=(
                "SET #status = :status, #version = :next_version, #updated_at = :changed_at, "
                "#updated_by = :actor_id, #transition_reason = :reason"
            ),
            ConditionExpression="#version = :expected_version",
            ExpressionAttributeNames={
                "#status": "status",
                "#version": "version",
                "#updated_at": "updated_at",
                "#updated_by": "updated_by",
                "#transition_reason": "transition_reason",
            },
            ExpressionAttributeValues={
                ":status": status,
                ":next_version": expected_version + 1,
                ":changed_at": changed_at,
                ":actor_id": actor_id,
                ":reason": reason,
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise CapabilityVersionConflict("stale capability grant version") from exc
        raise
    return dict(response.get("Attributes") or {})


def get_current_grants(
    user_id: str,
    *,
    now: datetime | None = None,
    table_factory: Callable[[], Any] = get_table,
) -> list[dict[str, Any]]:
    """Return only currently effective, non-expired grants using a consistent read."""
    response = table_factory().query(
        KeyConditionExpression=(
            Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("CAPABILITY#")
        ),
        ConsistentRead=True,
    )
    instant = now or datetime.now(UTC)
    current = []
    for raw in response.get("Items", []):
        item = dict(raw)
        if item.get("status") != "active" or int(item.get("version") or 0) < 1:
            continue
        if not item.get("capability") or not item.get("scope") or not item.get("grant_id"):
            continue
        effective = _parse_time(item.get("effective_at"))
        expires = _parse_time(item.get("expires_at"))
        if effective and effective > instant:
            continue
        if expires and expires <= instant:
            continue
        current.append(item)
    return current


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
