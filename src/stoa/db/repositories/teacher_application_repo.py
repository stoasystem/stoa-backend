"""Immutable teacher applications and conditional invitation activation commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class TeacherApplicationConflict(RuntimeError):
    """An immutable version or lifecycle transition already exists."""


type TeacherApplicationItem = dict[str, object]


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
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _mapping(value: object) -> TeacherApplicationItem:
    if not isinstance(value, Mapping):
        raise TeacherApplicationConflict("malformed teacher application dependency response")
    item: TeacherApplicationItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise TeacherApplicationConflict(
                "malformed teacher application dependency response"
            )
        item[key] = member
    return item


def _required_text(item: Mapping[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TeacherApplicationConflict("invalid teacher application input")
    return value


def _required_version(item: Mapping[str, object]) -> int:
    value = item.get("version")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TeacherApplicationConflict("invalid teacher application input")
    return value


def _get_item(table: object, **kwargs: object) -> TeacherApplicationItem:
    if not isinstance(table, _GetTable):
        raise TeacherApplicationConflict("teacher application dependency unavailable")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise TeacherApplicationConflict("teacher application dependency unavailable")
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> TeacherApplicationItem:
    if not isinstance(table, _QueryTable):
        raise TeacherApplicationConflict("teacher application dependency unavailable")
    return _mapping(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> TeacherApplicationItem:
    if not isinstance(table, _UpdateTable):
        raise TeacherApplicationConflict("teacher application dependency unavailable")
    return _mapping(table.update_item(**kwargs))


def _optional_item(value: object) -> TeacherApplicationItem | None:
    if value is None:
        return None
    item = _mapping(value)
    return item or None


def create_application_version(item: TeacherApplicationItem) -> TeacherApplicationItem:
    application_id = _required_text(item, "application_id")
    version = _required_version(item)
    row = {
        "PK": f"TEACHER_APPLICATION#{application_id}",
        "SK": f"VERSION#{version:08d}",
        "entity_type": "teacher_application_version",
        **item,
    }
    _conditional_put(row)
    return row


def get_application_version(
    application_id: str, version: int
) -> TeacherApplicationItem | None:
    response = _get_item(
        get_table(),
        Key={
            "PK": f"TEACHER_APPLICATION#{application_id}",
            "SK": f"VERSION#{int(version):08d}",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _optional_item(item)


def list_application_versions(application_id: str) -> list[TeacherApplicationItem]:
    response = _query(
        get_table(),
        KeyConditionExpression=(
            Key("PK").eq(f"TEACHER_APPLICATION#{application_id}")
            & Key("SK").begins_with("VERSION#")
        ),
        ConsistentRead=True,
    )
    items = response.get("Items", [])
    if not isinstance(items, list):
        raise TeacherApplicationConflict("malformed teacher application dependency response")
    return [_mapping(item) for item in items]


def create_review(item: TeacherApplicationItem) -> TeacherApplicationItem:
    application_id = _required_text(item, "application_id")
    version = _required_version(item)
    row = {
        "PK": f"TEACHER_APPLICATION#{application_id}",
        "SK": f"REVIEW#{version:08d}",
        "entity_type": "teacher_application_review",
        **item,
    }
    _conditional_put(row)
    return row


def create_invitation(item: TeacherApplicationItem) -> TeacherApplicationItem:
    token_digest = _required_text(item, "token_digest")
    row = {
        "PK": f"TEACHER_INVITATION#{token_digest}",
        "SK": "META",
        "entity_type": "teacher_activation_invitation",
        **item,
    }
    _conditional_put(row)
    return row


def get_invitation(token_digest: str) -> TeacherApplicationItem | None:
    response = _get_item(
        get_table(),
        Key={"PK": f"TEACHER_INVITATION#{token_digest}", "SK": "META"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _optional_item(item)


def claim_invitation(token_digest: str, *, command_id: str, consumed_at: str) -> bool:
    try:
        _update_item(
            get_table(),
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


def create_activation_command(item: TeacherApplicationItem) -> TeacherApplicationItem:
    command_id = _required_text(item, "command_id")
    row = {
        "PK": f"TEACHER_ACTIVATION#{command_id}",
        "SK": "COMMAND",
        "entity_type": "teacher_activation_command",
        **item,
    }
    try:
        _conditional_put(row)
    except TeacherApplicationConflict:
        existing = get_activation_command(command_id)
        if existing:
            return existing
        raise
    return row


def get_activation_command(command_id: str) -> TeacherApplicationItem | None:
    response = _get_item(
        get_table(),
        Key={"PK": f"TEACHER_ACTIVATION#{command_id}", "SK": "COMMAND"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _optional_item(item)


def update_activation_command(
    command_id: str,
    *,
    expected_version: int,
    status: str,
    updated_at: str,
    evidence_reference: str,
) -> TeacherApplicationItem:
    try:
        response = _update_item(
            get_table(),
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
    attributes = response.get("Attributes")
    return {} if attributes is None else _mapping(attributes)


def _conditional_put(row: TeacherApplicationItem) -> None:
    try:
        _put_item(
            get_table(),
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise TeacherApplicationConflict("immutable lifecycle row already exists") from exc
        raise
