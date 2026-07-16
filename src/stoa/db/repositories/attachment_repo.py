"""Conditional single-table persistence for upload intents and attachments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from stoa.db.dynamodb import get_table


@dataclass(frozen=True, slots=True)
class AttachmentRepositoryConflict(Exception):
    category: str = "conditional_conflict"


class AttachmentTransactionOutcome(StrEnum):
    """Closed, provider-independent result of an attachment transaction."""

    CONCEALED_RESOURCE_CONFLICT = "concealed_resource_conflict"
    QUOTA_EXCEEDED = "quota_exceeded"
    RETRYABLE_DEPENDENCY = "retryable_dependency"


class TransactionOperationKind(StrEnum):
    """Semantic transaction positions; never derived from provider diagnostics."""

    MESSAGE_PUT = "message_put"
    UPLOAD_CONSUME = "upload_consume"
    ATTACHMENT_PUT = "attachment_put"
    ATTACHMENT_REF = "attachment_ref"
    ASSOCIATION_PUT = "association_put"
    STORAGE_QUOTA_UPDATE = "storage_quota_update"
    QUESTION_PUT = "question_put"


@dataclass(frozen=True, slots=True)
class TransactionOperation:
    kind: TransactionOperationKind
    item: dict[str, Any]

    def __contains__(self, key: object) -> bool:
        return key in self.item

    def __getitem__(self, key: str) -> Any:
        return self.item[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.item.get(key, default)


@dataclass(frozen=True, slots=True)
class AttachmentTransactionError(Exception):
    outcome: AttachmentTransactionOutcome


def upload_key(upload_id: str) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": "META"}


def upload_part_key(upload_id: str, part_number: int) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": f"PART#{part_number:06d}"}


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


def question_association_key(attachment_id: str, question_id: str) -> dict[str, str]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": f"REF#QUESTION#{question_id}",
    }


def create_upload_intent(item: dict[str, Any], *, table: Any | None = None) -> None:
    try:
        (table or get_table()).put_item(
            Item={**upload_key(item["upload_id"]), **item},
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        _translate(exc)


def mark_upload_issued(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    staging_object_key: str,
    multipart_upload_id: str,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "issuing",
        "pending_upload",
        version,
        None,
        attributes={
            "staging_object_key": staging_object_key,
            "multipart_upload_id": multipart_upload_id,
        },
        table=table,
    )


def mark_upload_issuance_failed(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    cleanup_pending: bool = False,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "issuing",
        "cleanup_pending" if cleanup_pending else "invalid",
        version,
        None,
        attributes={"validation_failure": "service_unavailable"},
        table=table,
    )


def get_upload_part(
    upload_id: str, part_number: int, *, table: Any | None = None
) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(
        Key=upload_part_key(upload_id, part_number), ConsistentRead=True
    )
    return response.get("Item")


def claim_upload_part(
    upload_id: str,
    part_number: int,
    checksum_sha256: str,
    length: int,
    lease_owner: str,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    """Claim before provider mutation; one expired takeover is the only retry fence."""
    target = table or get_table()
    item = {
        **upload_part_key(upload_id, part_number),
        "upload_id": upload_id,
        "part_number": part_number,
        "status": "uploading",
        "checksum_sha256": checksum_sha256,
        "content_length": length,
        "lease_owner": lease_owner,
        "lease_expires_at": now_epoch + 120,
        "attempt": 1,
    }
    try:
        target.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        return item
    except ClientError as exc:
        if not _conditional(exc):
            raise AttachmentRepositoryConflict("dependency_failure") from None
    current = get_upload_part(upload_id, part_number, table=target)
    if not current:
        raise AttachmentRepositoryConflict("dependency_failure")
    if (
        current.get("checksum_sha256") != checksum_sha256
        or int(current.get("content_length", -1)) != length
    ):
        raise AttachmentRepositoryConflict("chunk_conflict")
    if current.get("status") == "completed" or int(current.get("lease_expires_at", 0)) > now_epoch:
        return current
    if int(current.get("attempt", 1)) >= 2:
        raise AttachmentRepositoryConflict("lease_exhausted")
    try:
        response = target.update_item(
            Key=upload_part_key(upload_id, part_number),
            UpdateExpression=("SET lease_owner=:owner, lease_expires_at=:expiry, attempt=:attempt"),
            ConditionExpression=(
                "#status=:uploading AND checksum_sha256=:checksum AND "
                "content_length=:length AND lease_expires_at<=:now AND attempt=:previous"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":uploading": "uploading",
                ":checksum": checksum_sha256,
                ":length": length,
                ":now": now_epoch,
                ":previous": 1,
                ":owner": lease_owner,
                ":expiry": now_epoch + 120,
                ":attempt": 2,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if _conditional(exc):
            return get_upload_part(upload_id, part_number, table=target) or current
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return response.get("Attributes") or {**current, "lease_owner": lease_owner, "attempt": 2}


def complete_upload_part(
    upload_id: str,
    part_number: int,
    lease_owner: str,
    *,
    provider_etag: str,
    provider_checksum: str,
    table: Any | None = None,
) -> bool:
    try:
        (table or get_table()).update_item(
            Key=upload_part_key(upload_id, part_number),
            UpdateExpression=(
                "SET #status=:completed, provider_etag=:etag, "
                "provider_checksum=:provider_checksum REMOVE lease_expires_at"
            ),
            ConditionExpression="#status=:uploading AND lease_owner=:owner",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":uploading": "uploading",
                ":completed": "completed",
                ":owner": lease_owner,
                ":etag": provider_etag,
                ":provider_checksum": provider_checksum,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def list_upload_parts(upload_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    response = (table or get_table()).query(
        KeyConditionExpression=Key("PK").eq(f"UPLOAD#{upload_id}") & Key("SK").begins_with("PART#"),
        ConsistentRead=True,
    )
    return sorted(response.get("Items", []), key=lambda item: int(item["part_number"]))


def begin_upload_assembly(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "pending_upload",
        "assembling",
        version,
        now_epoch,
        table=table,
    )


def mark_staging_completed(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    staging_version_id: str,
    staging_etag: str,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "assembling",
        "validating",
        version,
        None,
        attributes={
            "staging_version_id": staging_version_id,
            "staging_etag": staging_etag,
        },
        table=table,
    )


def mark_upload_terminal(
    upload_id: str,
    owner_id: str,
    version: int,
    failure_category: str,
    *,
    table: Any | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return _transition(
        upload_id,
        owner_id,
        str(item.get("status")),
        "cleanup_pending",
        version,
        None,
        attributes={"validation_failure": failure_category},
        table=table,
    )


def get_upload_intent(upload_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(Key=upload_key(upload_id), ConsistentRead=True)
    return response.get("Item")


def list_upload_cleanup_candidates(
    now_epoch: int,
    *,
    limit: int,
    exclusive_start_key: dict[str, Any] | None = None,
    table: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return one bounded page of terminal or expired unconsumed upload intents."""
    scan: dict[str, Any] = {
        "Limit": limit,
        "FilterExpression": (
            "begins_with(PK,:upload) AND SK=:meta AND ("
            "#status IN (:invalid,:expired,:cleanup_pending) OR ("
            "#status IN (:pending,:validating,:validated) AND expires_at<=:now))"
        ),
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":upload": "UPLOAD#",
            ":meta": "META",
            ":invalid": "invalid",
            ":expired": "expired",
            ":cleanup_pending": "cleanup_pending",
            ":pending": "pending_upload",
            ":validating": "validating",
            ":validated": "validated",
            ":now": now_epoch,
        },
    }
    if exclusive_start_key:
        scan["ExclusiveStartKey"] = exclusive_start_key
    response = (table or get_table()).scan(**scan)
    return list(response.get("Items", [])), response.get("LastEvaluatedKey")


def claim_upload_cleanup(
    upload_id: str,
    version: int,
    now_epoch: int,
    reason: str,
    *,
    table: Any | None = None,
) -> dict[str, Any] | None:
    """Conditionally make one eligible intent non-consumable for cleanup."""
    try:
        response = (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=(
                "SET #status=:cleanup_pending, #version=:next, cleanup_reason=:reason"
            ),
            ConditionExpression=(
                "#version=:version AND ("
                "#status IN (:invalid,:expired,:cleanup_pending) OR ("
                "#status IN (:pending,:validating,:validated) AND expires_at<=:now))"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":version": version,
                ":next": version + 1,
                ":invalid": "invalid",
                ":expired": "expired",
                ":cleanup_pending": "cleanup_pending",
                ":pending": "pending_upload",
                ":validating": "validating",
                ":validated": "validated",
                ":now": now_epoch,
                ":reason": reason,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if _conditional(exc):
            return None
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return response.get("Attributes")


def scan_durable_upload_references(
    upload_id: str,
    immutable_object_key: str = "",
    immutable_version_id: str = "",
    *,
    limit: int,
    exclusive_start_key: dict[str, Any] | None = None,
    table: Any | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Scan one bounded page for a durable attachment referencing upload bytes."""
    scan: dict[str, Any] = {
        "Limit": limit,
        "FilterExpression": (
            "begins_with(PK,:attachment) AND SK=:meta AND "
            "(source_upload_id=:upload_id OR "
            "(immutable_object_key=:immutable_key AND immutable_version_id=:immutable_version))"
        ),
        "ExpressionAttributeValues": {
            ":attachment": "ATTACHMENT#",
            ":meta": "META",
            ":upload_id": upload_id,
            ":immutable_key": immutable_object_key,
            ":immutable_version": immutable_version_id,
        },
    }
    if exclusive_start_key:
        scan["ExclusiveStartKey"] = exclusive_start_key
    response = (table or get_table()).scan(**scan)
    return bool(response.get("Items")), response.get("LastEvaluatedKey")


def advance_upload_cleanup_reference_scan(
    upload_id: str,
    version: int,
    cursor: dict[str, Any],
    *,
    table: Any | None = None,
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_reference_cursor=:cursor, #version=:next",
        {":cursor": cursor, ":next": version + 1},
        table=table,
    )


def block_upload_cleanup(upload_id: str, version: int, *, table: Any | None = None) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET #status=:blocked, #version=:next REMOVE cleanup_reference_cursor",
        {":blocked": "cleanup_blocked", ":next": version + 1},
        table=table,
    )


def complete_upload_cleanup(
    upload_id: str,
    version: int,
    cleaned_at: str,
    *,
    table: Any | None = None,
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        (
            "SET #status=:complete, #version=:next, cleaned_at=:cleaned_at "
            "REMOVE staging_object_key, staging_version_id, staging_etag, "
            "multipart_upload_id, cleanup_reference_cursor"
        ),
        {":complete": "cleanup_complete", ":next": version + 1, ":cleaned_at": cleaned_at},
        table=table,
    )


def _cleanup_update(
    upload_id: str,
    version: int,
    update_expression: str,
    values: dict[str, Any],
    *,
    table: Any | None,
) -> bool:
    try:
        (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=update_expression,
            ConditionExpression="#status=:pending AND #version=:version",
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                **values,
                ":pending": "cleanup_pending",
                ":version": version,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


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
            RequestItems={
                target.name: {"Keys": [attachment_key(value) for value in attachment_ids]}
            }
        )
        items = response.get("Responses", {}).get(target.name, [])
    elif hasattr(target, "meta") and hasattr(target.meta, "client"):
        serializer = TypeSerializer()
        response = target.meta.client.batch_get_item(
            RequestItems={
                target.name: {
                    "Keys": [
                        {
                            key: serializer.serialize(value)
                            for key, value in attachment_key(item).items()
                        }
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
) -> list[TransactionOperation]:
    operations: list[TransactionOperation] = [
        TransactionOperation(
            TransactionOperationKind.MESSAGE_PUT,
            {
                "Put": {
                    "Item": message,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        )
    ]
    for upload, attachment in fresh:
        operations.extend(
            [
                TransactionOperation(
                    TransactionOperationKind.UPLOAD_CONSUME,
                    {
                        "Update": {
                            "Key": upload_key(upload["upload_id"]),
                            "UpdateExpression": (
                                "SET #s=:consumed, #v=#v+:one, durable_attachment_id=:attachment_id"
                            ),
                            "ConditionExpression": (
                                "#owner=:owner AND #s=:validated AND #v=:version AND expires_at>:now"
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
                                ":attachment_id": attachment["attachment_id"],
                            },
                        }
                    },
                ),
                TransactionOperation(
                    TransactionOperationKind.ATTACHMENT_PUT,
                    {
                        "Put": {
                            "Item": {**attachment_key(attachment["attachment_id"]), **attachment},
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ),
            ]
        )
    for attachment in reused:
        operations.append(
            TransactionOperation(
                TransactionOperationKind.ATTACHMENT_REF,
                {
                    "Update": {
                        "Key": attachment_key(attachment["attachment_id"]),
                        "UpdateExpression": "SET ref_count=if_not_exists(ref_count,:one)+:one",
                        "ConditionExpression": "owner_id=:owner AND #status=:active",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":owner": owner_id,
                            ":active": "active",
                            ":one": 1,
                        },
                    }
                },
            )
        )
    operations.extend(
        TransactionOperation(
            TransactionOperationKind.ASSOCIATION_PUT,
            {
                "Put": {
                    "Item": association,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        )
        for association in associations
    )
    fresh_bytes = sum(int(attachment["content_length"]) for _, attachment in fresh)
    if fresh_bytes:
        operations.append(
            TransactionOperation(
                TransactionOperationKind.STORAGE_QUOTA_UPDATE,
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
                },
            )
        )
    return operations


def reserve_upload_for_question(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> bool:
    """Conditionally reserve one validated upload before any OCR/provider effect."""
    return _transition(
        upload_id,
        owner_id,
        "validated",
        "consuming",
        version,
        now_epoch,
        table=table,
    )


def release_question_upload_reservation(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> bool:
    """Release a transient question reservation within the original expiry."""
    return _transition(
        upload_id,
        owner_id,
        "consuming",
        "validated",
        version,
        now_epoch,
        table=table,
    )


def invalidate_question_upload_reservation(
    upload_id: str,
    owner_id: str,
    version: int,
    failure_category: str,
    *,
    table: Any | None = None,
) -> bool:
    return _transition(
        upload_id,
        owner_id,
        "consuming",
        "invalid",
        version,
        None,
        attributes={"validation_failure": failure_category},
        table=table,
    )


def invalidate_attachment(
    attachment_id: str,
    owner_id: str,
    *,
    table: Any | None = None,
) -> bool:
    try:
        (table or get_table()).update_item(
            Key=attachment_key(attachment_id),
            UpdateExpression="SET #status=:invalid",
            ConditionExpression="owner_id=:owner AND #status=:active",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":active": "active",
                ":invalid": "invalid",
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def build_question_attachment_transaction(
    *,
    question: dict[str, Any],
    prepared: dict[str, Any],
    attachment: dict[str, Any],
    association: dict[str, Any],
    owner_id: str,
    limit_bytes: int,
    now_iso: str,
) -> list[TransactionOperation]:
    """Commit a question and its attachment association as one conditional unit."""
    operations: list[TransactionOperation] = []
    if prepared["kind"] == "upload":
        upload = prepared["record"]
        operations.extend(
            [
                TransactionOperation(
                    TransactionOperationKind.UPLOAD_CONSUME,
                    {
                        "Update": {
                            "Key": upload_key(upload["upload_id"]),
                            "UpdateExpression": (
                                "SET #s=:consumed, #v=#v+:one, durable_attachment_id=:attachment_id"
                            ),
                            "ConditionExpression": (
                                "#owner=:owner AND #s=:consuming AND #v=:version AND expires_at>:now"
                            ),
                            "ExpressionAttributeNames": {
                                "#owner": "owner_id",
                                "#s": "status",
                                "#v": "version",
                            },
                            "ExpressionAttributeValues": {
                                ":owner": owner_id,
                                ":consuming": "consuming",
                                ":consumed": "consumed",
                                ":version": int(upload["version"]),
                                ":one": 1,
                                ":now": int(upload["consume_epoch"]),
                                ":attachment_id": attachment["attachment_id"],
                            },
                        }
                    },
                ),
                TransactionOperation(
                    TransactionOperationKind.ATTACHMENT_PUT,
                    {
                        "Put": {
                            "Item": {**attachment_key(attachment["attachment_id"]), **attachment},
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ),
                TransactionOperation(
                    TransactionOperationKind.STORAGE_QUOTA_UPDATE,
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
                                ":size": int(attachment["content_length"]),
                                ":limit": limit_bytes,
                                ":updated": now_iso,
                            },
                        }
                    },
                ),
            ]
        )
    else:
        operations.append(
            TransactionOperation(
                TransactionOperationKind.ATTACHMENT_REF,
                {
                    "Update": {
                        "Key": attachment_key(attachment["attachment_id"]),
                        "UpdateExpression": "SET ref_count=if_not_exists(ref_count,:one)+:one",
                        "ConditionExpression": (
                            "owner_id=:owner AND #status=:active AND detected_type IN (:jpeg,:png)"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":owner": owner_id,
                            ":active": "active",
                            ":one": 1,
                            ":jpeg": "image/jpeg",
                            ":png": "image/png",
                        },
                    }
                },
            )
        )
    operations.extend(
        [
            TransactionOperation(
                TransactionOperationKind.ASSOCIATION_PUT,
                {
                    "Put": {
                        "Item": association,
                        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                    }
                },
            ),
            TransactionOperation(
                TransactionOperationKind.QUESTION_PUT,
                {
                    "Put": {
                        "Item": question,
                        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                    }
                },
            ),
        ]
    )
    return operations


def get_storage_usage(owner_id: str, *, table: Any | None = None) -> int:
    response = (table or get_table()).get_item(Key=storage_key(owner_id), ConsistentRead=True)
    return int((response.get("Item") or {}).get("used_bytes", 0))


def list_owner_attachment_items(owner_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    response = (table or get_table()).query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq(owner_id),
    )
    return [
        item
        for item in response.get("Items", [])
        if item.get("entity_type") in {"attachment", "attachment_association"}
    ]


def build_release_reference_transaction(
    *, attachment: dict[str, Any], association: dict[str, Any], last_reference: bool
) -> list[dict[str, Any]]:
    delete_association = {
        "Delete": {
            "Key": {"PK": association["PK"], "SK": association["SK"]},
            "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
        }
    }
    if not last_reference:
        return [
            delete_association,
            {
                "Update": {
                    "Key": attachment_key(attachment["attachment_id"]),
                    "UpdateExpression": "SET ref_count=ref_count-:one",
                    "ConditionExpression": (
                        "owner_id=:owner AND #status=:active AND ref_count>:one"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": attachment["owner_id"],
                        ":active": "active",
                        ":one": 1,
                    },
                }
            },
        ]
    return [
        delete_association,
        {
            "Update": {
                "Key": attachment_key(attachment["attachment_id"]),
                "UpdateExpression": (
                    "SET #status=:pending, deletion_resource_type=:resource_type, "
                    "deletion_resource_id=:resource_id"
                ),
                "ConditionExpression": (
                    "owner_id=:owner AND #status=:active AND "
                    "(attribute_not_exists(ref_count) OR ref_count=:one)"
                ),
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": attachment["owner_id"],
                    ":active": "active",
                    ":pending": "deletion_pending",
                    ":one": 1,
                    ":resource_type": association["resource_type"],
                    ":resource_id": association["resource_id"],
                },
            }
        },
    ]


def build_finalize_deletion_transaction(
    attachment: dict[str, Any], now_iso: str
) -> list[dict[str, Any]]:
    size = int(attachment["content_length"])
    return [
        {
            "Delete": {
                "Key": attachment_key(attachment["attachment_id"]),
                "ConditionExpression": "owner_id=:owner AND #status=:pending",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": attachment["owner_id"],
                    ":pending": "deletion_pending",
                },
            }
        },
        {
            "Update": {
                "Key": storage_key(attachment["owner_id"]),
                "UpdateExpression": "SET used_bytes=used_bytes-:size, updated_at=:updated",
                "ConditionExpression": "used_bytes>=:size",
                "ExpressionAttributeValues": {":size": size, ":updated": now_iso},
            }
        },
    ]


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


def clear_staging_coordinates(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    table: Any | None = None,
) -> bool:
    try:
        (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=(
                "REMOVE staging_object_key, staging_version_id, staging_etag, multipart_upload_id"
            ),
            ConditionExpression=("owner_id=:owner AND #status=:validated AND #version=:version"),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":validated": "validated",
                ":version": version,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


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
                "UpdateExpression": (
                    "SET #s=:consumed, #v=#v+:one, durable_attachment_id=:attachment_id"
                ),
                "ConditionExpression": "#owner=:owner AND #s=:validated AND #v=:version AND expires_at>:now",
                "ExpressionAttributeNames": {"#owner": "owner_id", "#s": "status", "#v": "version"},
                "ExpressionAttributeValues": {
                    ":owner": upload["owner_id"],
                    ":validated": "validated",
                    ":consumed": "consumed",
                    ":version": upload["version"],
                    ":one": 1,
                    ":now": upload.get("consume_epoch", 0),
                    ":attachment_id": attachment["attachment_id"],
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


def transact(
    operations: list[dict[str, Any]] | list[TransactionOperation],
    *,
    table: Any | None = None,
) -> None:
    target = table or get_table()
    described = bool(operations) and isinstance(operations[0], TransactionOperation)
    transact_items = [operation.item for operation in operations] if described else operations
    try:
        if hasattr(target, "transact_write_items"):
            target.transact_write_items(TransactItems=transact_items)
        else:
            target.meta.client.transact_write_items(
                TransactItems=_serialize_transactions(transact_items, target.name)
            )
    except ClientError as exc:
        if described:
            raise AttachmentTransactionError(
                _attachment_transaction_outcome(
                    exc,
                    operations,  # type: ignore[arg-type]
                )
            ) from None
        if _conditional(exc):
            raise AttachmentRepositoryConflict() from None
        raise AttachmentRepositoryConflict("dependency_failure") from None


def _attachment_transaction_outcome(
    exc: ClientError, operations: list[TransactionOperation]
) -> AttachmentTransactionOutcome:
    """Classify from error code and ordered reason codes only.

    Provider messages, items, keys, and exception text intentionally never cross
    this function's boundary.
    """
    error_code = exc.response.get("Error", {}).get("Code")
    if error_code == "ConditionalCheckFailedException":
        return AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT
    if error_code != "TransactionCanceledException":
        return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY

    reasons = exc.response.get("CancellationReasons")
    if not isinstance(reasons, list) or len(reasons) != len(operations):
        return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY

    conditional_kinds: list[TransactionOperationKind] = []
    for operation, reason in zip(operations, reasons, strict=True):
        if not isinstance(reason, dict):
            return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
        code = reason.get("Code")
        if not isinstance(code, str):
            return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
        if code == "None":
            continue
        if code == "ConditionalCheckFailed":
            conditional_kinds.append(operation.kind)
            continue
        if code in {
            "TransactionConflict",
            "ProvisionedThroughputExceeded",
            "ThrottlingError",
        }:
            return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
        return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY

    if any(kind is not TransactionOperationKind.STORAGE_QUOTA_UPDATE for kind in conditional_kinds):
        return AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT
    if conditional_kinds:
        return AttachmentTransactionOutcome.QUOTA_EXCEEDED
    return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY


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
