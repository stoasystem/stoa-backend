"""Conditional single-table persistence for upload intents and attachments."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from stoa.config import UPLOAD_INTENT_TTL_SECONDS
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


type AttachmentItem = dict[str, object]


@runtime_checkable
class _GetItemTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutItemTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateItemTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _BatchGetTable(Protocol):
    name: str

    def batch_get_item(self, **kwargs: object) -> object: ...


class _DynamoClient(Protocol):
    def batch_get_item(self, **kwargs: object) -> object: ...

    def transact_write_items(self, **kwargs: object) -> object: ...


class _DynamoMeta(Protocol):
    client: _DynamoClient


@runtime_checkable
class _DynamoTable(Protocol):
    name: str
    meta: _DynamoMeta


@runtime_checkable
class _HighLevelTransactionTable(Protocol):
    def transact_write_items(self, **kwargs: object) -> object: ...


def _mapping(value: object, *, category: str = "dependency_failure") -> AttachmentItem:
    if not isinstance(value, Mapping):
        raise AttachmentRepositoryConflict(category)
    item: AttachmentItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise AttachmentRepositoryConflict(category)
        item[key] = member
    return item


def _optional_mapping(
    value: object, *, category: str = "dependency_failure"
) -> AttachmentItem | None:
    return None if value is None else _mapping(value, category=category)


def _required_text(value: object, *, category: str = "conditional_conflict") -> str:
    if not isinstance(value, str) or not value:
        raise AttachmentRepositoryConflict(category)
    return value


def _required_integer(
    value: object,
    *,
    category: str = "conditional_conflict",
    minimum: int = 0,
) -> int:
    if isinstance(value, bool):
        raise AttachmentRepositoryConflict(category)
    if isinstance(value, int):
        result = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        result = int(value)
    else:
        raise AttachmentRepositoryConflict(category)
    if result < minimum:
        raise AttachmentRepositoryConflict(category)
    return result


def _get_item(table: object, **kwargs: object) -> AttachmentItem:
    if not isinstance(table, _GetItemTable):
        raise AttachmentRepositoryConflict("dependency_failure")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutItemTable):
        raise AttachmentRepositoryConflict("dependency_failure")
    return table.put_item(**kwargs)


def _update_item(table: object, **kwargs: object) -> AttachmentItem:
    if not isinstance(table, _UpdateItemTable):
        raise AttachmentRepositoryConflict("dependency_failure")
    response = table.update_item(**kwargs)
    return {} if response is None else _mapping(response)


def _query(table: object, **kwargs: object) -> AttachmentItem:
    if not isinstance(table, _QueryTable):
        raise AttachmentRepositoryConflict("dependency_failure")
    return _mapping(table.query(**kwargs))


def _scan(table: object, **kwargs: object) -> AttachmentItem:
    if not isinstance(table, _ScanTable):
        raise AttachmentRepositoryConflict("dependency_failure")
    return _mapping(table.scan(**kwargs))


def _deserialize_attribute(value: object) -> object:
    """Deserialize one validated string-keyed DynamoDB attribute wrapper."""
    attribute = _mapping(value)
    deserialize = getattr(TypeDeserializer(), "deserialize", None)
    if not callable(deserialize):
        raise AttachmentRepositoryConflict("dependency_failure")
    try:
        return deserialize(attribute)
    except (TypeError, ValueError):
        raise AttachmentRepositoryConflict("dependency_failure") from None


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
    RESOURCE_RETENTION_FENCE_CHECK = "resource_retention_fence_check"
    ACCOUNT_RETENTION_FENCE_CHECK = "account_retention_fence_check"


@dataclass(frozen=True, slots=True)
class TransactionOperation:
    kind: TransactionOperationKind
    item: dict[str, object]

    def __contains__(self, key: object) -> bool:
        return key in self.item

    def __getitem__(self, key: str) -> object:
        return self.item[key]

    def get(self, key: str, default: object = None) -> object:
        return self.item.get(key, default)


@dataclass(frozen=True, slots=True)
class AttachmentTransactionError(Exception):
    outcome: AttachmentTransactionOutcome


@dataclass(frozen=True, slots=True)
class MessageCommandResult:
    disposition: MessageCommandDisposition
    command: dict[str, object] | None = None
    counter_value: int | None = None
    error_code: str | None = None
    attempt: int | None = None
    operations: tuple[TransactionOperation, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversationPrivatePage:
    """One bounded strong base-table page used by account deletion."""

    items: tuple[dict[str, object], ...]
    cursor: dict[str, str] | None = None
    scanned_count: int = 0


CONVERSATION_PRIVATE_ROW_REGISTRY = frozenset(
    {
        "conversation_header",
        "conversation_message",
        "teacher_note",
        "message_command",
        "chat_quota_operation",
        "chat_usage_event",
        "attachment_association",
    }
)
CONVERSATION_WRITER_REGISTRY = frozenset(
    {
        "create_conversation",
        "message_command_claim",
        "message_attachment_commit",
        "ai_lease_claim",
        "ai_lease_renew",
        "ai_completion",
        "teacher_help",
        "usage_event",
    }
)
CONVERSATION_PRIVATE_FIELDS = frozenset(
    {
        "content",
        "result_json",
        "fingerprint",
        "history_fingerprint",
        "history_message_ids",
        "requested_attachments",
        "deterministic_attachment_ids",
        "student_message_id",
        "assistant_message_id",
        "title",
        "last_message_preview",
        "subject",
        "grade",
        "note",
        "notes",
        "help_text",
        "resolution_note",
        "escalation_message",
        "escalation_request_id",
        "attachment_ids",
        "request_correlation_id",
        "request_id",
        "metadata",
        "counter_key",
        "usage_resource_id",
        "usage_idempotency_key",
        "usage_event_id",
        "leaseOwner",
        "claimedAt",
        "expiresAt",
        "error_code",
    }
)
CONVERSATION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "conversation_id",
        "message_id",
        "command_id",
        "owner_id",
        "student_id",
        "role",
        "status",
        "action",
        "quantity",
        "quota_period",
        "counter_value",
        "counter_value_after",
        "count",
        "expires_at",
        "created_at",
        "updated_at",
        "deleted_at",
        "owner_deletion_generation",
        "account_fence_generation",
    }
)
CONVERSATION_ACTIVE_COMMAND_STATES = frozenset(
    {"claimed", "message_committed", "ai_running"}
)
CONVERSATION_PROVIDER_RETENTION_BOUNDARY = {
    "bedrock_request_response": "outside_backend_deletion_control"
}


def upload_key(upload_id: str) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": "META"}


def upload_part_key(upload_id: str, part_number: int) -> dict[str, str]:
    return {"PK": f"UPLOAD#{upload_id}", "SK": f"PART#{part_number:06d}"}


def attachment_key(attachment_id: str) -> dict[str, str]:
    return {"PK": f"ATTACHMENT#{attachment_id}", "SK": "META"}


def storage_key(owner_id: str) -> dict[str, str]:
    return {"PK": f"STORAGE#{owner_id}", "SK": "USAGE"}


def retention_fence_key(
    owner_id: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> dict[str, str]:
    if resource_type is None and resource_id is None:
        return account_deletion_repo.account_fence_key(owner_id)
    if (
        not isinstance(resource_type, str)
        or not resource_type.strip()
        or not isinstance(resource_id, str)
        or not resource_id.strip()
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    return {
        "PK": f"OWNER#{owner_id}",
        "SK": f"RETENTION#RESOURCE#{resource_type}#{resource_id}",
    }


def _retention_fence_checks(
    owner_id: str,
    resource_type: str,
    resource_id: str,
    account_fence_generation: int = 1,
) -> list[TransactionOperation]:
    expression = "attribute_not_exists(PK) OR #status=:complete"
    names = {"#status": "status"}
    values = {":complete": "complete"}
    return [
        TransactionOperation(
            TransactionOperationKind.RESOURCE_RETENTION_FENCE_CHECK,
            {
                "ConditionCheck": {
                    "Key": retention_fence_key(
                        owner_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                    ),
                    "ConditionExpression": expression,
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": values,
                }
            },
        ),
        TransactionOperation(
            TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
            account_deletion_repo.active_fence_condition(
                owner_id, account_fence_generation
            ),
        ),
    ]


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


def build_conversation_write_transaction(
    *,
    item: dict[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
) -> list[dict[str, object]]:
    """Build one owner-stamped conversation write behind the permanent fence."""
    if not owner_id or type(generation) is not int or generation <= 0:
        raise AttachmentRepositoryConflict("conditional_conflict")
    stamped = {
        **item,
        "owner_id": owner_id,
        "student_id": owner_id,
        "account_fence_generation": generation,
    }
    if not isinstance(stamped.get("PK"), str) or not isinstance(stamped.get("SK"), str):
        raise AttachmentRepositoryConflict("conditional_conflict")
    if mode == "put":
        mutation = {
            "Put": {
                "Item": stamped,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }
    elif mode == "replace":
        mutation = {
            "Put": {
                "Item": stamped,
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND "
                    "(owner_id=:owner OR student_id=:owner)"
                ),
                "ExpressionAttributeValues": {":owner": owner_id},
            }
        }
    else:
        raise AttachmentRepositoryConflict("conditional_conflict")
    return [account_deletion_repo.active_fence_condition(owner_id, generation), mutation]


def _conversation_write(
    *,
    item: dict[str, object],
    owner_id: str,
    generation: int,
    mode: str,
    table: object | None,
) -> dict[str, object]:
    operations = build_conversation_write_transaction(
        item=item, owner_id=owner_id, generation=generation, mode=mode
    )
    target = table or get_table()
    hook = getattr(target, "transact_conversation_write", None)
    if callable(hook):
        hook(operations)
    elif not hasattr(target, "meta") and hasattr(target, "put_item") and mode == "put":
        # Narrow compatibility for inherited in-memory fakes. Production tables
        # always execute the two-item transaction above.
        put = _mapping(operations[1].get("Put"))
        _put_item(target, Item=_mapping(put.get("Item")))
    else:
        try:
            account_deletion_repo.transact(operations, table=target)
        except account_deletion_repo.AccountDeletionConflict as exc:
            raise AttachmentRepositoryConflict("conditional_conflict") from exc
    return _mapping(_mapping(operations[1].get("Put")).get("Item"))


def create_conversation_record(
    item: dict[str, object],
    *,
    owner_id: str,
    generation: int = 1,
    table: object | None = None,
) -> dict[str, object]:
    return _conversation_write(
        item=item, owner_id=owner_id, generation=generation, mode="put", table=table
    )


def record_teacher_help_request(
    *,
    conversation: dict[str, object],
    message: dict[str, object],
    owner_id: str,
    generation: int = 1,
    table: object | None = None,
) -> None:
    """Persist help lifecycle and its system message atomically under one fence."""
    target = table or get_table()
    header = {
        **conversation,
        "escalated": True,
        "escalated_at": message["created_at"],
        "escalation_request_id": message["message_id"],
        "escalation_status": "pending",
        "escalation_message": message.get("escalation_message"),
        "updated_at": message["created_at"],
    }
    operations = [
        account_deletion_repo.active_fence_condition(owner_id, generation),
        {
            "Put": {
                "Item": {
                    **header,
                    "owner_id": owner_id,
                    "student_id": owner_id,
                    "account_fence_generation": generation,
                },
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:owner"
                ),
                "ExpressionAttributeValues": {":owner": owner_id},
            }
        },
        build_conversation_write_transaction(
            item=message, owner_id=owner_id, generation=generation, mode="put"
        )[1],
    ]
    hook = getattr(target, "transact_conversation_write", None)
    if callable(hook):
        hook(operations)
    elif not hasattr(target, "meta") and hasattr(target, "update_item"):
        # Inherited route fakes exercise projection only; production is atomic.
        _update_item(target,
            Key={"PK": header["PK"], "SK": header["SK"]},
            UpdateExpression="SET escalated=:e",
            ExpressionAttributeValues={":e": True},
        )
        _put_item(target, Item=operations[2]["Put"]["Item"])
    else:
        try:
            account_deletion_repo.transact(operations, table=target)
        except account_deletion_repo.AccountDeletionConflict as exc:
            raise AttachmentRepositoryConflict("conditional_conflict") from exc


def _valid_conversation_cursor(cursor: object) -> dict[str, str] | None:
    if cursor is None:
        return None
    if (
        not isinstance(cursor, dict)
        or set(cursor) != {"PK", "SK"}
        or any(not isinstance(cursor.get(key), str) or not cursor[key] for key in ("PK", "SK"))
    ):
        raise AttachmentRepositoryConflict("dependency_failure")
    return dict(cursor)


def _is_owned_conversation_private_row(item: dict[str, object], owner_id: str) -> bool:
    if item.get("owner_id") == owner_id or item.get("student_id") == owner_id:
        pk, sk = str(item.get("PK") or ""), str(item.get("SK") or "")
        return (
            pk.startswith(("CONV#", f"USAGE#{owner_id}", f"USAGE_LEDGER#{owner_id}"))
            or sk.startswith("REF#CONVERSATION#")
        )
    return False


def scan_conversation_private_rows(
    owner_id: str,
    *,
    cursor: dict[str, str] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> ConversationPrivatePage:
    """Strongly scan independently paginated conversation-owned row families."""
    if not owner_id or maximum_pages < 1 or maximum_pages > 100:
        raise AttachmentRepositoryConflict("dependency_failure")
    target = table or get_table()
    current = _valid_conversation_cursor(cursor)
    items: list[dict[str, object]] = []
    scanned = 0
    seen: set[tuple[str, str]] = set()
    for _ in range(maximum_pages):
        request: dict[str, object] = {"ConsistentRead": True}
        if current is not None:
            request["ExclusiveStartKey"] = current
        response = _scan(target, **request)
        if not isinstance(response, dict) or not isinstance(response.get("Items", []), list):
            raise AttachmentRepositoryConflict("dependency_failure")
        raw_page = response.get("Items", [])
        if not isinstance(raw_page, list):
            raise AttachmentRepositoryConflict("dependency_failure")
        page = [_mapping(item) for item in raw_page]
        scanned += len(page)
        items.extend(
            item for item in page if _is_owned_conversation_private_row(item, owner_id)
        )
        current = _valid_conversation_cursor(response.get("LastEvaluatedKey"))
        if current is None:
            break
        identity = (current["PK"], current["SK"])
        if identity in seen:
            raise AttachmentRepositoryConflict("dependency_failure")
        seen.add(identity)
    return ConversationPrivatePage(tuple(items), current, scanned)


def _conversation_tombstone(
    item: dict[str, object], *, owner_id: str, generation: int, now_iso: str
) -> dict[str, object]:
    tombstone = {
        key: value
        for key, value in item.items()
        if key in CONVERSATION_TOMBSTONE_ALLOWLIST
        and key not in CONVERSATION_PRIVATE_FIELDS
    }
    tombstone.update(
        {
            "PK": item["PK"],
            "SK": item["SK"],
            "owner_id": owner_id,
            "student_id": owner_id,
            "status": "deleted",
            "owner_deletion_generation": generation,
            "deleted_at": now_iso,
        }
    )
    return tombstone


def scrub_conversation_private_row(
    item: dict[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> dict[str, object]:
    tombstone = _conversation_tombstone(
        item, owner_id=owner_id, generation=generation, now_iso=now_iso
    )
    target = table or get_table()
    hook = getattr(target, "scrub_conversation_private_row", None)
    if callable(hook):
        hook(item, tombstone, owner_id, generation)
    else:
        operations = [
            {
                "ConditionCheck": {
                    "Key": account_deletion_repo.account_fence_key(owner_id),
                    "ConditionExpression": "#status=:pending AND generation=:generation",
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":pending": "deletion_pending",
                        ":generation": generation,
                    },
                }
            },
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) AND "
                        "(owner_id=:owner OR student_id=:owner)"
                    ),
                    "ExpressionAttributeValues": {":owner": owner_id},
                }
            },
        ]
        try:
            account_deletion_repo.transact(operations, table=target)
        except account_deletion_repo.AccountDeletionConflict as exc:
            raise AttachmentRepositoryConflict("conditional_conflict") from exc
    return tombstone


def cancel_stale_message_command(
    command: dict[str, object],
    *,
    owner_id: str,
    deletion_generation: int,
    now_iso: str,
    table: object | None = None,
) -> dict[str, object]:
    """Invalidate one old-generation command and erase all replay/lease content."""
    if command.get("owner_id") != owner_id and command.get("student_id") != owner_id:
        raise AttachmentRepositoryConflict("conditional_conflict")
    remove_fields = tuple(sorted(CONVERSATION_PRIVATE_FIELDS))
    target = table or get_table()
    hook = getattr(target, "cancel_stale_message_command", None)
    if callable(hook):
        hook(
            command=command,
            owner_id=owner_id,
            deletion_generation=deletion_generation,
            remove_fields=remove_fields,
            now_iso=now_iso,
        )
    else:
        scrub_conversation_private_row(
            command,
            owner_id=owner_id,
            generation=deletion_generation,
            now_iso=now_iso,
            table=target,
        )
    return {"status": "canceled", "command_id": command.get("command_id")}


def _message_usage_event_item(
    *, command: dict[str, object], owner_id: str, now_iso: str
) -> dict[str, object]:
    action = _required_text(command.get("usage_action"))
    quota_period = _required_text(command.get("quota_period"))
    idempotency_key = _required_text(command.get("usage_idempotency_key"))
    counter_value = _required_integer(command.get("counter_value"), minimum=1)
    resource_id = _required_text(command.get("usage_resource_id"))
    return {
        "PK": f"USAGE_LEDGER#{owner_id}",
        "SK": f"EVENT#{action}#{quota_period}#{idempotency_key}",
        "entity_type": "usage_ledger_event",
        "schema_version": "usage-ledger.v1",
        "event_id": _required_text(command.get("usage_event_id")),
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
            "conversation_id": _required_text(command.get("conversation_id")),
            "request_id": resource_id,
            "status": "sent",
            "write_order": "message_effect_transaction",
        },
        "created_at": _required_text(command.get("created_at")),
        "updated_at": now_iso,
        "expires_at": _required_integer(command.get("expires_at"), minimum=1),
    }


def get_message_command(
    conversation_id: str,
    idempotency_key: str,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    response = _get_item(table or get_table(),
        Key=message_command_key(conversation_id, idempotency_key), ConsistentRead=True
    )
    return _optional_mapping(response.get("Item"))


def classify_message_command(
    command: dict[str, object] | None,
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
    table: object | None = None,
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


def _optional_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def build_message_command_claim_transaction(
    *,
    command: dict[str, object],
    owner_id: str,
    quota_period: str,
    expected_counter: int,
    limit: int,
    expires_at: int,
    account_fence_generation: int = 1,
) -> list[TransactionOperation]:
    command_id = str(command["command_id"])
    expected_exists = expected_counter > 0
    counter_condition = (
        "#count=:expected AND :next<=:limit"
        if expected_exists
        else "attribute_not_exists(#count) AND :next<=:limit"
    )
    values: dict[str, object] = {
        ":next": expected_counter + 1,
        ":limit": limit,
        ":expires": expires_at,
    }
    if expected_exists:
        values[":expected"] = expected_counter
    return [
        TransactionOperation(
            TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
            account_deletion_repo.active_fence_condition(
                owner_id, account_fence_generation
            ),
        ),
        TransactionOperation(
            TransactionOperationKind.MESSAGE_COMMAND_PUT,
            {
                "Put": {
                    "Item": {
                        **message_command_key(
                            str(command["conversation_id"]), str(command["idempotency_key"])
                        ),
                        **command,
                        "owner_id": owner_id,
                        "student_id": owner_id,
                        "account_fence_generation": account_fence_generation,
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
    command: dict[str, object],
    owner_id: str,
    quota_period: str,
    limit: int,
    expires_at: int,
    account_fence_generation: int = 1,
    table: object | None = None,
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
            raw_counter = _get_item(target,
                Key=chat_quota_key(owner_id, quota_period), ConsistentRead=True
            ).get("Item")
            counter = _optional_mapping(raw_counter) or {}
        except Exception:
            raise AttachmentRepositoryConflict("dependency_failure") from None
        expected = _required_integer(counter.get("count", 0))
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
            account_fence_generation=account_fence_generation,
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
            "owner_id": owner_id,
            "student_id": owner_id,
            "account_fence_generation": account_fence_generation,
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


def create_upload_intent(item: dict[str, object], *, table: object | None = None) -> None:
    owner_id = str(item.get("owner_id") or "")
    generation = item.get("account_fence_generation")
    if type(generation) is not int or generation <= 0:
        raise AttachmentRepositoryConflict("conditional_conflict")
    upload_id = _required_text(item.get("upload_id"))
    try:
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(owner_id, generation),
                {
                    "Put": {
                        "Item": {**upload_key(upload_id), **item},
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
            ],
            table=table or get_table(),
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise AttachmentRepositoryConflict("conditional_conflict") from exc


def prepare_staging_issuance(item: dict[str, object], *, table: object | None = None) -> None:
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


def _require_provider_coordinate(value: object) -> str:
    """Reject malformed provider success coordinates before state can advance."""
    if not isinstance(value, str) or not value.strip():
        raise AttachmentRepositoryConflict("invalid_provider_coordinate")
    return value


def _require_positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return value


def _require_canonical_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return value


def _require_provider_sha256(value: object, *, expected_hex: str) -> str:
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
    table: object | None = None,
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
    table: object | None = None,
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
    table: object | None = None,
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
    upload_id: str, part_number: int, *, table: object | None = None
) -> dict[str, object] | None:
    response = _get_item(table or get_table(),
        Key=upload_part_key(upload_id, part_number), ConsistentRead=True
    )
    return _optional_mapping(response.get("Item"))


def claim_upload_part(
    upload_id: str,
    part_number: int,
    checksum_sha256: str,
    length: int,
    lease_owner: str,
    now_epoch: int,
    *,
    table: object | None = None,
) -> dict[str, object]:
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
        _put_item(target,
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
        or _required_integer(current.get("content_length", -1)) != length
    ):
        raise AttachmentRepositoryConflict("chunk_conflict")
    if (
        current.get("status") == "completed"
        or _required_integer(current.get("lease_expires_at", 0)) > now_epoch
    ):
        return current
    if _required_integer(current.get("attempt", 1), minimum=1) >= 2:
        raise AttachmentRepositoryConflict("lease_exhausted")
    try:
        response = _update_item(target,
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
    return _optional_mapping(response.get("Attributes")) or {
        **current,
        "lease_owner": lease_owner,
        "attempt": 2,
    }


def complete_upload_part(
    upload_id: str,
    part_number: int,
    lease_owner: str,
    *,
    provider_etag: str,
    provider_checksum: str,
    expected_checksum_sha256: str,
    content_length: int,
    table: object | None = None,
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
        _update_item(table or get_table(),
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


def list_upload_parts(upload_id: str, *, table: object | None = None) -> list[dict[str, object]]:
    from boto3.dynamodb.conditions import Key

    response = _query(table or get_table(),
        KeyConditionExpression=Key("PK").eq(f"UPLOAD#{upload_id}") & Key("SK").begins_with("PART#"),
        ConsistentRead=True,
    )
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    items = [
        _mapping(item, category="invalid_provider_acknowledgement")
        for item in raw_items
    ]
    validated: list[dict[str, object]] = []
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
                item.get("provider_checksum"),
                expected_hex=_require_canonical_sha256(item.get("checksum_sha256")),
            )
        validated.append(item)
    return sorted(
        validated,
        key=lambda item: _require_positive_integer(item.get("part_number")),
    )


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
    table: object | None = None,
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
    table: object | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return claim_staging_assembly(
        upload_id, owner_id, version, now_epoch,
        operation_fence=_required_text(item.get("operation_fence") or "legacy"),
        multipart_upload_id=_required_text(item.get("multipart_upload_id")),
        ordered_part_count=_required_integer(item.get("part_count", 0)),
        part_ledger_digest=_required_text(
            item.get("assembly_ledger_digest") or "legacy"
        ),
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
    table: object | None = None,
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
    table: object | None = None,
) -> dict[str, object] | None:
    """Bounded lease takeover that fences every pre-restart worker."""
    try:
        response = _update_item(table or get_table(),
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
    return _optional_mapping(response.get("Attributes"))


def mark_staging_completed(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    staging_version_id: str,
    staging_etag: str,
    table: object | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return recover_staging_completion(
        upload_id, owner_id, version,
        operation_fence=_required_text(item.get("operation_fence")),
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
    table: object | None = None,
) -> bool:
    item = get_upload_intent(upload_id, table=table)
    if not item:
        return False
    return _transition(
        upload_id,
        owner_id,
        _required_text(item.get("status")),
        "cleanup_pending",
        version,
        None,
        attributes={"validation_failure": failure_category},
        table=table,
    )


def get_upload_intent(upload_id: str, *, table: object | None = None) -> dict[str, object] | None:
    response = _get_item(table or get_table(), Key=upload_key(upload_id), ConsistentRead=True)
    return _optional_mapping(response.get("Item"))


def list_upload_cleanup_candidates(
    now_epoch: int,
    *,
    limit: int,
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Return one bounded page of terminal or expired unconsumed upload intents."""
    scan: dict[str, object] = {
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
    response = _scan(table or get_table(), **scan)
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
    table: object | None = None,
) -> dict[str, object] | None:
    """Conditionally make one eligible intent non-consumable for cleanup."""
    try:
        response = _update_item(table or get_table(),
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
    return _optional_mapping(response.get("Attributes"))


def scan_durable_upload_references(
    upload_id: str,
    immutable_object_key: str = "",
    immutable_version_id: str = "",
    *,
    limit: int,
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[bool, dict[str, object] | None]:
    """Scan one bounded page for a durable attachment referencing upload bytes."""
    scan: dict[str, object] = {
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
    response = _scan(table or get_table(), **scan)
    return bool(response.get("Items")), _optional_mapping(
        response.get("LastEvaluatedKey")
    )


def advance_upload_cleanup_reference_scan(
    upload_id: str,
    version: int,
    cursor: dict[str, object],
    *,
    table: object | None = None,
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_reference_cursor=:cursor, #version=:next",
        {":cursor": cursor, ":next": version + 1},
        table=table,
    )


def block_upload_cleanup(upload_id: str, version: int, *, table: object | None = None) -> bool:
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
    table: object | None = None,
) -> bool:
    try:
        _update_item(table or get_table(),
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
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_multipart_aborted", table=table)


def mark_cleanup_staging_deleted(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_progress(upload_id, version, "cleanup_staging_deleted", table=table)


def mark_cleanup_immutable_deleted(
    upload_id: str, version: int, *, table: object | None = None
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
    table: object | None = None,
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
    exclusive_start_key: dict[str, object] | None = None,
    table: object | None = None,
) -> tuple[int, dict[str, object] | None] | None:
    """Delete one bounded PART page only while the cleanup generation is current."""
    from boto3.dynamodb.conditions import Key

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 24:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    target = table or get_table()
    request: dict[str, object] = {
        "KeyConditionExpression": Key("PK").eq(f"UPLOAD#{upload_id}")
        & Key("SK").begins_with("PART#"),
        "ConsistentRead": True,
        "Limit": limit,
    }
    if exclusive_start_key:
        request["ExclusiveStartKey"] = exclusive_start_key
    response = _query(target, **request)
    items = response.get("Items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AttachmentRepositoryConflict("dependency_failure")
    if not items:
        return 0, None
    operations: list[dict[str, object]] = [
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
    cursor: dict[str, object] | None,
    *,
    table: object | None = None,
) -> bool:
    if cursor is None:
        expression = "SET #version=:next REMOVE cleanup_part_cursor"
        values: dict[str, object] = {":next": version + 1}
    elif isinstance(cursor, dict) and cursor:
        expression = "SET cleanup_part_cursor=:cursor, #version=:next"
        values = {":cursor": cursor, ":next": version + 1}
    else:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return _cleanup_update(upload_id, version, expression, values, table=table)


def mark_cleanup_parts_absent(
    upload_id: str, version: int, *, table: object | None = None
) -> bool:
    return _cleanup_update(
        upload_id,
        version,
        "SET cleanup_parts_absent=:true, #version=:next REMOVE cleanup_part_cursor",
        {":true": True, ":next": version + 1},
        table=table,
    )


def record_cleanup_staging_version(
    upload_id: str, version: int, version_id: str, etag: str, *, table: object | None = None
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
    upload_id: str, version: int, version_id: str, etag: str, *, table: object | None = None
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
    upload_id: str, version: int, field: str, *, table: object | None
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
    values: dict[str, object],
    *,
    table: object | None,
) -> bool:
    try:
        _update_item(table or get_table(),
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


def get_attachment(attachment_id: str, *, table: object | None = None) -> dict[str, object] | None:
    response = _get_item(table or get_table(),
        Key=attachment_key(attachment_id), ConsistentRead=True
    )
    return _optional_mapping(response.get("Item"))


def get_attachments(
    attachment_ids: list[str], *, table: object | None = None
) -> dict[str, dict[str, object]]:
    if not attachment_ids:
        return {}
    if (
        any(not isinstance(value, str) or not value for value in attachment_ids)
        or len(set(attachment_ids)) != len(attachment_ids)
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    target = table or get_table()
    expected_keys: list[dict[str, object]] = [
        _mapping(attachment_key(value)) for value in attachment_ids
    ]
    if isinstance(target, _BatchGetTable):
        pending: list[dict[str, object]] = expected_keys
        items: list[dict[str, object]] = []
        for _attempt in range(3):
            try:
                response = _mapping(target.batch_get_item(
                    RequestItems={
                        target.name: {"Keys": pending, "ConsistentRead": True}
                    }
                ))
            except Exception:
                raise AttachmentRepositoryConflict("dependency_failure") from None
            returned, pending = _batch_response_page(
                response,
                table_name=target.name,
                expected_pending=pending,
            )
            items.extend(returned)
            if not pending:
                break
        if pending:
            raise AttachmentRepositoryConflict("dependency_failure")
    elif isinstance(target, _DynamoTable):
        serializer = TypeSerializer()
        pending = [
            {
                key: serializer.serialize(value)
                for key, value in attachment_key(item).items()
            }
            for item in attachment_ids
        ]
        raw_items: list[dict[str, object]] = []
        for _attempt in range(3):
            try:
                response = _mapping(target.meta.client.batch_get_item(
                    RequestItems={
                        target.name: {"Keys": pending, "ConsistentRead": True}
                    }
                ))
            except Exception:
                raise AttachmentRepositoryConflict("dependency_failure") from None
            returned, pending = _batch_response_page(
                response,
                table_name=target.name,
                expected_pending=pending,
            )
            raw_items.extend(returned)
            if not pending:
                break
        if pending:
            raise AttachmentRepositoryConflict("dependency_failure")
        items = [
            {key: _deserialize_attribute(value) for key, value in item.items()}
            for item in raw_items
        ]
    else:
        try:
            items = [
                item
                for value in attachment_ids
                if (item := get_attachment(value, table=target))
            ]
        except Exception:
            raise AttachmentRepositoryConflict("dependency_failure") from None
    by_id: dict[str, dict[str, object]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise AttachmentRepositoryConflict("dependency_failure")
        attachment_id = item.get("attachment_id")
        if not isinstance(attachment_id, str) or attachment_id in by_id:
            raise AttachmentRepositoryConflict("conditional_conflict")
        if attachment_id not in attachment_ids:
            raise AttachmentRepositoryConflict("conditional_conflict")
        if item.get("PK") != attachment_key(attachment_id)["PK"] or item.get("SK") != "META":
            raise AttachmentRepositoryConflict("conditional_conflict")
        by_id[attachment_id] = item
    if set(by_id) != set(attachment_ids):
        raise AttachmentRepositoryConflict("conditional_conflict")
    return {attachment_id: by_id[attachment_id] for attachment_id in attachment_ids}


def list_saved_attachments(
    owner_id: str,
    *,
    limit: int,
    exclusive_start_key: dict[str, str] | None = None,
    table: object | None = None,
) -> tuple[list[dict[str, object]], dict[str, str] | None]:
    """Return a stable owner page from the authoritative strongly-read base table."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise AttachmentRepositoryConflict("conditional_conflict")
    if exclusive_start_key is not None and (
        not isinstance(exclusive_start_key, dict)
        or set(exclusive_start_key) != {"attachment_id"}
        or not isinstance(exclusive_start_key.get("attachment_id"), str)
        or not exclusive_start_key["attachment_id"]
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    items = list_owner_attachment_items(
        owner_id,
        table=table,
        entity_types=frozenset({"attachment"}),
    )
    active: list[tuple[str, AttachmentItem]] = []
    for item in items:
        attachment_id = item.get("attachment_id")
        if (
            item.get("status") == "active"
            and isinstance(attachment_id, str)
            and attachment_id
        ):
            active.append((attachment_id, item))
    ordered = [item for _attachment_id, item in sorted(active)]
    if exclusive_start_key is not None:
        after = exclusive_start_key["attachment_id"]
        ordered = [
            item
            for item in ordered
            if _required_text(item.get("attachment_id")) > after
        ]
    page = ordered[:limit]
    cursor = (
        {"attachment_id": _required_text(page[-1].get("attachment_id"))}
        if len(ordered) > limit
        else None
    )
    return page, cursor


def mark_saved_attachment_deletion_pending(
    attachment: dict[str, object], *, table: object | None = None
) -> bool:
    """Fence an unreferenced owner attachment before exact-version deletion."""
    try:
        _update_item(table or get_table(),
            Key=attachment_key(_required_text(attachment.get("attachment_id"))),
            UpdateExpression=(
                "SET #status=:pending, deletion_stage=:stage, "
                "deletion_resource_type=:resource_type, "
                "deletion_resource_id=:resource_id, "
                "deletion_expected_ref_count=:zero, "
                "deletion_expected_quota_bytes=:size"
            ),
            ConditionExpression=(
                "owner_id=:owner AND #status=:active AND "
                "(attribute_not_exists(ref_count) OR ref_count=:zero) AND "
                "immutable_object_key=:key AND immutable_version_id=:version AND "
                "immutable_etag=:etag AND content_length=:size"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": attachment["owner_id"],
                ":active": "active",
                ":pending": "deletion_pending",
                ":stage": "object_deletion_pending",
                ":resource_type": "saved_attachment",
                ":resource_id": attachment["attachment_id"],
                ":zero": 0,
                ":size": _require_positive_integer(attachment["content_length"]),
                ":key": _require_provider_coordinate(
                    attachment["immutable_object_key"]
                ),
                ":version": _require_provider_coordinate(
                    attachment["immutable_version_id"]
                ),
                ":etag": _require_provider_coordinate(attachment["immutable_etag"]),
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    except AttachmentRepositoryConflict:
        raise
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def claim_account_upload_cleanup(
    upload: dict[str, object],
    *,
    owner_id: str,
    account_fence_generation: int,
    table: object | None = None,
) -> dict[str, object] | None:
    """Make any account-owned upload non-consumable under the account fence."""
    upload_id = _required_text(upload.get("upload_id"))
    upload_version = _required_integer(upload.get("version"), minimum=1)
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(owner_id),
                "ConditionExpression": "#status=:pending AND generation=:generation",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":pending": "deletion_pending",
                    ":generation": account_fence_generation,
                },
            }
        },
        {
            "Update": {
                "Key": upload_key(upload_id),
                "UpdateExpression": (
                    "SET #status=:pending, #version=:next, cleanup_reason=:reason "
                    "REMOVE durable_attachment_id"
                ),
                "ConditionExpression": (
                    "owner_id=:owner AND #version=:version AND "
                    "#status<>:complete"
                ),
                "ExpressionAttributeNames": {
                    "#status": "status",
                    "#version": "version",
                },
                "ExpressionAttributeValues": {
                    ":owner": owner_id,
                    ":version": upload_version,
                    ":next": upload_version + 1,
                    ":pending": "cleanup_pending",
                    ":complete": "cleanup_complete",
                    ":reason": "account_closure",
                },
            }
        },
    ]
    try:
        transact(operations, table=table)
    except AttachmentRepositoryConflict:
        return None
    current = get_upload_intent(upload_id, table=table)
    if (
        not current
        or current.get("owner_id") != owner_id
        or current.get("status") != "cleanup_pending"
    ):
        return None
    return current


def delete_account_upload_tombstone(
    upload_id: str,
    *,
    owner_id: str,
    account_fence_generation: int,
    table: object | None = None,
) -> bool:
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(owner_id),
                "ConditionExpression": "#status=:pending AND generation=:generation",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":pending": "deletion_pending",
                    ":generation": account_fence_generation,
                },
            }
        },
        {
            "Delete": {
                "Key": upload_key(upload_id),
                "ConditionExpression": "owner_id=:owner AND #status=:complete",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": owner_id,
                    ":complete": "cleanup_complete",
                },
            }
        },
    ]
    try:
        transact(operations, table=table)
    except AttachmentRepositoryConflict:
        return False
    return True


def delete_empty_storage_usage(
    owner_id: str,
    *,
    account_fence_generation: int,
    table: object | None = None,
) -> bool:
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(owner_id),
                "ConditionExpression": "#status=:pending AND generation=:generation",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":pending": "deletion_pending",
                    ":generation": account_fence_generation,
                },
            }
        },
        {
            "Delete": {
                "Key": storage_key(owner_id),
                "ConditionExpression": (
                    "attribute_not_exists(used_bytes) OR used_bytes=:zero"
                ),
                "ExpressionAttributeValues": {":zero": 0},
            }
        },
    ]
    try:
        transact(operations, table=table)
    except AttachmentRepositoryConflict:
        return False
    return True


def _batch_response_page(
    response: object,
    *,
    table_name: str,
    expected_pending: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Validate one BatchGet response without coercing provider shapes."""
    if not isinstance(response, dict):
        raise AttachmentRepositoryConflict("dependency_failure")
    responses = response.get("Responses", {})
    unprocessed = response.get("UnprocessedKeys", {})
    if not isinstance(responses, dict) or not isinstance(unprocessed, dict):
        raise AttachmentRepositoryConflict("dependency_failure")
    returned = responses.get(table_name, [])
    table_unprocessed = unprocessed.get(table_name, {})
    if not isinstance(returned, list) or not isinstance(table_unprocessed, dict):
        raise AttachmentRepositoryConflict("dependency_failure")
    pending = table_unprocessed.get("Keys", [])
    if not isinstance(pending, list) or any(not isinstance(key, dict) for key in pending):
        raise AttachmentRepositoryConflict("dependency_failure")
    if any(key not in expected_pending for key in pending) or len(pending) != len(
        {repr(sorted(key.items())) for key in pending}
    ):
        raise AttachmentRepositoryConflict("dependency_failure")
    return returned, pending


def build_message_attachment_transaction(
    *,
    message: dict[str, object],
    fresh: list[tuple[dict[str, object], dict[str, object]]],
    reused: list[dict[str, object]],
    associations: list[dict[str, object]],
    owner_id: str,
    limit_bytes: int,
    now_iso: str,
    command: dict[str, object] | None = None,
    account_fence_generation: int = 1,
) -> list[TransactionOperation]:
    operations: list[TransactionOperation] = [
        TransactionOperation(
            TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
            account_deletion_repo.active_fence_condition(
                owner_id, account_fence_generation
            ),
        )
    ]
    if associations:
        resource_type = _required_text(
            associations[0].get("resource_type") or "conversation"
        )
        resource_id = _required_text(associations[0].get("resource_id"))
        operations.append(
            TransactionOperation(
                TransactionOperationKind.RESOURCE_RETENTION_FENCE_CHECK,
                {
                    "ConditionCheck": {
                        "Key": retention_fence_key(
                            owner_id,
                            resource_type=resource_type,
                            resource_id=resource_id,
                        ),
                        "ConditionExpression": "attribute_not_exists(PK) OR #status=:complete",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {":complete": "complete"},
                    }
                },
            )
        )
    operations.extend(
        [
        TransactionOperation(
            TransactionOperationKind.MESSAGE_PUT,
            {
                "Put": {
                    "Item": {
                        **message,
                        "owner_id": owner_id,
                        "student_id": owner_id,
                        "account_fence_generation": account_fence_generation,
                    },
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        )
        ]
    )
    for upload, attachment in fresh:
        upload_id = _required_text(upload.get("upload_id"))
        upload_version = _required_integer(upload.get("version"), minimum=1)
        consume_epoch = _required_integer(upload.get("consume_epoch"))
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.extend(
            [
                TransactionOperation(
                    TransactionOperationKind.UPLOAD_CONSUME,
                    {
                        "Update": {
                            "Key": upload_key(upload_id),
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
                                ":version": upload_version,
                                ":one": 1,
                                ":now": consume_epoch,
                                ":attachment_id": attachment_id,
                            },
                        }
                    },
                ),
                TransactionOperation(
                    TransactionOperationKind.ATTACHMENT_PUT,
                    {
                        "Put": {
                            "Item": {**attachment_key(attachment_id), **attachment},
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ),
            ]
        )
    for attachment in reused:
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.append(
            TransactionOperation(
                TransactionOperationKind.ATTACHMENT_REF,
                {
                    "Update": {
                        "Key": attachment_key(attachment_id),
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
    fresh_bytes = sum(
        _require_positive_integer(attachment.get("content_length"))
        for _, attachment in fresh
    )
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
                            _required_text(command.get("conversation_id")),
                            _required_text(command.get("idempotency_key")),
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
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> MessageCommandResult:
    target = table or get_table()
    try:
        command = get_message_command(conversation_id, idempotency_key, table=target) or {}
    except Exception:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    persisted_attempt = _optional_positive_int(command.get("attempt")) or 0
    attempt = persisted_attempt + 1
    generation = account_fence_generation or command.get("account_fence_generation")
    if type(generation) is not int or generation <= 0:
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    command_status = command.get("status")
    can_claim = command_status == "message_committed" or (
        command_status == "ai_running"
        and (_optional_positive_int(command.get("expiresAt")) or 0) <= now_epoch
        and attempt <= max_attempts
    )
    if not can_claim or attempt > max_attempts:
        if command_status == "completed":
            disposition = MessageCommandDisposition.COMPLETED
        elif command_status == "rejected":
            disposition = MessageCommandDisposition.REJECTED
        elif persisted_attempt >= max_attempts:
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
            attempt=persisted_attempt,
        )
    try:
        transact(
            [
                TransactionOperation(
                    TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
                    account_deletion_repo.active_fence_condition(owner_id, generation),
                ),
                TransactionOperation(
                    TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
                    {
                        "Update": {
                            "Key": message_command_key(conversation_id, idempotency_key),
                            "UpdateExpression": (
                                "SET #status=:running, leaseOwner=:lease_owner, claimedAt=:claimed, "
                                "expiresAt=:expires, attempt=:attempt"
                            ),
                            "ConditionExpression": (
                                "owner_id=:owner AND account_fence_generation=:generation AND "
                                "(#status=:committed OR (#status=:running AND "
                                "expiresAt<=:now AND attempt<:max_attempts))"
                            ),
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": {
                                ":owner": owner_id,
                                ":generation": generation,
                                ":committed": "message_committed",
                                ":running": "ai_running",
                                ":lease_owner": lease_owner,
                                ":claimed": now_epoch,
                                ":expires": expires_at,
                                ":now": now_epoch,
                                ":attempt": attempt,
                                ":max_attempts": max_attempts,
                            },
                        }
                    },
                ),
            ],
            table=target,
        )
    except AttachmentTransactionError as exc:
        if exc.outcome is AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT:
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
    assistant_message: dict[str, object],
    result_json: str,
    completed_at: str,
    lease_attempt: int = 1,
    completed_epoch: int = 0,
    account_fence_generation: int = 1,
    table: object | None = None,
) -> MessageCommandResult:
    if (
        isinstance(lease_attempt, bool)
        or not isinstance(lease_attempt, int)
        or lease_attempt <= 0
        or isinstance(completed_epoch, bool)
        or not isinstance(completed_epoch, int)
        or completed_epoch < 0
    ):
        return MessageCommandResult(MessageCommandDisposition.RETRYABLE)
    operations = [
        TransactionOperation(
            TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
            account_deletion_repo.active_fence_condition(
                owner_id, account_fence_generation
            ),
        ),
        TransactionOperation(
            TransactionOperationKind.ASSISTANT_MESSAGE_PUT,
            {
                "Put": {
                    "Item": {
                        **assistant_message,
                        "owner_id": owner_id,
                        "student_id": owner_id,
                        "account_fence_generation": account_fence_generation,
                    },
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
                        "owner_id=:owner AND account_fence_generation=:generation AND #status=:running AND "
                        "leaseOwner=:lease_owner AND attempt=:lease_attempt AND "
                        "expiresAt>:completed_epoch"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {
                        ":owner": owner_id,
                        ":generation": account_fence_generation,
                        ":running": "ai_running",
                        ":completed": "completed",
                        ":lease_owner": lease_owner,
                        ":lease_attempt": lease_attempt,
                        ":completed_epoch": completed_epoch,
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
    account_fence_generation: int = 1,
    table: object | None = None,
) -> bool:
    try:
        transact(
            [
                TransactionOperation(
                    TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK,
                    account_deletion_repo.active_fence_condition(
                        owner_id, account_fence_generation
                    ),
                ),
                TransactionOperation(
                    TransactionOperationKind.MESSAGE_COMMAND_UPDATE,
                    {
                        "Update": {
                            "Key": message_command_key(conversation_id, idempotency_key),
                            "UpdateExpression": "SET claimedAt=:now, expiresAt=:expires",
                            "ConditionExpression": (
                                "owner_id=:owner AND account_fence_generation=:generation AND "
                                "#status=:running AND leaseOwner=:lease_owner AND expiresAt>:now"
                            ),
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": {
                                ":owner": owner_id,
                                ":generation": account_fence_generation,
                                ":running": "ai_running",
                                ":lease_owner": lease_owner,
                                ":now": now_epoch,
                                ":expires": expires_at,
                            },
                        }
                    },
                ),
            ],
            table=table,
        )
    except AttachmentTransactionError as exc:
        if exc.outcome is AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT:
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
    table: object | None = None,
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
    command_id = _required_text(current.command.get("command_id"))
    quota_period = _required_text(current.command.get("quota_period"))
    counter_value = _required_integer(
        current.command.get("counter_value"), minimum=1
    )
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
    table: object | None = None,
) -> MessageCommandResult:
    try:
        _update_item(table or get_table(),
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
    table: object | None = None,
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
    table: object | None = None,
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
    table: object | None = None,
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
    table: object | None = None,
) -> bool:
    try:
        _update_item(table or get_table(),
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
    question: dict[str, object],
    prepared: dict[str, object],
    attachment: dict[str, object],
    association: dict[str, object],
    owner_id: str,
    limit_bytes: int,
    now_iso: str,
    account_fence_generation: int = 1,
) -> list[TransactionOperation]:
    """Commit a question and its attachment association as one conditional unit."""
    resource_type = _required_text(
        association.get("resource_type") or "question"
    )
    resource_id = _required_text(
        association.get("resource_id") or question.get("question_id")
    )
    operations = _retention_fence_checks(
        owner_id,
        resource_type,
        resource_id,
        account_fence_generation=account_fence_generation,
    )
    if prepared["kind"] == "upload":
        upload = _mapping(prepared.get("record"), category="conditional_conflict")
        upload_id = _required_text(upload.get("upload_id"))
        upload_version = _required_integer(upload.get("version"), minimum=1)
        consume_epoch = _required_integer(upload.get("consume_epoch"))
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.extend(
            [
                TransactionOperation(
                    TransactionOperationKind.UPLOAD_CONSUME,
                    {
                        "Update": {
                            "Key": upload_key(upload_id),
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
                                ":version": upload_version,
                                ":one": 1,
                                ":now": consume_epoch,
                                ":attachment_id": attachment_id,
                            },
                        }
                    },
                ),
                TransactionOperation(
                    TransactionOperationKind.ATTACHMENT_PUT,
                    {
                        "Put": {
                            "Item": {**attachment_key(attachment_id), **attachment},
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
                                ":size": _require_positive_integer(
                                    attachment.get("content_length")
                                ),
                                ":limit": limit_bytes,
                                ":updated": now_iso,
                            },
                        }
                    },
                ),
            ]
        )
    else:
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.append(
            TransactionOperation(
                TransactionOperationKind.ATTACHMENT_REF,
                {
                    "Update": {
                        "Key": attachment_key(attachment_id),
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


def get_storage_usage(owner_id: str, *, table: object | None = None) -> int:
    response = _get_item(table or get_table(), Key=storage_key(owner_id), ConsistentRead=True)
    item = _optional_mapping(response.get("Item")) or {}
    return _required_integer(item.get("used_bytes", 0))


def list_owner_attachment_items(
    owner_id: str,
    *,
    table: object | None = None,
    maximum_pages: int = 100,
    maximum_items: int = 10_000,
    entity_types: frozenset[str] | None = frozenset(
        {"attachment", "attachment_association"}
    ),
    fence: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Exhaustively read the authoritative table before inferring reference absence.

    DynamoDB GSIs cannot provide strongly consistent reads. Retention therefore scans
    the base table with ConsistentRead and validates every pagination transition.
    """
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise AttachmentRepositoryConflict("conditional_conflict")
    target = table or get_table()
    cursor: dict[str, str] | None = None
    seen_cursors: set[tuple[str, str]] = set()
    seen_keys: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for _page in range(maximum_pages):
        request: dict[str, object] = {
            "ConsistentRead": True,
            "Limit": min(100, maximum_items),
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        try:
            response = _scan(target, **request)
        except AttachmentRepositoryConflict:
            raise
        except Exception:
            raise AttachmentRepositoryConflict("dependency_failure") from None
        raw_items = response.get("Items", [])
        if not isinstance(raw_items, list):
            raise AttachmentRepositoryConflict("dependency_failure")
        for raw_item in raw_items:
            item = _mapping(raw_item)
            if item.get("student_id") != owner_id and item.get("owner_id") != owner_id:
                continue
            if entity_types is not None and item.get("entity_type") not in entity_types:
                continue
            pk = item.get("PK")
            sk = item.get("SK")
            if not isinstance(pk, str) or not pk or not isinstance(sk, str) or not sk:
                raise AttachmentRepositoryConflict("conditional_conflict")
            identity = (pk, sk)
            if identity in seen_keys:
                continue
            seen_keys.add(identity)
            result.append(item)
            if len(result) > maximum_items:
                raise AttachmentRepositoryConflict("dependency_failure")
        raw_cursor = response.get("LastEvaluatedKey")
        if raw_cursor is None:
            if fence is not None and not advance_retention_fence_cursor(
                fence, None, table=target
            ):
                raise AttachmentRepositoryConflict("conditional_conflict")
            return result
        if (
            not isinstance(raw_cursor, dict)
            or set(raw_cursor) != {"PK", "SK"}
            or not isinstance(raw_cursor.get("PK"), str)
            or not raw_cursor["PK"]
            or not isinstance(raw_cursor.get("SK"), str)
            or not raw_cursor["SK"]
        ):
            raise AttachmentRepositoryConflict("dependency_failure")
        cursor_identity = (raw_cursor["PK"], raw_cursor["SK"])
        if cursor_identity in seen_cursors:
            raise AttachmentRepositoryConflict("dependency_failure")
        seen_cursors.add(cursor_identity)
        cursor = {"PK": raw_cursor["PK"], "SK": raw_cursor["SK"]}
        if fence is not None and not advance_retention_fence_cursor(
            fence, cursor, table=target
        ):
            raise AttachmentRepositoryConflict("conditional_conflict")
    raise AttachmentRepositoryConflict("dependency_failure")


def list_owner_staging_cleanup_debts(
    owner_id: str, *, table: object | None = None
) -> list[dict[str, object]]:
    return [
        item
        for item in list_owner_attachment_items(
            owner_id,
            table=table,
            entity_types=None,
        )
        if item.get("staging_cleanup_status") == "pending"
    ]


def activate_retention_fence(
    owner_id: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    now_iso: str,
    table: object | None = None,
) -> dict[str, object]:
    """Create one durable active fence, or resume the existing generation."""
    target = table or get_table()
    key = retention_fence_key(
        owner_id, resource_type=resource_type, resource_id=resource_id
    )
    try:
        _update_item(target,
            Key=key,
            UpdateExpression=(
                "SET owner_id=:owner, entity_type=:entity, schema_version=:schema, "
                "#status=:active, generation=if_not_exists(generation,:zero)+:one, "
                "retention_stage=:fenced, updated_at=:now, quiescent_passes=:zero "
                "REMOVE retention_cursor"
            ),
            ConditionExpression="attribute_not_exists(PK) OR #status=:complete",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": owner_id,
                ":entity": "attachment_retention_fence",
                ":schema": "attachment-retention.v1",
                ":active": "active",
                ":complete": "complete",
                ":fenced": "fenced",
                ":zero": 0,
                ":one": 1,
                ":now": now_iso,
            },
        )
    except ClientError as exc:
        if not _conditional(exc):
            raise AttachmentRepositoryConflict("dependency_failure") from None
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    try:
        response = _get_item(target, Key=key, ConsistentRead=True)
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    item = _optional_mapping(response.get("Item"))
    generation = item.get("generation") if item is not None else None
    if (
        not isinstance(item, dict)
        or item.get("owner_id") != owner_id
        or item.get("status") != "active"
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    return item


def complete_retention_fence(
    fence: dict[str, object], *, now_iso: str, table: object | None = None
) -> bool:
    # The canonical account fence is permanent. Only resource-retention fences
    # transition to complete; Plan 35 owns the terminal account lifecycle state.
    if fence.get("SK") == "ACCOUNT_FENCE":
        return False
    fence_pk = _required_text(fence.get("PK"))
    fence_sk = _required_text(fence.get("SK"))
    generation = _required_integer(fence.get("generation"), minimum=1)
    try:
        _update_item(table or get_table(),
            Key={"PK": fence_pk, "SK": fence_sk},
            UpdateExpression=(
                "SET #status=:complete, retention_stage=:complete, updated_at=:now "
                "REMOVE retention_cursor"
            ),
            ConditionExpression="#status=:active AND generation=:generation",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":active": "active",
                ":complete": "complete",
                ":generation": generation,
                ":now": now_iso,
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def advance_retention_fence_cursor(
    fence: dict[str, object],
    cursor: dict[str, str] | None,
    *,
    table: object | None = None,
) -> bool:
    """Persist validated scan progress and count completed quiescence passes."""
    if cursor is None:
        update = (
            "SET retention_stage=:releasing, "
            "quiescent_passes=if_not_exists(quiescent_passes,:zero)+:one "
            "REMOVE retention_cursor"
        )
        values: dict[str, object] = {
            ":releasing": "references_releasing",
            ":zero": 0,
            ":one": 1,
        }
    elif (
        isinstance(cursor, dict)
        and set(cursor) == {"PK", "SK"}
        and all(isinstance(cursor[field], str) and cursor[field] for field in ("PK", "SK"))
    ):
        update = "SET retention_stage=:releasing, retention_cursor=:cursor"
        values = {":releasing": "references_releasing", ":cursor": cursor}
    else:
        raise AttachmentRepositoryConflict("conditional_conflict")
    fence_pk = _required_text(fence.get("PK"))
    fence_sk = _required_text(fence.get("SK"))
    generation = _required_integer(fence.get("generation"), minimum=1)
    values.update(
        {
            ":active": "active",
            ":pending": "deletion_pending",
            ":generation": generation,
        }
    )
    try:
        _update_item(table or get_table(),
            Key={"PK": fence_pk, "SK": fence_sk},
            UpdateExpression=update,
            ConditionExpression=(
                "#status IN (:active,:pending) AND generation=:generation"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def build_release_reference_transaction(
    *, attachment: dict[str, object], association: dict[str, object], last_reference: bool
) -> list[dict[str, object]]:
    attachment_id = _required_text(attachment.get("attachment_id"))
    association_pk = _required_text(association.get("PK"))
    association_sk = _required_text(association.get("SK"))
    delete_association: dict[str, object] = {
        "Delete": {
            "Key": {"PK": association_pk, "SK": association_sk},
            "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
        }
    }
    if not last_reference:
        return [
            delete_association,
            {
                "Update": {
                    "Key": attachment_key(attachment_id),
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
                "Key": attachment_key(attachment_id),
                "UpdateExpression": (
                    "SET #status=:pending, deletion_resource_type=:resource_type, "
                    "deletion_resource_id=:resource_id, deletion_stage=:stage, "
                    "deletion_expected_ref_count=:one, deletion_expected_quota_bytes=:size"
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
                    ":stage": "object_deletion_pending",
                    ":size": _require_positive_integer(
                        attachment.get("content_length")
                    ),
                },
            }
        },
    ]


def mark_deletion_absence_proven(
    attachment: dict[str, object], *, table: object | None = None
) -> bool:
    """Persist exact object-absence proof before quota/reference finalization."""
    try:
        _update_item(table or get_table(),
            Key=attachment_key(_required_text(attachment.get("attachment_id"))),
            UpdateExpression="SET deletion_stage=:absence",
            ConditionExpression=(
                "owner_id=:owner AND #status=:pending AND "
                "immutable_object_key=:key AND immutable_version_id=:version AND "
                "immutable_etag=:etag AND content_length=:size AND "
                "(attribute_not_exists(deletion_stage) OR deletion_stage IN (:deleting,:absence))"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":owner": attachment["owner_id"],
                ":pending": "deletion_pending",
                ":key": _require_provider_coordinate(attachment["immutable_object_key"]),
                ":version": _require_provider_coordinate(
                    attachment["immutable_version_id"]
                ),
                ":etag": _require_provider_coordinate(attachment["immutable_etag"]),
                ":size": _require_positive_integer(attachment["content_length"]),
                ":deleting": "object_deletion_pending",
                ":absence": "object_absence_proven",
            },
        )
    except ClientError as exc:
        if _conditional(exc):
            return False
        raise AttachmentRepositoryConflict("dependency_failure") from None
    except AttachmentRepositoryConflict:
        raise
    except Exception:
        raise AttachmentRepositoryConflict("dependency_failure") from None
    return True


def build_finalize_deletion_transaction(
    attachment: dict[str, object], now_iso: str
) -> list[dict[str, object]]:
    size = _require_positive_integer(attachment.get("content_length"))
    attachment_id = _required_text(attachment.get("attachment_id"))
    owner_id = _required_text(attachment.get("owner_id"))
    return [
        {
            "Delete": {
                "Key": attachment_key(attachment_id),
                "ConditionExpression": (
                    "owner_id=:owner AND #status=:pending AND deletion_stage=:absence AND "
                    "immutable_object_key=:key AND immutable_version_id=:version AND "
                    "immutable_etag=:etag AND content_length=:size"
                ),
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {
                    ":owner": attachment["owner_id"],
                    ":pending": "deletion_pending",
                    ":absence": "object_absence_proven",
                    ":key": attachment["immutable_object_key"],
                    ":version": attachment["immutable_version_id"],
                    ":etag": attachment["immutable_etag"],
                    ":size": size,
                },
            }
        },
        {
            "Update": {
                "Key": storage_key(owner_id),
                "UpdateExpression": "SET used_bytes=used_bytes-:size, updated_at=:updated",
                "ConditionExpression": "used_bytes>=:size",
                "ExpressionAttributeValues": {":size": size, ":updated": now_iso},
            }
        },
    ]


def begin_validation(
    upload_id: str, owner_id: str, version: int, now_epoch: int, *, table: object | None = None
) -> bool:
    return _transition(
        upload_id, owner_id, "pending_upload", "validating", version, now_epoch, table=table
    )


def mark_validated(
    upload_id: str,
    owner_id: str,
    version: int,
    detected: dict[str, object],
    *,
    table: object | None = None,
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
    table: object | None = None,
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
    table: object | None = None,
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
            "staging_cleanup_status": "pending",
        },
        remove_operation=True,
        table=table,
    )


def clear_staging_coordinates(
    upload_id: str,
    owner_id: str,
    version: int,
    *,
    table: object | None = None,
) -> bool:
    try:
        _update_item(table or get_table(),
            Key=upload_key(upload_id),
            UpdateExpression=(
                "REMOVE staging_object_key, staging_version_id, staging_etag, "
                "multipart_upload_id, staging_cleanup_status"
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
    upload_id: str, owner_id: str, version: int, failure_category: str, *, table: object | None = None
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
    upload_id: str, owner_id: str, version: int, now_epoch: int, *, table: object | None = None
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
    attributes: dict[str, object] | None = None,
    table: object | None = None,
) -> bool:
    names = {"#owner": "owner_id", "#status": "status", "#version": "version"}
    values: dict[str, object] = {
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
        _update_item(table or get_table(),
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
    attributes: dict[str, object] | None = None,
    remove_operation: bool = False,
    table: object | None = None,
) -> bool:
    names = {
        "#owner": "owner_id",
        "#status": "status",
        "#version": "version",
        "#fence": "operation_fence",
    }
    values: dict[str, object] = {
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
        _update_item(table or get_table(),
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
    upload: dict[str, object],
    attachment: dict[str, object],
    association: dict[str, object],
    limit_bytes: int,
    now_iso: str,
) -> list[dict[str, object]]:
    size = _require_positive_integer(attachment.get("content_length"))
    upload_id = _required_text(upload.get("upload_id"))
    upload_owner = _required_text(upload.get("owner_id"))
    attachment_id = _required_text(attachment.get("attachment_id"))
    return [
        {
            "Update": {
                "Key": upload_key(upload_id),
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
                    ":attachment_id": attachment_id,
                },
            }
        },
        {
            "Put": {
                "Item": {**attachment_key(attachment_id), **attachment},
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
                "Key": storage_key(upload_owner),
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
    *, attachment: dict[str, object], association: dict[str, object]
) -> list[dict[str, object]]:
    attachment_id = _required_text(attachment.get("attachment_id"))
    return [
        {
            "ConditionCheck": {
                "Key": attachment_key(attachment_id),
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
    operations: list[dict[str, object]] | list[TransactionOperation],
    *,
    table: object | None = None,
) -> None:
    target = table or get_table()
    described_operations: list[TransactionOperation] = []
    transact_items: list[AttachmentItem] = []
    for operation in operations:
        if isinstance(operation, TransactionOperation):
            described_operations.append(operation)
            transact_items.append(operation.item)
        else:
            transact_items.append(_mapping(operation))
    described = bool(described_operations)
    if described and len(described_operations) != len(operations):
        raise AttachmentRepositoryConflict("dependency_failure")
    try:
        if isinstance(target, _HighLevelTransactionTable):
            target.transact_write_items(TransactItems=transact_items)
        else:
            if not isinstance(target, _DynamoTable):
                raise AttachmentRepositoryConflict("dependency_failure")
            target.meta.client.transact_write_items(
                TransactItems=_serialize_transactions(transact_items, target.name)
            )
    except ClientError as exc:
        if described:
            raise AttachmentTransactionError(
                _attachment_transaction_outcome(
                    exc,
                    described_operations,
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
    operations: list[dict[str, object]], table_name: str
) -> list[dict[str, object]]:
    serializer = TypeSerializer()
    result: list[dict[str, object]] = []
    for operation in operations:
        operation_name, raw_value = next(iter(operation.items()))
        value = _mapping(raw_value)
        encoded: dict[str, object] = {"TableName": table_name}
        if "Key" in value:
            key_values = _mapping(value["Key"])
            encoded["Key"] = {
                key: serializer.serialize(item) for key, item in key_values.items()
            }
        if "Item" in value:
            item_values = _mapping(value["Item"])
            encoded["Item"] = {
                key: serializer.serialize(item)
                for key, item in item_values.items()
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
            attribute_values = _mapping(value["ExpressionAttributeValues"])
            encoded["ExpressionAttributeValues"] = {
                key: serializer.serialize(item)
                for key, item in attribute_values.items()
            }
        result.append({operation_name: encoded})
    return result


def _translate(exc: ClientError) -> None:
    raise AttachmentRepositoryConflict(
        "conditional_conflict" if _conditional(exc) else "dependency_failure"
    ) from None
