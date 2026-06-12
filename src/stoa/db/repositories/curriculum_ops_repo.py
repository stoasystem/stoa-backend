"""DynamoDB access patterns for internal curriculum authoring workflows."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


VERSION_ENTITY = "curriculum_version"
POINTER_ENTITY = "curriculum_pointer"
MANIFEST_ENTITY = "curriculum_publish_manifest"
AUDIT_ENTITY = "curriculum_audit_event"


class StalePointerError(RuntimeError):
    """Raised when a conditional publish/rollback pointer update loses a race."""


def put_version(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"CURRICULUM_VERSION#{item['public_id']}",
            "SK": f"VERSION#{item['version_id']}",
            "entity_type": VERSION_ENTITY,
            **item,
        }
    )


def get_version(public_id: str, version_id: str) -> dict[str, Any] | None:
    table = get_table()
    resp = table.get_item(
        Key={
            "PK": f"CURRICULUM_VERSION#{public_id}",
            "SK": f"VERSION#{version_id}",
        }
    )
    return resp.get("Item")


def get_pointer(public_id: str) -> dict[str, Any] | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"CURRICULUM_POINTER#{public_id}", "SK": "META"})
    return resp.get("Item")


def put_pointer(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"CURRICULUM_POINTER#{item['public_id']}",
            "SK": "META",
            "entity_type": POINTER_ENTITY,
            **item,
        }
    )


def set_published_pointer(
    *,
    public_id: str,
    version_id: str,
    manifest_id: str,
    expected_published_version_id: str | None,
    actor_id: str,
    updated_at: str,
) -> dict[str, Any]:
    table = get_table()
    names = {
        "#published_version_id": "published_version_id",
        "#manifest_id": "manifest_id",
        "#updated_at": "updated_at",
        "#updated_by": "updated_by",
        "#entity_type": "entity_type",
        "#public_id": "public_id",
    }
    values: dict[str, Any] = {
        ":version_id": version_id,
        ":manifest_id": manifest_id,
        ":updated_at": updated_at,
        ":updated_by": actor_id,
        ":entity_type": POINTER_ENTITY,
        ":public_id": public_id,
    }
    condition = "attribute_not_exists(#published_version_id)"
    if expected_published_version_id is not None:
        condition = "#published_version_id = :expected"
        values[":expected"] = expected_published_version_id
    try:
        resp = table.update_item(
            Key={"PK": f"CURRICULUM_POINTER#{public_id}", "SK": "META"},
            UpdateExpression=(
                "SET #entity_type = :entity_type, #public_id = :public_id, "
                "#published_version_id = :version_id, #manifest_id = :manifest_id, "
                "#updated_at = :updated_at, #updated_by = :updated_by"
            ),
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        error = exc.response.get("Error", {}).get("Code")
        if error == "ConditionalCheckFailedException":
            raise StalePointerError("Published pointer changed") from exc
        raise
    return resp.get("Attributes", {})


def put_manifest(item: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"CURRICULUM_MANIFEST#{item['public_id']}",
            "SK": f"MANIFEST#{item['manifest_id']}",
            "entity_type": MANIFEST_ENTITY,
            **item,
        }
    )


def put_published_projection(version: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Write the published practice projection consumed by current curriculum reads."""
    table = get_table()
    lesson = dict(version.get("lesson") or {})
    lesson["lesson_id"] = version["public_id"]
    lesson["status"] = "active"
    lesson["rollout_state"] = "active"
    lesson["version_id"] = version["version_id"]
    lesson["manifest_id"] = manifest["manifest_id"]
    table.put_item(Item={"PK": "PRACTICE", "SK": f"LESSON#{version['public_id']}", **lesson})

    for index, exercise in enumerate(version.get("exercises") or [], start=1):
        item = dict(exercise)
        exercise_id = str(item.get("exercise_id") or item.get("challenge_id"))
        item["challenge_id"] = exercise_id
        item["exercise_id"] = exercise_id
        item["lesson_id"] = version["public_id"]
        item["status"] = "active"
        item["rollout_state"] = "active"
        item["version_id"] = version["version_id"]
        item["manifest_id"] = manifest["manifest_id"]
        item["order"] = int(item.get("order") or index)
        table.put_item(
            Item={
                "PK": "PRACTICE",
                "SK": f"CHALLENGE#{version['public_id']}#{exercise_id}",
                **item,
            }
        )


def append_audit_event(public_id: str, event: dict[str, Any]) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"CURRICULUM_AUDIT#{public_id}",
            "SK": f"EVENT#{event['event_id']}",
            "entity_type": AUDIT_ENTITY,
            **event,
        }
    )


def list_audit_events(public_id: str, limit: int = 50) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"CURRICULUM_AUDIT#{public_id}") & Key("SK").begins_with("EVENT#")
        ),
        Limit=limit,
        ScanIndexForward=False,
    )
    return resp.get("Items", [])


def list_worklist(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    table = get_table()
    filter_expr = Attr("entity_type").eq(VERSION_ENTITY)
    if status:
        filter_expr = filter_expr & Attr("state").eq(status)
    resp = table.scan(FilterExpression=filter_expr, Limit=limit)
    return sorted(resp.get("Items", []), key=lambda item: item.get("updated_at", ""), reverse=True)


def list_active_assignment_refs(public_id: str, limit: int = 100) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.scan(
        FilterExpression=(
            Attr("entity_type").eq("learning_assignment")
            & Attr("lesson_id").eq(public_id)
            & Attr("status").is_in(["recommended", "assigned", "started"])
        ),
        Limit=limit,
    )
    return resp.get("Items", [])

