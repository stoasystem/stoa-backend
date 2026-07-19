"""DynamoDB access patterns for internal curriculum authoring workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, SupportsInt, runtime_checkable

from boto3.dynamodb.conditions import Attr, ConditionBase, Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


VERSION_ENTITY = "curriculum_version"
POINTER_ENTITY = "curriculum_pointer"
MANIFEST_ENTITY = "curriculum_publish_manifest"
AUDIT_ENTITY = "curriculum_audit_event"
MIGRATION_ENTITY = "curriculum_migration_evidence"


type CurriculumItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


class StalePointerError(RuntimeError):
    """Raised when a conditional publish/rollback pointer update loses a race."""


def _mapping(value: object) -> CurriculumItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("curriculum dependency unavailable")
    item: CurriculumItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("curriculum dependency unavailable")
        item[key] = member
    return item


def _get_item(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _GetTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise RuntimeError("curriculum dependency unavailable")
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _QueryTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.query(**kwargs))


def _scan(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _ScanTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.scan(**kwargs))


def _update_item(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _UpdateTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.update_item(**kwargs))


def _items(value: object) -> list[CurriculumItem]:
    if not isinstance(value, list):
        raise RuntimeError("curriculum dependency unavailable")
    return [_mapping(item) for item in value]


def _integer(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray, SupportsInt)):
        return int(value)
    raise RuntimeError("curriculum dependency unavailable")


def put_version(item: CurriculumItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_VERSION#{item['public_id']}",
            "SK": f"VERSION#{item['version_id']}",
            "entity_type": VERSION_ENTITY,
            **item,
        },
    )


def get_version(public_id: str, version_id: str) -> CurriculumItem | None:
    table = get_table()
    resp = _get_item(
        table,
        Key={
            "PK": f"CURRICULUM_VERSION#{public_id}",
            "SK": f"VERSION#{version_id}",
        },
    )
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def get_pointer(public_id: str) -> CurriculumItem | None:
    table = get_table()
    resp = _get_item(table, Key={"PK": f"CURRICULUM_POINTER#{public_id}", "SK": "META"})
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def put_pointer(item: CurriculumItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_POINTER#{item['public_id']}",
            "SK": "META",
            "entity_type": POINTER_ENTITY,
            **item,
        },
    )


def set_published_pointer(
    *,
    public_id: str,
    version_id: str,
    manifest_id: str,
    expected_published_version_id: str | None,
    actor_id: str,
    updated_at: str,
) -> CurriculumItem:
    table = get_table()
    names = {
        "#published_version_id": "published_version_id",
        "#manifest_id": "manifest_id",
        "#updated_at": "updated_at",
        "#updated_by": "updated_by",
        "#entity_type": "entity_type",
        "#public_id": "public_id",
    }
    values: CurriculumItem = {
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
        resp = _update_item(
            table,
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
    return _mapping(resp.get("Attributes", {}))


def put_manifest(item: CurriculumItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_MANIFEST#{item['public_id']}",
            "SK": f"MANIFEST#{item['manifest_id']}",
            "entity_type": MANIFEST_ENTITY,
            **item,
        },
    )


def put_migration_evidence(item: CurriculumItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_MIGRATION#{item['migration_id']}",
            "SK": "EVIDENCE",
            "entity_type": MIGRATION_ENTITY,
            **item,
        },
    )


def get_migration_evidence(migration_id: str) -> CurriculumItem | None:
    table = get_table()
    resp = _get_item(
        table,
        Key={
            "PK": f"CURRICULUM_MIGRATION#{migration_id}",
            "SK": "EVIDENCE",
        },
    )
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def put_published_projection(version: CurriculumItem, manifest: CurriculumItem) -> None:
    """Write the published practice projection consumed by current curriculum reads."""
    table = get_table()
    raw_lesson = version.get("lesson")
    lesson = {} if raw_lesson is None else _mapping(raw_lesson)
    lesson["lesson_id"] = version["public_id"]
    lesson["status"] = "active"
    lesson["rollout_state"] = "active"
    lesson["version_id"] = version["version_id"]
    lesson["manifest_id"] = manifest["manifest_id"]
    _put_item(
        table,
        Item={"PK": "PRACTICE", "SK": f"LESSON#{version['public_id']}", **lesson},
    )

    raw_exercises = version.get("exercises")
    if raw_exercises is None:
        exercises: list[object] = []
    elif isinstance(raw_exercises, list):
        exercises = raw_exercises
    else:
        raise RuntimeError("curriculum dependency unavailable")
    for index, exercise in enumerate(exercises, start=1):
        item = _mapping(exercise)
        exercise_id = str(item.get("exercise_id") or item.get("challenge_id"))
        item["challenge_id"] = exercise_id
        item["exercise_id"] = exercise_id
        item["lesson_id"] = version["public_id"]
        item["status"] = "active"
        item["rollout_state"] = "active"
        item["version_id"] = version["version_id"]
        item["manifest_id"] = manifest["manifest_id"]
        item["order"] = _integer(item.get("order") or index)
        _put_item(
            table,
            Item={
                "PK": "PRACTICE",
                "SK": f"CHALLENGE#{version['public_id']}#{exercise_id}",
                **item,
            },
        )


def append_audit_event(public_id: str, event: CurriculumItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_AUDIT#{public_id}",
            "SK": f"EVENT#{event['event_id']}",
            "entity_type": AUDIT_ENTITY,
            **event,
        },
    )


def list_audit_events(public_id: str, limit: int = 50) -> list[CurriculumItem]:
    table = get_table()
    resp = _query(
        table,
        KeyConditionExpression=(
            Key("PK").eq(f"CURRICULUM_AUDIT#{public_id}") & Key("SK").begins_with("EVENT#")
        ),
        Limit=limit,
        ScanIndexForward=False,
    )
    return _items(resp.get("Items", []))


def list_worklist(status: str | None = None, limit: int = 100) -> list[CurriculumItem]:
    table = get_table()
    filter_expr: ConditionBase = Attr("entity_type").eq(VERSION_ENTITY)
    if status:
        filter_expr = filter_expr & Attr("state").eq(status)
    resp = _scan(table, FilterExpression=filter_expr, Limit=limit)
    items = _items(resp.get("Items", []))
    return sorted(items, key=lambda item: str(item.get("updated_at", "")), reverse=True)


def list_active_assignment_refs(public_id: str, limit: int = 100) -> list[CurriculumItem]:
    table = get_table()
    resp = _scan(
        table,
        FilterExpression=(
            Attr("entity_type").eq("learning_assignment")
            & Attr("lesson_id").eq(public_id)
            & Attr("status").is_in(["recommended", "assigned", "started"])
        ),
        Limit=limit,
    )
    return _items(resp.get("Items", []))
