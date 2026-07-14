"""Immutable teacher applications and conditional invitation activation commands."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class TeacherApplicationConflict(RuntimeError):
    """An immutable version or lifecycle transition already exists."""


def create_application_version(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "PK": f"TEACHER_APPLICATION#{item['application_id']}",
        "SK": f"VERSION#{int(item['version']):08d}",
        "entity_type": "teacher_application_version",
        **item,
    }
    _conditional_put(row)
    return row


def get_application_version(application_id: str, version: int) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={
            "PK": f"TEACHER_APPLICATION#{application_id}",
            "SK": f"VERSION#{int(version):08d}",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if item else None


def list_application_versions(application_id: str) -> list[dict[str, Any]]:
    response = get_table().query(
        KeyConditionExpression=(
            Key("PK").eq(f"TEACHER_APPLICATION#{application_id}")
            & Key("SK").begins_with("VERSION#")
        ),
        ConsistentRead=True,
    )
    return [dict(item) for item in response.get("Items", [])]


def create_review(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "PK": f"TEACHER_APPLICATION#{item['application_id']}",
        "SK": f"REVIEW#{int(item['version']):08d}",
        "entity_type": "teacher_application_review",
        **item,
    }
    _conditional_put(row)
    return row


def create_invitation(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "PK": f"TEACHER_INVITATION#{item['token_digest']}",
        "SK": "META",
        "entity_type": "teacher_activation_invitation",
        **item,
    }
    _conditional_put(row)
    return row


def get_invitation(token_digest: str) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={"PK": f"TEACHER_INVITATION#{token_digest}", "SK": "META"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if item else None


def claim_invitation(token_digest: str, *, command_id: str, consumed_at: str) -> bool:
    try:
        get_table().update_item(
            Key={"PK": f"TEACHER_INVITATION#{token_digest}", "SK": "META"},
            UpdateExpression=(
                "SET #status = :consumed, #command_id = :command_id, "
                "#consumed_at = :consumed_at, #version = :next_version"
            ),
            ConditionExpression="#status = :issued AND #version = :expected_version",
            ExpressionAttributeNames={
                "#status": "status",
                "#command_id": "command_id",
                "#consumed_at": "consumed_at",
                "#version": "version",
            },
            ExpressionAttributeValues={
                ":issued": "issued",
                ":consumed": "consumed",
                ":command_id": command_id,
                ":consumed_at": consumed_at,
                ":expected_version": 1,
                ":next_version": 2,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def create_activation_command(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "PK": f"TEACHER_ACTIVATION#{item['command_id']}",
        "SK": "COMMAND",
        "entity_type": "teacher_activation_command",
        **item,
    }
    try:
        _conditional_put(row)
    except TeacherApplicationConflict:
        existing = get_activation_command(item["command_id"])
        if existing:
            return existing
        raise
    return row


def get_activation_command(command_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(
        Key={"PK": f"TEACHER_ACTIVATION#{command_id}", "SK": "COMMAND"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return dict(item) if item else None


def update_activation_command(
    command_id: str,
    *,
    expected_version: int,
    status: str,
    updated_at: str,
    evidence_reference: str,
) -> dict[str, Any]:
    try:
        response = get_table().update_item(
            Key={"PK": f"TEACHER_ACTIVATION#{command_id}", "SK": "COMMAND"},
            UpdateExpression=(
                "SET #status = :status, #updated_at = :updated_at, "
                "#evidence_reference = :evidence_reference, #version = :next_version"
            ),
            ConditionExpression="#version = :expected_version",
            ExpressionAttributeNames={
                "#status": "status",
                "#updated_at": "updated_at",
                "#evidence_reference": "evidence_reference",
                "#version": "version",
            },
            ExpressionAttributeValues={
                ":status": status,
                ":updated_at": updated_at,
                ":evidence_reference": evidence_reference,
                ":expected_version": expected_version,
                ":next_version": expected_version + 1,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise TeacherApplicationConflict("stale activation command") from exc
        raise
    return dict(response.get("Attributes") or {})


def _conditional_put(row: dict[str, Any]) -> None:
    try:
        get_table().put_item(
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise TeacherApplicationConflict("immutable lifecycle row already exists") from exc
        raise
