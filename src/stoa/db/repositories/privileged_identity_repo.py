"""Idempotent routine privileged-identity lifecycle commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


class PrivilegedIdentityCommandConflict(RuntimeError):
    """A command identifier was reused for different input or from stale state."""


type PrivilegedIdentityCommand = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _mapping(value: object) -> PrivilegedIdentityCommand:
    if not isinstance(value, Mapping):
        raise PrivilegedIdentityCommandConflict(
            "malformed privileged identity dependency response"
        )
    item: PrivilegedIdentityCommand = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise PrivilegedIdentityCommandConflict(
                "malformed privileged identity dependency response"
            )
        item[key] = member
    return item


def _required_command_id(item: Mapping[str, object]) -> str:
    value = item.get("command_id")
    if not isinstance(value, str) or not value.strip():
        raise PrivilegedIdentityCommandConflict("invalid privileged identity command")
    return value


def _get_item(table: object, **kwargs: object) -> PrivilegedIdentityCommand:
    if not isinstance(table, _GetTable):
        raise PrivilegedIdentityCommandConflict("privileged identity dependency unavailable")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise PrivilegedIdentityCommandConflict("privileged identity dependency unavailable")
    return table.put_item(**kwargs)


def _update_item(table: object, **kwargs: object) -> PrivilegedIdentityCommand:
    if not isinstance(table, _UpdateTable):
        raise PrivilegedIdentityCommandConflict("privileged identity dependency unavailable")
    return _mapping(table.update_item(**kwargs))


def create_command(
    item: PrivilegedIdentityCommand,
) -> tuple[PrivilegedIdentityCommand, bool]:
    command_id = _required_command_id(item)
    row = {
        "PK": f"PRIVILEGED_IDENTITY_COMMAND#{command_id}",
        "SK": "COMMAND",
        "entity_type": "privileged_identity_command",
        **item,
    }
    try:
        _put_item(
            get_table(),
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        existing = get_command(command_id)
        immutable = ("operation", "target_id", "issuer", "subject", "reason", "approved_by")
        if existing and all(existing.get(key) == item.get(key) for key in immutable):
            return existing, False
        raise PrivilegedIdentityCommandConflict("command id conflicts with approved input") from exc
    return row, True


def get_command(command_id: str) -> PrivilegedIdentityCommand | None:
    response = _get_item(
        get_table(),
        Key={"PK": f"PRIVILEGED_IDENTITY_COMMAND#{command_id}", "SK": "COMMAND"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if item is None:
        return None
    existing = _mapping(item)
    return existing or None


def update_command(
    command_id: str,
    *,
    expected_version: int,
    status: str,
    updated_at: str,
    evidence_reference: str,
) -> PrivilegedIdentityCommand:
    try:
        response = _update_item(
            get_table(),
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
    attributes = response.get("Attributes")
    return {} if attributes is None else _mapping(attributes)
