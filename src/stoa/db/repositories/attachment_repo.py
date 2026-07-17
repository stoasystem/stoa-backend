"""Conditional single-table persistence for upload intents and attachments."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from stoa.config import UPLOAD_INTENT_TTL_SECONDS
from stoa.db.dynamodb import get_table


@dataclass(frozen=True, slots=True)
class AttachmentRepositoryConflict(Exception):
    category: str = "conditional_conflict"


class AttachmentTransactionOutcome(StrEnum):
    """Closed, provider-independent result of an attachment transaction."""

    CONCEALED_RESOURCE_CONFLICT = "concealed_resource_conflict"
    QUOTA_EXCEEDED = "quota_exceeded"
    RETRYABLE_DEPENDENCY = "retryable_dependency"


class MessageCommandDisposition(StrEnum):
    """Closed durable outcomes for every message-command transition."""

    CLAIMED = "claimed"
    RESUME = "resume"
    COMPLETED = "completed"
    REJECTED = "rejected"
    QUOTA_EXCEEDED = "quota_exceeded"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RETRYABLE = "retryable"
    LEASE_HELD = "lease_held"
    TERMINAL = "terminal"
    EXPIRED = "expired"
    MISSING = "missing"


class TransactionOperationKind(StrEnum):
    """Semantic transaction positions; never derived from provider diagnostics."""

    MESSAGE_PUT = "message_put"
    UPLOAD_CONSUME = "upload_consume"
    ATTACHMENT_PUT = "attachment_put"
    ATTACHMENT_REF = "attachment_ref"
    ASSOCIATION_PUT = "association_put"
    STORAGE_QUOTA_UPDATE = "storage_quota_update"
    QUESTION_PUT = "question_put"
    MESSAGE_COMMAND_PUT = "message_command_put"
    CHAT_QUOTA_OPERATION_PUT = "chat_quota_operation_put"
    CHAT_QUOTA_UPDATE = "chat_quota_update"
    CHAT_QUOTA_OPERATION_DELETE = "chat_quota_operation_delete"
    CHAT_QUOTA_COMPENSATE = "chat_quota_compensate"
    USAGE_EVENT_PUT = "usage_event_put"
    MESSAGE_COMMAND_UPDATE = "message_command_update"
    MESSAGE_COMMAND_REJECT = "message_command_reject"
    ASSISTANT_MESSAGE_PUT = "assistant_message_put"


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


@dataclass(frozen=True, slots=True)
class MessageCommandResult:
    disposition: MessageCommandDisposition
    command: dict[str, Any] | None = None
    counter_value: int | None = None
    error_code: str | None = None
    attempt: int | None = None
    operations: tuple[TransactionOperation, ...] = ()


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


def message_command_key(conversation_id: str, idempotency_key: str) -> dict[str, str]:
    return {
        "PK": f"CONV#{conversation_id}",
        "SK": f"MESSAGE_COMMAND#{idempotency_key}",
    }


def chat_quota_key(owner_id: str, quota_period: str) -> dict[str, str]:
    return {"PK": f"USAGE#{owner_id}", "SK": f"CHAT#{quota_period}"}


def chat_quota_operation_key(owner_id: str, command_id: str) -> dict[str, str]:
    return {"PK": f"USAGE#{owner_id}", "SK": f"CHAT_QUOTA_OP#{command_id}"}


def _message_usage_event_item(
    *, command: dict[str, Any], owner_id: str, now_iso: str
) -> dict[str, Any]:
    action = str(command["usage_action"])
    quota_period = str(command["quota_period"])
    idempotency_key = str(command["usage_idempotency_key"])
    counter_value = int(command["counter_value"])
    resource_id = str(command["usage_resource_id"])
    return {
        "PK": f"USAGE_LEDGER#{owner_id}",
        "SK": f"EVENT#{action}#{quota_period}#{idempotency_key}",
        "entity_type": "usage_ledger_event",
        "schema_version": "usage-ledger.v1",
        "event_id": str(command["usage_event_id"]),
        "actor_id": owner_id,
        "actor_role": "student",
        "student_id": owner_id,
        "action": action,
        "quantity": 1,
        "quota_period": quota_period,
        "counter_key": f"USAGE#{owner_id}/CHAT#{quota_period}",
        "counter_value_after": counter_value,
        "idempotency_key": idempotency_key,
        "request_correlation_id": resource_id,
        "privacy": {
            "raw_content_stored": False,
            "raw_learning_content_stored": False,
            "private_artifact_keys_stored": False,
            "provider_payloads_stored": False,
            "auth_tokens_stored": False,
            "verification_codes_stored": False,
        },
        "metadata": {
            "usage_type": "daily_chat_message",
            "summary_group": "chat",
            "quota_enforced": True,
            "support_visible": True,
            "conversation_id": str(command["conversation_id"]),
            "request_id": resource_id,
            "status": "sent",
            "write_order": "message_effect_transaction",
        },
        "created_at": str(command["created_at"]),
        "updated_at": now_iso,
        "expires_at": int(command["expires_at"]),
    }


def get_message_command(
    conversation_id: str,
    idempotency_key: str,
    *,
    table: Any | None = None,
) -> dict[str, Any] | None:
    response = (table or get_table()).get_item(
        Key=message_command_key(conversation_id, idempotency_key), ConsistentRead=True
    )
    return response.get("Item")


def classify_message_command(
    command: dict[str, Any] | None,
    *,
    owner_id: str,
    fingerprint: str,
    now_epoch: int,
) -> MessageCommandResult:
    """Validate identity and project one persisted command into a named state."""
    if not isinstance(command, dict):
        return MessageCommandResult(MessageCommandDisposition.MISSING)
    if command.get("owner_id") != owner_id:
        return MessageCommandResult(MessageCommandDisposition.MISSING)
    if command.get("fingerprint") != fingerprint:
        return MessageCommandResult(
            MessageCommandDisposition.IDEMPOTENCY_CONFLICT, command=dict(command)
        )
    if (
        command.get("entity_type") != "message_command"
        or command.get("schema_version") != "message-command.v2"
    ):
        return MessageCommandResult(
            MessageCommandDisposition.RETRYABLE, command=dict(command)
        )

    status = command.get("status")
    if not isinstance(status, str):
        return MessageCommandResult(
            MessageCommandDisposition.RETRYABLE, command=dict(command)
        )
    persisted = dict(command)
    counter_value = _optional_positive_int(persisted.get("counter_value"))
    if status == "claimed":
        expires_at = _optional_positive_int(persisted.get("expires_at"))
        disposition = (
            MessageCommandDisposition.EXPIRED
            if expires_at is not None and expires_at <= now_epoch
            else MessageCommandDisposition.CLAIMED
        )
    elif status == "message_committed":
        disposition = MessageCommandDisposition.RESUME
    elif status == "ai_running":
        lease_expiry = _optional_positive_int(persisted.get("expiresAt"))
        disposition = (
            MessageCommandDisposition.RESUME
            if lease_expiry is not None and lease_expiry <= now_epoch
            else MessageCommandDisposition.LEASE_HELD
        )
    elif status == "completed":
        disposition = (
            MessageCommandDisposition.COMPLETED
            if isinstance(persisted.get("result_json"), str)
            and bool(persisted["result_json"])
            else MessageCommandDisposition.RETRYABLE
        )
    elif status == "rejected":
        disposition = MessageCommandDisposition.REJECTED
    elif status == "terminal_failed":
        disposition = MessageCommandDisposition.TERMINAL
    elif status == "expired":
        disposition = MessageCommandDisposition.EXPIRED
    else:
        disposition = MessageCommandDisposition.RETRYABLE
    return MessageCommandResult(
        disposition,
        command=persisted,
        counter_value=counter_value,
        error_code=(
            str(persisted["error_code"])
            if isinstance(persisted.get("error_code"), str)
            else None
        ),
        attempt=_optional_positive_int(persisted.get("attempt")) or 0,
    )


def read_message_command_result(
    conversation_id: str,
    idempotency_key: str,
    *,
    owner_id: str,
    fingerprint: str,
    now_epoch: int = 0,
    table: Any | None = None,
) -> MessageCommandResult:
    try:
        command = get_message_command(conversation_id, idempotency_key, table=table)
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=now_epoch,
    )


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def build_message_command_claim_transaction(
    *,
    command: dict[str, Any],
    owner_id: str,
    quota_period: str,
    expected_counter: int,
    limit: int,
    expires_at: int,
) -> list[TransactionOperation]:
    command_id = str(command["command_id"])
    expected_exists = expected_counter > 0
    counter_condition = (
        "#count=:expected AND :next<=:limit"
        if expected_exists
        else "attribute_not_exists(#count) AND :next<=:limit"
    )
    values: dict[str, Any] = {
        ":next": expected_counter + 1,
        ":limit": limit,
        ":expires": expires_at,
    }
    if expected_exists:
        values[":expected"] = expected_counter
    return [
        TransactionOperation(
            TransactionOperationKind.MESSAGE_COMMAND_PUT,
            {
                "Put": {
                    "Item": {
                        **message_command_key(
                            str(command["conversation_id"]), str(command["idempotency_key"])
                        ),
                        **command,
                        "counter_value": expected_counter + 1,
                        "quota_period": quota_period,
                        "expires_at": expires_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.CHAT_QUOTA_OPERATION_PUT,
            {
                "Put": {
                    "Item": {
                        **chat_quota_operation_key(owner_id, command_id),
                        "entity_type": "chat_quota_operation",
                        "command_id": command_id,
                        "owner_id": owner_id,
                        "quota_period": quota_period,
                        "counter_value": expected_counter + 1,
                        "created_at": command["created_at"],
                        "expires_at": expires_at,
                    },
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.CHAT_QUOTA_UPDATE,
            {
                "Update": {
                    "Key": chat_quota_key(owner_id, quota_period),
                    "UpdateExpression": "SET #count=:next, #ttl=if_not_exists(#ttl,:expires)",
                    "ConditionExpression": counter_condition,
                    "ExpressionAttributeNames": {"#count": "count", "#ttl": "expires_at"},
                    "ExpressionAttributeValues": {
                        **values,
                    },
                }
            },
        ),
    ]


def claim_message_command_and_quota(
    *,
    command: dict[str, Any],
    owner_id: str,
    quota_period: str,
    limit: int,
    expires_at: int,
    table: Any | None = None,
) -> MessageCommandResult:
    """Atomically create a message command and charge its daily quota once."""
    target = table or get_table()
    fingerprint = str(command["fingerprint"])
    now_epoch = max(0, expires_at - 172800)
    existing = read_message_command_result(
        str(command["conversation_id"]),
        str(command["idempotency_key"]),
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=now_epoch,
        table=target,
    )
    if existing.disposition is not MessageCommandDisposition.MISSING:
        return existing

    expected = 0
    for _ in range(3):
        try:
            counter = target.get_item(
                Key=chat_quota_key(owner_id, quota_period), ConsistentRead=True
            ).get("Item") or {}
        except Exception:
            raise AttachmentRepositoryConflict("dependency_failure") from None
        expected = int(counter.get("count", 0))
        if expected >= limit:
            raced = read_message_command_result(
                str(command["conversation_id"]),
                str(command["idempotency_key"]),
                owner_id=owner_id,
                fingerprint=fingerprint,
                now_epoch=now_epoch,
                table=target,
            )
            if raced.disposition is not MessageCommandDisposition.MISSING:
                if raced.disposition is MessageCommandDisposition.CLAIMED:
                    return MessageCommandResult(
                        MessageCommandDisposition.RESUME,
                        command=raced.command,
                        counter_value=raced.counter_value,
                        attempt=raced.attempt,
                    )
                return raced
            return MessageCommandResult(
                MessageCommandDisposition.QUOTA_EXCEEDED,
                counter_value=expected,
            )
        operations = build_message_command_claim_transaction(
            command=command,
            owner_id=owner_id,
            quota_period=quota_period,
            expected_counter=expected,
            limit=limit,
            expires_at=expires_at,
        )
        try:
            transact(operations, table=target)
        except AttachmentTransactionError as exc:
            if exc.outcome is AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY:
                return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
            raced = read_message_command_result(
                str(command["conversation_id"]),
                str(command["idempotency_key"]),
                owner_id=owner_id,
                fingerprint=fingerprint,
                now_epoch=now_epoch,
                table=target,
            )
            if raced.disposition is not MessageCommandDisposition.MISSING:
                if raced.disposition is MessageCommandDisposition.CLAIMED:
                    return MessageCommandResult(
                        MessageCommandDisposition.RESUME,
                        command=raced.command,
                        counter_value=raced.counter_value,
                        attempt=raced.attempt,
                    )
                return raced
            continue
        persisted = {
            **command,
            "counter_value": expected + 1,
            "quota_period": quota_period,
            "expires_at": expires_at,
        }
        return MessageCommandResult(
            MessageCommandDisposition.CLAIMED,
            command=persisted,
            counter_value=expected + 1,
        )
    return MessageCommandResult(
        MessageCommandDisposition.RETRYABLE,
        counter_value=expected,
    )


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


def prepare_staging_issuance(item: dict[str, Any], *, table: Any | None = None) -> None:
    """Persist the never-reused staging coordinate before provider mutation."""
    required = {
        "staging_object_key",
        "operation_kind",
        "operation_fence",
        "operation_lease_expires_at",
    }
    if item.get("status") != "issuing" or not required.issubset(item):
        raise AttachmentRepositoryConflict("invalid_operation_state")
    create_upload_intent(item, table=table)


def _require_provider_coordinate(value: Any) -> str:
    """Reject malformed provider success coordinates before state can advance."""
    if not isinstance(value, str) or not value.strip():
        raise AttachmentRepositoryConflict("invalid_provider_coordinate")
    return value


def _require_positive_integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return value


def _require_canonical_sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return value


def _require_provider_sha256(value: Any, *, expected_hex: str) -> str:
    if not isinstance(value, str) or not value:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError):
        raise AttachmentRepositoryConflict(
            "invalid_provider_acknowledgement"
        ) from None
    if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != value:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    if decoded.hex() != _require_canonical_sha256(expected_hex):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return value


def record_staging_multipart(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    multipart_upload_id: str,
    table: Any | None = None,
) -> bool:
    multipart_upload_id = _require_provider_coordinate(multipart_upload_id)
    return _fenced_transition(
        upload_id, owner_id, "issuing", "pending_upload", version, operation_fence,
        attributes={"multipart_upload_id": multipart_upload_id},
        remove_operation=True, table=table,
    )


# Compatibility alias for callers outside the upload gateway. New code must persist
# the staging key through prepare_staging_issuance before provider mutation.
def mark_upload_issued(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    staging_object_key: str,
    multipart_upload_id: str,
    table: Any | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item or item.get("staging_object_key") != staging_object_key:
        return False
    return record_staging_multipart(
        upload_id,
        owner_id,
        version,
        operation_fence=str(item.get("operation_fence") or ""),
        multipart_upload_id=multipart_upload_id,
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
    part_number = _require_positive_integer(part_number)
    checksum_sha256 = _require_canonical_sha256(checksum_sha256)
    length = _require_positive_integer(length)
    lease_owner = _require_provider_coordinate(lease_owner)
    if isinstance(now_epoch, bool) or not isinstance(now_epoch, int) or now_epoch < 0:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    target = table or get_table()
    intent_expires_at = now_epoch + UPLOAD_INTENT_TTL_SECONDS
    if hasattr(target, "get_item"):
        intent = get_upload_intent(upload_id, table=target)
        if intent is None:
            raise AttachmentRepositoryConflict("conditional_conflict")
        raw_expires_at = intent.get("expires_at")
        if (
            isinstance(raw_expires_at, bool)
            or not isinstance(raw_expires_at, int)
            or raw_expires_at <= now_epoch
        ):
            raise AttachmentRepositoryConflict("conditional_conflict")
        intent_expires_at = raw_expires_at
    item = {
        **upload_part_key(upload_id, part_number),
        "upload_id": upload_id,
        "part_number": part_number,
        "status": "uploading",
        "checksum_sha256": checksum_sha256,
        "content_length": length,
        "lease_owner": lease_owner,
        "lease_expires_at": now_epoch + 120,
        "expires_at": intent_expires_at,
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
    expected_checksum_sha256: str,
    content_length: int,
    table: Any | None = None,
) -> bool:
    part_number = _require_positive_integer(part_number)
    _require_provider_coordinate(lease_owner)
    provider_etag = _require_provider_coordinate(provider_etag)
    expected_checksum_sha256 = _require_canonical_sha256(expected_checksum_sha256)
    provider_checksum = _require_provider_sha256(
        provider_checksum, expected_hex=expected_checksum_sha256
    )
    content_length = _require_positive_integer(content_length)
    try:
        (table or get_table()).update_item(
            Key=upload_part_key(upload_id, part_number),
            UpdateExpression=(
                "SET #status=:completed, provider_etag=:etag, "
                "provider_checksum=:provider_checksum REMOVE lease_expires_at"
            ),
            ConditionExpression=(
                "#status=:uploading AND lease_owner=:owner AND "
                "checksum_sha256=:checksum AND content_length=:length"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":uploading": "uploading",
                ":completed": "completed",
                ":owner": lease_owner,
                ":etag": provider_etag,
                ":provider_checksum": provider_checksum,
                ":checksum": expected_checksum_sha256,
                ":length": content_length,
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
    items = response.get("Items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    validated: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        part_number = _require_positive_integer(item.get("part_number"))
        if part_number in seen:
            raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
        seen.add(part_number)
        _require_canonical_sha256(item.get("checksum_sha256"))
        _require_positive_integer(item.get("content_length"))
        if item.get("status") == "completed":
            _require_provider_coordinate(item.get("provider_etag"))
            _require_provider_sha256(
                item.get("provider_checksum"), expected_hex=item["checksum_sha256"]
            )
        validated.append(item)
    return sorted(validated, key=lambda item: item["part_number"])


def claim_staging_assembly(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    operation_fence: str,
    multipart_upload_id: str,
    ordered_part_count: int,
    part_ledger_digest: str,
    table: Any | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    multipart_upload_id = _require_provider_coordinate(multipart_upload_id)
    ordered_part_count = _require_positive_integer(ordered_part_count)
    part_ledger_digest = _require_canonical_sha256(part_ledger_digest)
    return _transition(
        upload_id,
        owner_id,
        "pending_upload",
        "assembling",
        version,
        now_epoch,
        attributes={
            "operation_kind": "staging_assembly",
            "operation_fence": operation_fence,
            "operation_lease_expires_at": now_epoch + 120,
            "multipart_upload_id": multipart_upload_id,
            "assembly_part_count": ordered_part_count,
            "assembly_ledger_digest": part_ledger_digest,
            "operation_takeover_count": 0,
        },
        table=table,
    )


def begin_upload_assembly(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return claim_staging_assembly(
        upload_id, owner_id, version, now_epoch,
        operation_fence=str(item.get("operation_fence") or "legacy"),
        multipart_upload_id=str(item.get("multipart_upload_id") or ""),
        ordered_part_count=int(item.get("part_count", 0)),
        part_ledger_digest=str(item.get("assembly_ledger_digest") or "legacy"),
        table=table,
    )


def recover_staging_completion(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    staging_version_id: str,
    staging_etag: str,
    table: Any | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    staging_version_id = _require_provider_coordinate(staging_version_id)
    staging_etag = _require_provider_coordinate(staging_etag)
    return _fenced_transition(
        upload_id, owner_id, "assembling", "validating", version, operation_fence,
        attributes={
            "staging_version_id": staging_version_id,
            "staging_etag": staging_etag,
        },
        remove_operation=True, table=table,
    )


def claim_stale_upload_operation(
    upload_id: str,
    owner_id: str,
    version: int,
    operation_kind: str,
    previous_fence: str,
    new_fence: str,
    now_epoch: int,
    *,
    table: Any | None = None,
) -> dict[str, Any] | None:
    """Bounded lease takeover that fences every pre-restart worker."""
    try:
        response = (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=(
                "SET operation_fence=:new_fence, operation_lease_expires_at=:lease, "
                "operation_takeover_count=if_not_exists(operation_takeover_count,:zero)+:one, "
                "#version=:next"
            ),
            ConditionExpression=(
                "#owner=:owner AND #version=:version AND operation_kind=:kind AND "
                "operation_fence=:previous_fence AND operation_lease_expires_at<=:now AND "
                "(attribute_not_exists(operation_takeover_count) OR operation_takeover_count<:max)"
            ),
            ExpressionAttributeNames={"#owner": "owner_id", "#version": "version"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":version": version,
                ":next": version + 1,
                ":kind": operation_kind,
                ":previous_fence": previous_fence,
                ":new_fence": new_fence,
                ":now": now_epoch,
                ":lease": now_epoch + 120,
                ":zero": 0,
                ":one": 1,
                ":max": 2,
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if _conditional(exc):
            return None
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return response.get("Attributes")


def mark_staging_completed(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    staging_version_id: str,
    staging_etag: str,
    table: Any | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return recover_staging_completion(
        upload_id, owner_id, version,
        operation_fence=str(item.get("operation_fence") or ""),
        staging_version_id=staging_version_id,
        staging_etag=staging_etag,
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
            "#status IN (:pending,:validating,:validated,:issuing,:assembling,:promoting) "
            "AND expires_at<=:now))"
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
            ":issuing": "issuing",
            ":assembling": "assembling",
            ":promoting": "promoting",
            ":now": now_epoch,
        },
    }
    if exclusive_start_key:
        scan["ExclusiveStartKey"] = exclusive_start_key
    response = (table or get_table()).scan(**scan)
    items = response.get("Items", [])
    cursor = response.get("LastEvaluatedKey")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("dependency_failure")
    if cursor is not None and (
        not isinstance(cursor, dict)
        or set(cursor) != {"PK", "SK"}
        or any(not isinstance(value, str) or not value for value in cursor.values())
    ):
        raise AttachmentRepositoryConflict("dependency_failure")
    return items, cursor


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
                "#status IN (:pending,:validating,:validated,:issuing,:assembling,:promoting) "
                "AND expires_at<=:now))"
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
                ":issuing": "issuing",
                ":assembling": "assembling",
                ":promoting": "promoting",
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
    try:
        (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=(
                "SET #status=:complete, #version=:next, cleaned_at=:cleaned_at "
                "REMOVE staging_object_key, staging_version_id, staging_etag, "
                "multipart_upload_id, immutable_object_key, immutable_version_id, "
                "immutable_etag, operation_kind, operation_fence, "
                "operation_lease_expires_at, operation_takeover_count, "
                "cleanup_reference_cursor, cleanup_multipart_aborted, "
                "cleanup_staging_deleted, cleanup_immutable_deleted, "
                "cleanup_multipart_cursor, cleanup_staging_cursor, "
                "cleanup_immutable_cursor, cleanup_multipart_mutation_attempts, "
                "cleanup_staging_mutation_attempts, cleanup_immutable_mutation_attempts, "
                "cleanup_multipart_reconciliation_pages, "
                "cleanup_staging_reconciliation_pages, "
                "cleanup_immutable_reconciliation_pages, cleanup_part_cursor, "
                "cleanup_parts_absent"
            ),
            ConditionExpression=(
                "#status=:pending AND #version=:version AND "
                "cleanup_multipart_aborted=:true AND cleanup_staging_deleted=:true AND "
                "cleanup_immutable_deleted=:true AND cleanup_parts_absent=:true"
            ),
            ExpressionAttributeNames={"#status": "status", "#version": "version"},
            ExpressionAttributeValues={
                ":pending": "cleanup_pending",
                ":complete": "cleanup_complete",
                ":version": version,
                ":next": version + 1,
                ":cleaned_at": cleaned_at,
                ":true": True,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def mark_cleanup_multipart_aborted(
    upload_id: str, version: int, *, table: Any | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_multipart_aborted", table=table)


def mark_cleanup_staging_deleted(
    upload_id: str, version: int, *, table: Any | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_staging_deleted", table=table)


def mark_cleanup_immutable_deleted(
    upload_id: str, version: int, *, table: Any | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_immutable_deleted", table=table)


def defer_cleanup_reconciliation(
    upload_id: str,
    version: int,
    kind: str,
    cursor: dict[str, str],
    *,
    mutation_attempted: bool,
    pages: int,
    table: Any | None = None,
) -> bool:
    """Persist one bounded provider listing continuation under its cleanup generation."""
    if kind not in {"multipart", "staging", "immutable"}:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    if (
        not isinstance(cursor, dict)
        or not cursor
        or any(not isinstance(value, str) or not value.strip() for value in cursor.values())
    ):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    pages = _require_positive_integer(pages)
    mutation_increment = 1 if mutation_attempted is True else 0
    return _cleanup_update(
        upload_id,
        version,
        (
            f"SET cleanup_{kind}_cursor=:cursor, #version=:next, "
            f"cleanup_{kind}_mutation_attempts="
            f"if_not_exists(cleanup_{kind}_mutation_attempts,:zero)+:mutation, "
            f"cleanup_{kind}_reconciliation_pages="
            f"if_not_exists(cleanup_{kind}_reconciliation_pages,:zero)+:pages"
        ),
        {
            ":cursor": cursor,
            ":next": version + 1,
            ":zero": 0,
            ":mutation": mutation_increment,
            ":pages": pages,
        },
        table=table,
    )


def scrub_upload_parts(
    upload_id: str,
    version: int,
    *,
    limit: int,
    exclusive_start_key: dict[str, Any] | None = None,
    table: Any | None = None,
) -> tuple[int, dict[str, Any] | None] | None:
    """Delete one bounded PART page only while the cleanup generation is current."""
    from boto3.dynamodb.conditions import Key

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 24:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    target = table or get_table()
    request: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(f"UPLOAD#{upload_id}")
        & Key("SK").begins_with("PART#"),
        "ConsistentRead": True,
        "Limit": limit,
    }
    if exclusive_start_key:
        request["ExclusiveStartKey"] = exclusive_start_key
    response = target.query(**request)
    items = response.get("Items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("dependency_failure")
    if not items:
        return 0, None
    operations: list[dict[str, Any]] = [
        {
            "ConditionCheck": {
                "Key": upload_key(upload_id),
                "ConditionExpression": "#status=:pending AND #version=:version",
                "ExpressionAttributeNames": {"#status": "status", "#version": "version"},
                "ExpressionAttributeValues": {
                    ":pending": "cleanup_pending",
                    ":version": version,
                },
            }
        }
    ]
    for item in items:
        key = {"PK": item.get("PK"), "SK": item.get("SK")}
        if (
            key["PK"] != f"UPLOAD#{upload_id}"
            or not isinstance(key["SK"], str)
            or not key["SK"].startswith("PART#")
        ):
            raise AttachmentRepositoryConflict("dependency_failure")
        operations.append({"Delete": {"Key": key}})
    transact(operations, table=target)
    cursor = response.get("LastEvaluatedKey")
    if cursor is not None and not isinstance(cursor, dict):
        raise AttachmentRepositoryConflict("dependency_failure")
    return len(items), cursor


def advance_cleanup_part_scrub(
    upload_id: str,
    version: int,
    cursor: dict[str, Any] | None,
    *,
    table: Any | None = None,
) -> bool:
    if cursor is None:
        expression = "SET #version=:next REMOVE cleanup_part_cursor"
        values = {":next": version + 1}
    elif isinstance(cursor, dict) and cursor:
        expression = "SET cleanup_part_cursor=:cursor, #version=:next"
        values = {":cursor": cursor, ":next": version + 1}
    else:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return _cleanup_update(upload_id, version, expression, values, table=table)


def mark_cleanup_parts_absent(
    upload_id: str, version: int, *, table: Any | None = None
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_parts_absent=:true, #version=:next REMOVE cleanup_part_cursor",
        {":true": True, ":next": version + 1},
        table=table,
    )


def record_cleanup_staging_version(
    upload_id: str, version: int, version_id: str, etag: str, *, table: Any | None = None
) -> bool:
    version_id = _require_provider_coordinate(version_id)
    etag = _require_provider_coordinate(etag)
    return _cleanup_update(
        upload_id,
        version,
        "SET staging_version_id=:target, staging_etag=:etag, #version=:next",
        {":target": version_id, ":etag": etag, ":next": version + 1},
        table=table,
    )


def record_cleanup_immutable_version(
    upload_id: str, version: int, version_id: str, etag: str, *, table: Any | None = None
) -> bool:
    version_id = _require_provider_coordinate(version_id)
    etag = _require_provider_coordinate(etag)
    return _cleanup_update(
        upload_id,
        version,
        "SET immutable_version_id=:target, immutable_etag=:etag, #version=:next",
        {":target": version_id, ":etag": etag, ":next": version + 1},
        table=table,
    )


def _cleanup_progress(
    upload_id: str, version: int, field: str, *, table: Any | None
) -> bool:
    kind = {
        "cleanup_multipart_aborted": "multipart",
        "cleanup_staging_deleted": "staging",
        "cleanup_immutable_deleted": "immutable",
    }[field]
    return _cleanup_update(
        upload_id,
        version,
        (
            f"SET {field}=:true, #version=:next "
            f"REMOVE cleanup_{kind}_cursor"
        ),
        {":true": True, ":next": version + 1},
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
    command: dict[str, Any] | None = None,
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
    if command is not None:
        operations.append(
            TransactionOperation(
                TransactionOperationKind.USAGE_EVENT_PUT,
                {
                    "Put": {
                        "Item": _message_usage_event_item(
                            command=command, owner_id=owner_id, now_iso=now_iso
                        ),
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
            )
        )
        operations.append(
            TransactionOperation(
                TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
                {
                    "Update": {
                        "Key": message_command_key(
                            str(command["conversation_id"]),
                            str(command["idempotency_key"]),
                        ),
                        "UpdateExpression": "SET #status=:committed, message_committed_at=:now",
                        "ConditionExpression": (
                            "owner_id=:owner AND fingerprint=:fingerprint AND #status=:claimed"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":owner": owner_id,
                            ":fingerprint": command["fingerprint"],
                            ":claimed": "claimed",
                            ":committed": "message_committed",
                            ":now": now_iso,
                        },
                    }
                },
            )
        )
    return operations


def claim_message_ai_lease(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    now_epoch: int,
    expires_at: int,
    max_attempts: int = 3,
    table: Any | None = None,
) -> MessageCommandResult:
    target = table or get_table()
    try:
        command = get_message_command(conversation_id, idempotency_key, table=target) or {}
    except Exception:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    attempt = int(command.get("attempt", 0)) + 1
    command_status = command.get("status")
    can_claim = command_status == "message_committed" or (
        command_status == "ai_running"
        and int(command.get("expiresAt", 0)) <= now_epoch
        and attempt <= max_attempts
    )
    if not can_claim or attempt > max_attempts:
        if command_status == "completed":
            disposition = MessageCommandDisposition.COMPLETED
        elif command_status == "rejected":
            disposition = MessageCommandDisposition.REJECTED
        elif int(command.get("attempt", 0)) >= max_attempts:
            disposition = MessageCommandDisposition.TERMINAL
        elif command_status == "ai_running":
            disposition = MessageCommandDisposition.LEASE_HELD
        else:
            disposition = MessageCommandDisposition.RETRYABLE
        return MessageCommandResult(
            disposition,
            command=dict(command),
            counter_value=_optional_positive_int(command.get("counter_value")),
            error_code=(
                str(command["error_code"])
                if isinstance(command.get("error_code"), str)
                else None
            ),
            attempt=int(command.get("attempt", 0)),
        )
    try:
        target.update_item(
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:running, leaseOwner=:lease_owner, claimedAt=:claimed, "
                "expiresAt=:expires, attempt=:attempt"
            ),
            ConditionExpression=(
                "owner_id=:owner AND (#status=:committed OR "
                "(#status=:running AND expiresAt<=:now AND attempt<:max_attempts))"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":committed": "message_committed",
                ":running": "ai_running",
                ":lease_owner": lease_owner,
                ":claimed": now_epoch,
                ":expires": expires_at,
                ":now": now_epoch,
                ":attempt": attempt,
                ":max_attempts": max_attempts,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            try:
                reread = get_message_command(
                    conversation_id, idempotency_key, table=target
                )
            except Exception:
                return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
            if isinstance(reread, dict) and reread.get("owner_id") == owner_id:
                current_fingerprint = reread.get("fingerprint")
                if isinstance(current_fingerprint, str):
                    return classify_message_command(
                        reread,
                        owner_id=owner_id,
                        fingerprint=current_fingerprint,
                        now_epoch=now_epoch,
                    )
            return MessageCommandResult(MessageCommandDisposition.MISSING)
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    claimed = {
        **command,
        "status": "ai_running",
        "leaseOwner": lease_owner,
        "claimedAt": now_epoch,
        "expiresAt": expires_at,
        "attempt": attempt,
    }
    return MessageCommandResult(
        MessageCommandDisposition.CLAIMED,
        command=claimed,
        counter_value=_optional_positive_int(command.get("counter_value")),
        attempt=attempt,
    )


def complete_message_command(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    assistant_message: dict[str, Any],
    result_json: str,
    completed_at: str,
    table: Any | None = None,
) -> MessageCommandResult:
    operations = [
        TransactionOperation(
            TransactionOperationKind.ASSISTANT_MESSAGE_PUT,
            {
                "Put": {
                    "Item": assistant_message,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
            {
                "Update": {
                    "Key": message_command_key(conversation_id, idempotency_key),
                    "UpdateExpression": (
                        "SET #status=:completed, result_json=:result, completed_at=:completed_at "
                        "REMOVE leaseOwner, claimedAt, expiresAt"
                    ),
                    "ConditionExpression": (
                        "owner_id=:owner AND #status=:running AND leaseOwner=:lease_owner"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":running": "ai_running",
                        ":completed": "completed",
                        ":lease_owner": lease_owner,
                        ":result": result_json,
                        ":completed_at": completed_at,
                    },
                }
            },
        ),
    ]
    try:
        transact(operations, table=table)
    except AttachmentTransactionError:
        try:
            command = get_message_command(
                conversation_id, idempotency_key, table=table
            )
        except Exception:
            return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
        if (
            isinstance(command, dict)
            and command.get("owner_id") == owner_id
            and command.get("status") == "completed"
            and isinstance(command.get("result_json"), str)
            and command["result_json"]
        ):
            return MessageCommandResult(
                MessageCommandDisposition.COMPLETED,
                command=dict(command),
                counter_value=_optional_positive_int(command.get("counter_value")),
            )
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    return MessageCommandResult(MessageCommandDisposition.COMPLETED)


def renew_message_ai_lease(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    lease_owner: str,
    now_epoch: int,
    expires_at: int,
    table: Any | None = None,
) -> bool:
    try:
        (table or get_table()).update_item(
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression="SET claimedAt=:now, expiresAt=:expires",
            ConditionExpression=(
                "owner_id=:owner AND #status=:running AND leaseOwner=:lease_owner "
                "AND expiresAt>:now"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":lease_owner": lease_owner,
                ":now": now_epoch,
                ":expires": expires_at,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def reject_message_command_and_compensate(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    fingerprint: str,
    error_code: str,
    now_iso: str,
    table: Any | None = None,
) -> MessageCommandResult:
    """Terminally reject a pre-bind command and reverse its one quota claim."""
    target = table or get_table()
    try:
        command = get_message_command(conversation_id, idempotency_key, table=target)
    except Exception:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    current = classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=0,
    )
    if current.disposition is not MessageCommandDisposition.CLAIMED:
        return current
    assert current.command is not None
    command_id = str(current.command["command_id"])
    quota_period = str(current.command["quota_period"])
    counter_value = int(current.command["counter_value"])
    operations = (
        TransactionOperation(
            TransactionOperationKind.MESSAGE_COMMAND_REJECT,
            {
                "Update": {
                    "Key": message_command_key(conversation_id, idempotency_key),
                    "UpdateExpression": (
                        "SET #status=:rejected, error_code=:error, rejected_at=:now"
                    ),
                    "ConditionExpression": (
                        "owner_id=:owner AND fingerprint=:fingerprint AND #status=:claimed"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":fingerprint": fingerprint,
                        ":claimed": "claimed",
                        ":rejected": "rejected",
                        ":error": error_code,
                        ":now": now_iso,
                    },
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.CHAT_QUOTA_OPERATION_DELETE,
            {
                "Delete": {
                    "Key": chat_quota_operation_key(owner_id, command_id),
                    "ConditionExpression": "command_id=:command",
                    "ExpressionAttributeValues": {":command": command_id},
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.CHAT_QUOTA_COMPENSATE,
            {
                "Update": {
                    "Key": chat_quota_key(owner_id, quota_period),
                    "UpdateExpression": "SET #count=#count-:one",
                    "ConditionExpression": "#count=:expected AND #count>:zero",
                    "ExpressionAttributeNames": {"#count": "count"},
                    "ExpressionAttributeValues": {
                        ":one": 1,
                        ":zero": 0,
                        ":expected": counter_value,
                    },
                }
            },
        ),
    )
    try:
        transact(list(operations), table=target)
    except AttachmentTransactionError:
        try:
            reread = get_message_command(
                conversation_id, idempotency_key, table=target
            )
        except Exception:
            return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
        reconciled = classify_message_command(
            reread,
            owner_id=owner_id,
            fingerprint=fingerprint,
            now_epoch=0,
        )
        if reconciled.disposition is MessageCommandDisposition.REJECTED:
            return reconciled
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    rejected = {
        **current.command,
        "status": "rejected",
        "error_code": error_code,
        "rejected_at": now_iso,
    }
    return MessageCommandResult(
        MessageCommandDisposition.REJECTED,
        command=rejected,
        counter_value=counter_value,
        error_code=error_code,
        operations=operations,
    )


def mark_message_command_terminal(
    *,
    conversation_id: str,
    idempotency_key: str,
    owner_id: str,
    now_iso: str,
    table: Any | None = None,
) -> MessageCommandResult:
    try:
        (table or get_table()).update_item(
            Key=message_command_key(conversation_id, idempotency_key),
            UpdateExpression=(
                "SET #status=:terminal, terminal_at=:now REMOVE leaseOwner, claimedAt, expiresAt"
            ),
            ConditionExpression="owner_id=:owner AND #status=:running AND attempt>=:max",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":running": "ai_running",
                ":terminal": "terminal_failed",
                ":now": now_iso,
                ":max": 3,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            try:
                command = get_message_command(
                    conversation_id, idempotency_key, table=table
                )
            except Exception:
                return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
            if isinstance(command, dict) and command.get("owner_id") == owner_id:
                fingerprint = command.get("fingerprint")
                if isinstance(fingerprint, str):
                    return classify_message_command(
                        command,
                        owner_id=owner_id,
                        fingerprint=fingerprint,
                        now_epoch=0,
                    )
            return MessageCommandResult(MessageCommandDisposition.MISSING)
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    return MessageCommandResult(MessageCommandDisposition.TERMINAL)


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
    detected = {
        **detected,
        "immutable_version_id": _require_provider_coordinate(
            detected.get("immutable_version_id")
        ),
        "immutable_etag": _require_provider_coordinate(
            detected.get("immutable_etag")
        ),
    }
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


def begin_immutable_promotion(
    upload_id: str,
    owner_id: str,
    version: int,
    now_epoch: int,
    *,
    operation_fence: str,
    immutable_object_key: str,
    content_sha256: str,
    content_length: int,
    detected_type: str,
    image_width: int | None,
    image_height: int | None,
    table: Any | None = None,
) -> bool:
    """Fence and persist the exact immutable target before PutObject."""
    operation_fence = _require_provider_coordinate(operation_fence)
    immutable_object_key = _require_provider_coordinate(immutable_object_key)
    content_sha256 = _require_canonical_sha256(content_sha256)
    content_length = _require_positive_integer(content_length)
    detected_type = _require_provider_coordinate(detected_type)
    return _transition(
        upload_id,
        owner_id,
        "validating",
        "promoting",
        version,
        now_epoch,
        attributes={
            "operation_kind": "immutable_promotion",
            "operation_fence": operation_fence,
            "operation_lease_expires_at": now_epoch + 120,
            "operation_takeover_count": 0,
            "immutable_object_key": immutable_object_key,
            "content_sha256": content_sha256,
            "content_length": content_length,
            "detected_type": detected_type,
            "image_width": image_width,
            "image_height": image_height,
        },
        table=table,
    )


def record_immutable_version(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    operation_fence: str,
    immutable_version_id: str,
    immutable_etag: str,
    validated_at: str,
    table: Any | None = None,
) -> bool:
    operation_fence = _require_provider_coordinate(operation_fence)
    immutable_version_id = _require_provider_coordinate(immutable_version_id)
    immutable_etag = _require_provider_coordinate(immutable_etag)
    return _fenced_transition(
        upload_id,
        owner_id,
        "promoting",
        "validated",
        version,
        operation_fence,
        attributes={
            "immutable_version_id": immutable_version_id,
            "immutable_etag": immutable_etag,
            "validated_at": validated_at,
        },
        remove_operation=True,
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


def _fenced_transition(
    upload_id: str,
    owner_id: str,
    source: str,
    target: str,
    version: int,
    operation_fence: str,
    *,
    attributes: dict[str, Any] | None = None,
    remove_operation: bool = False,
    table: Any | None = None,
) -> bool:
    names = {
        "#owner": "owner_id",
        "#status": "status",
        "#version": "version",
        "#fence": "operation_fence",
    }
    values: dict[str, Any] = {
        ":owner": owner_id,
        ":source": source,
        ":target": target,
        ":version": version,
        ":next": version + 1,
        ":fence": operation_fence,
    }
    update = "SET #status=:target, #version=:next"
    for index, (name, value) in enumerate((attributes or {}).items()):
        names[f"#a{index}"] = name
        values[f":a{index}"] = value
        update += f", #a{index}=:a{index}"
    if remove_operation:
        update += (
            " REMOVE operation_kind, operation_fence, operation_lease_expires_at, "
            "operation_takeover_count"
        )
    try:
        (table or get_table()).update_item(
            Key=upload_key(upload_id),
            UpdateExpression=update,
            ConditionExpression=(
                "#owner=:owner AND #status=:source AND #version=:version AND #fence=:fence"
            ),
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
    except Exception:
        if described:
            raise AttachmentTransactionError(
                AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
            ) from None
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
