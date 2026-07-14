"""Idempotent routine privileged-identity lifecycle commands."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class PrivilegedIdentityCommandConflict(RuntimeError):
    """A command identifier was reused for different input or from stale state."""


def create_command(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    row = {
        "PK": f"PRIVILEGED_IDENTITY_COMMAND#{item['command_id']}",
        "SK": "COMMAND",
        "entity_type": "privileged_identity_command",
        **item,
    }
    try:
        get_table().put_item(
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        existing = get_command(item["command_id"])
        immutable = ("operation", "target_id", "issuer", "subject", "reason", "approved_by")
        if existing and all(existing.get(key) == item.get(key) for key in immutable):
            return existing, False
        raise PrivilegedIdentityCommandConflict("command id conflicts with approved input") from exc
    return row, True


def get_command(command_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={"PK": f"PRIVILEGED_IDENTITY_COMMAND#{command_id}", "SK": "COMMAND"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if item else None


def update_command(
    command_id: str,
    *,
    expected_version: int,
    status: str,
    updated_at: str,
    evidence_reference: str,
) -> dict[str, Any]:
    try:
        response = get_table().update_item(
            Key={"PK": f"PRIVILEGED_IDENTITY_COMMAND#{command_id}", "SK": "COMMAND"},
            UpdateExpression=(
                "SET #status = :status, #updated_at = :updated_at, "
                "#evidence = :evidence, #version = :next_version"
            ),
            ConditionExpression="#version = :expected_version",
            ExpressionAttributeNames={
                "#status": "status",
                "#updated_at": "updated_at",
                "#evidence": "evidence_reference",
                "#version": "version",
            },
            ExpressionAttributeValues={
                ":status": status,
                ":updated_at": updated_at,
                ":evidence": evidence_reference,
                ":expected_version": expected_version,
                ":next_version": expected_version + 1,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise PrivilegedIdentityCommandConflict("stale privileged command") from exc
        raise
    return dict(response.get("Attributes") or {})
