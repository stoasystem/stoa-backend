"""Conditional single-table persistence for upload intents and attachments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


@dataclass(frozen=True, slots=True)
class AttachmentRepositoryConflict(Exception):
    category: str = "conditional_conflict"


def upload_key(upload_id: str) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": "META"}


def attachment_key(attachment_id: str) -> dict[str, str]:
    return {"PK": f"ATTACHMENT#{attachment_id}", "SK": "META"}


def storage_key(owner_id: str) -> dict[str, str]:
    return {"PK": f"STORAGE#{owner_id}", "SK": "USAGE"}


def association_key(
    attachment_id: str, resource_type: str, resource_id: str, message_id: str
) -> dict[str, str]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": f"REF#{resource_type.upper()}#{resource_id}#MESSAGE#{message_id}",
    }


def create_upload_intent(item: dict[str, Any], *, table: Any | None = None) -> None:
    try:
        (table or get_table()).put_item(
            Item={**upload_key(item["upload_id"]), **item},
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        _translate(exc)


def get_upload_intent(upload_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(Key=upload_key(upload_id), ConsistentRead=True)
    return response.get("Item")


def get_attachment(attachment_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(
        Key=attachment_key(attachment_id), ConsistentRead=True
    )
    return response.get("Item")


def get_attachments(
    attachment_ids: list[str], *, table: Any | None = None
) -> dict[str, dict[str, Any]]:
    if not attachment_ids:
        return {}
    target = table or get_table()
    if hasattr(target, "batch_get_item"):
        response = target.batch_get_item(
            RequestItems={target.name: {"Keys": [attachment_key(value) for value in attachment_ids]}}
        )
        items = response.get("Responses", {}).get(target.name, [])
    elif hasattr(target, "meta") and hasattr(target.meta, "client"):
        serializer = TypeSerializer()
        response = target.meta.client.batch_get_item(
            RequestItems={
                target.name: {
                    "Keys": [
                        {key: serializer.serialize(value) for key, value in attachment_key(item).items()}
                        for item in attachment_ids
                    ]
                }
            }
        )
        deserializer = TypeDeserializer()
        items = [
            {key: deserializer.deserialize(value) for key, value in item.items()}
            for item in response.get("Responses", {}).get(target.name, [])
        ]
    else:
        items = [item for value in attachment_ids if (item := get_attachment(value, table=target))]
    return {str(item.get("attachment_id")): item for item in items if item.get("attachment_id")}


def build_message_attachment_transaction(
    *,
    message: dict[str, Any],
    fresh: list[tuple[dict[str, Any], dict[str, Any]]],
    reused: list[dict[str, Any]],
    associations: list[dict[str, Any]],
    owner_id: str,
    limit_bytes: int,
    now_iso: str,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = [
        {
            "Put": {
                "Item": message,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }
    ]
    for upload, attachment in fresh:
        operations.extend(
            [
                {
                    "Update": {
                        "Key": upload_key(upload["upload_id"]),
                        "UpdateExpression": "SET #s=:consumed, #v=#v+:one",
                        "ConditionExpression": (
                            "#owner=:owner AND #s=:validated AND #v=:version "
                            "AND expires_at>:now"
                        ),
                        "ExpressionAttributeNames": {
                            "#owner": "owner_id",
                            "#s": "status",
                            "#v": "version",
                        },
                        "ExpressionAttributeValues": {
                            ":owner": owner_id,
                            ":validated": "validated",
                            ":consumed": "consumed",
                            ":version": int(upload["version"]),
                            ":one": 1,
                            ":now": int(upload["consume_epoch"]),
                        },
                    }
                },
                {
                    "Put": {
                        "Item": {**attachment_key(attachment["attachment_id"]), **attachment},
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
            ]
        )
    for attachment in reused:
        operations.append(
            {
                "ConditionCheck": {
                    "Key": attachment_key(attachment["attachment_id"]),
                    "ConditionExpression": "owner_id=:owner AND #status=:active",
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {":owner": owner_id, ":active": "active"},
                }
            }
        )
    operations.extend(
        {
            "Put": {
                "Item": association,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }
        for association in associations
    )
    fresh_bytes = sum(int(attachment["content_length"]) for _, attachment in fresh)
    if fresh_bytes:
        operations.append(
            {
                "Update": {
                    "Key": storage_key(owner_id),
                    "UpdateExpression": (
                        "SET used_bytes=if_not_exists(used_bytes,:zero)+:size, "
                        "limit_bytes=:limit, updated_at=:updated"
                    ),
                    "ConditionExpression": (
                        "attribute_not_exists(used_bytes) OR used_bytes+:size<=:limit"
                    ),
                    "ExpressionAttributeValues": {
                        ":zero": 0,
                        ":size": fresh_bytes,
                        ":limit": limit_bytes,
                        ":updated": now_iso,
                    },
                }
            }
        )
    return operations


def get_storage_usage(owner_id: str, *, table: Any | None = None) -> int:
    response = (table or get_table()).get_item(Key=storage_key(owner_id), ConsistentRead=True)
    return int((response.get("Item") or {}).get("used_bytes", 0))


def begin_validation(
    upload_id: str, owner_id: str, version: int, now_epoch: int, *, table: Any | None = None
) -> bool:
    return _transition(
        upload_id, owner_id, "pending_upload", "validating", version, now_epoch, table=table
    )


def mark_validated(
    upload_id: str,
    owner_id: str,
    version: int,
    detected: dict[str, Any],
    *,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "validating",
        "validated",
        version,
        None,
        attributes=detected,
        table=table,
    )


def mark_invalid(
    upload_id: str, owner_id: str, version: int, failure_category: str, *, table: Any | None = None
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "validating",
        "invalid",
        version,
        None,
        attributes={"validation_failure": failure_category},
        table=table,
    )


def release_validation(
    upload_id: str, owner_id: str, version: int, now_epoch: int, *, table: Any | None = None
) -> bool:
    return _transition(
        upload_id, owner_id, "validating", "pending_upload", version, now_epoch, table=table
    )


def _transition(
    upload_id: str,
    owner_id: str,
    source: str,
    target: str,
    version: int,
    now_epoch: int | None,
    *,
    attributes: dict[str, Any] | None = None,
    table: Any | None = None,
) -> bool:
    names = {"#owner": "owner_id", "#status": "status", "#version": "version"}
    values: dict[str, Any] = {
        ":owner": owner_id,
        ":source": source,
        ":target": target,
        ":version": version,
        ":next": version + 1,
        ":one": 1,
    }
    condition = "#owner = :owner AND #status = :source AND #version = :version"
    if now_epoch is not None:
        names["#expiry"] = "expires_at"
        values[":now"] = now_epoch
        condition += " AND #expiry > :now"
    update = "SET #status = :target, #version = :next"
    for index, (name, value) in enumerate((attributes or {}).items()):
        names[f"#a{index}"] = name
        values[f":a{index}"] = value
        update += f", #a{index} = :a{index}"
    try:
        (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=update,
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def build_first_attachment_transaction(
    *,
    upload: dict[str, Any],
    attachment: dict[str, Any],
    association: dict[str, Any],
    limit_bytes: int,
    now_iso: str,
) -> list[dict[str, Any]]:
    size = int(attachment["content_length"])
    return [
        {
            "Update": {
                "Key": upload_key(upload["upload_id"]),
                "UpdateExpression": "SET #s=:consumed, #v=#v+:one",
                "ConditionExpression": "#owner=:owner AND #s=:validated AND #v=:version AND expires_at>:now",
                "ExpressionAttributeNames": {"#owner": "owner_id", "#s": "status", "#v": "version"},
                "ExpressionAttributeValues": {
                    ":owner": upload["owner_id"],
                    ":validated": "validated",
                    ":consumed": "consumed",
                    ":version": upload["version"],
                    ":one": 1,
                    ":now": upload.get("consume_epoch", 0),
                },
            }
        },
        {
            "Put": {
                "Item": {**attachment_key(attachment["attachment_id"]), **attachment},
                "ConditionExpression": "attribute_not_exists(PK)",
            }
        },
        {
            "Put": {
                "Item": association,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
        {
            "Update": {
                "Key": storage_key(upload["owner_id"]),
                "UpdateExpression": "SET used_bytes=if_not_exists(used_bytes,:zero)+:size, limit_bytes=:limit, updated_at=:updated",
                "ConditionExpression": "attribute_not_exists(used_bytes) OR used_bytes+:size<=:limit",
                "ExpressionAttributeValues": {
                    ":zero": 0,
                    ":size": size,
                    ":limit": limit_bytes,
                    ":updated": now_iso,
                },
            }
        },
    ]


def build_reuse_transaction(
    *, attachment: dict[str, Any], association: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "ConditionCheck": {
                "Key": attachment_key(attachment["attachment_id"]),
                "ConditionExpression": "owner_id=:owner AND #status=:active",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": attachment["owner_id"],
                    ":active": "active",
                },
            }
        },
        {
            "Put": {
                "Item": association,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
    ]


def transact(operations: list[dict[str, Any]], *, table: Any | None = None) -> None:
    target = table or get_table()
    try:
        if hasattr(target, "transact_write_items"):
            target.transact_write_items(TransactItems=operations)
        else:
            target.meta.client.transact_write_items(
                TransactItems=_serialize_transactions(operations, target.name)
            )
    except ClientError as exc:
        if _conditional(exc):
            raise AttachmentRepositoryConflict() from None
        raise AttachmentRepositoryConflict("dependency_failure") from None


def _conditional(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in {
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
    }


def _serialize_transactions(
    operations: list[dict[str, Any]], table_name: str
) -> list[dict[str, Any]]:
    serializer = TypeSerializer()
    result: list[dict[str, Any]] = []
    for operation in operations:
        operation_name, value = next(iter(operation.items()))
        encoded: dict[str, Any] = {"TableName": table_name}
        if "Key" in value:
            encoded["Key"] = {key: serializer.serialize(item) for key, item in value["Key"].items()}
        if "Item" in value:
            encoded["Item"] = {
                key: serializer.serialize(item)
                for key, item in value["Item"].items()
                if item is not None
            }
        for key in (
            "UpdateExpression",
            "ConditionExpression",
            "ExpressionAttributeNames",
        ):
            if key in value:
                encoded[key] = value[key]
        if "ExpressionAttributeValues" in value:
            encoded["ExpressionAttributeValues"] = {
                key: serializer.serialize(item)
                for key, item in value["ExpressionAttributeValues"].items()
            }
        result.append({operation_name: encoded})
    return result


def _translate(exc: ClientError) -> None:
    raise AttachmentRepositoryConflict(
        "conditional_conflict" if _conditional(exc) else "dependency_failure"
    ) from None
