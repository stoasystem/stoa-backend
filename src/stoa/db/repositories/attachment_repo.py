"""Conditional single-table persistence for attachments; upload rows are `uploads._store`'s."""

from __future__ import annotations

import base64
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


logger = logging.getLogger(__name__)

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


class _DynamoMeta(Protocol):
    client: _DynamoClient


@runtime_checkable
class _DynamoTable(Protocol):
    name: str
    meta: _DynamoMeta


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


def _storage_quota_condition(limit_bytes: int, size: int) -> tuple[str, int]:
    """Ask "does this file still fit" in a dialect the provider actually has.

    DynamoDB allows arithmetic only in an UpdateExpression's SET, so
    `used_bytes+:size<=:limit` is a syntax error in a condition. Every attempt
    to attach a file to a message was answered 503 by it, which is why the
    production table has never held a single attachment row. The question is
    the same with the addition done here instead.

    A file larger than the whole quota leaves no headroom at all, and then the
    owner having no usage row yet must not be what lets it through.
    """
    headroom = limit_bytes - size
    if headroom < 0:
        return "used_bytes<=:headroom", headroom
    return "attribute_not_exists(used_bytes) OR used_bytes<=:headroom", headroom


def _failure_site() -> str:
    """Name the frame that raised, since `from None` removes the traceback."""
    try:
        frame = sys._getframe(3)
    except ValueError:
        return "unknown"
    return f"{frame.f_code.co_name}:{frame.f_lineno}"


def _failure_cause() -> tuple[str, str]:
    """The in-flight exception's class and the provider's own code, never more.

    A provider error carries account coordinates in its message, so only the
    `Error.Code` is taken; anything else is reported by class name alone.
    """
    cause = sys.exception()
    if cause is None:
        return "none", "raised"
    # The gateway's outcomes carry the provider's error as their cause.
    provider = (
        cause.__cause__
        if isinstance(cause, (db_table.WriteRefused, db_table.TableUnavailable))
        else cause
    )
    response = getattr(provider, "response", None)
    if isinstance(provider, ClientError) and isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            code = str(error.get("Code") or "unknown")
            # A validation failure means the request itself was wrong, and
            # which rule it broke is only ever in the provider's own words.
            if code == "ValidationException":
                return (
                    type(cause).__name__,
                    f"{code}: {db_table.safe_validation_message(provider)}",
                )
            return type(cause).__name__, code
    if isinstance(cause, (db_table.WriteRefused, db_table.TableUnavailable)):
        return type(cause).__name__, cause.code
    return type(cause).__name__, "-"


@dataclass(frozen=True, slots=True)
class AttachmentRepositoryConflict(Exception):
    """A conflict the caller is told about as `upload_service_unavailable`.

    Forty-odd sites raise this with `from None`, and that is right for the
    student - a provider's words are not an answer to give them - but it left
    an operator nothing at all. Production ran for months with no application
    log line from this module, so a 503 here could not be told apart from any
    other 503. The cause is still in flight while this is constructed, so it
    is recorded once here instead of at every site.
    """

    category: str = "conditional_conflict"

    def __post_init__(self) -> None:
        cause, detail = _failure_cause()
        # A conditional conflict is ordinary control flow - an idempotent
        # replay losing a race - and saying so at WARNING would bury the
        # dependency failures, which are the ones nobody can otherwise see.
        log = logger.warning if self.category == "dependency_failure" else logger.info
        log(
            "attachment_repository_conflict category=%s site=%s cause=%s detail=%s",
            self.category,
            _failure_site(),
            cause,
            detail,
        )


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
    MESSAGE_COMMAND_PUT = "message_command_put"
    CHAT_QUOTA_OPERATION_PUT = "chat_quota_operation_put"
    CHAT_QUOTA_UPDATE = "chat_quota_update"
    CHAT_QUOTA_OPERATION_DELETE = "chat_quota_operation_delete"
    CHAT_QUOTA_COMPENSATE = "chat_quota_compensate"
    USAGE_EVENT_PUT = "usage_event_put"
    MESSAGE_COMMAND_UPDATE = "message_command_update"
    MESSAGE_COMMAND_REJECT = "message_command_reject"
    ASSISTANT_MESSAGE_PUT = "assistant_message_put"
    KNOWLEDGE_GAP_UPDATE = "knowledge_gap_update"
    ASKED_KNOWLEDGE_PUT = "asked_knowledge_put"
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

    def __post_init__(self) -> None:
        cause, detail = _failure_cause()
        logger.warning(
            "attachment_transaction_failed outcome=%s site=%s cause=%s detail=%s",
            self.outcome,
            _failure_site(),
            cause,
            detail,
        )


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
        # What a new Ask question asked about (#143).
        "asked_knowledge_points",
        # The conversation's request for a teacher (#189).
        "help_request",
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
        "ai_failure",
        "ai_invocation_record",
        "ai_result_record",
        "generation_context_record",
        "allowance_settlement",
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
        "generation_context",
        "provider_result_json",
        "knowledge_points",
        "unit_ids",
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
CONVERSATION_PROVIDER_RETENTION_BOUNDARY = {
    "bedrock_request_response": "outside_backend_deletion_control"
}


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


def association_key(
    attachment_id: str, resource_type: str, resource_id: str, message_id: str
) -> dict[str, str]:
    return {
        "PK": f"ATTACHMENT#{attachment_id}",
        "SK": f"REF#{resource_type.upper()}#{resource_id}#MESSAGE#{message_id}",
    }


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
    # A tombstone keeps its owner, so without this the deletion branch found
    # its own tombstones on every pass, never had a clean one, and a student
    # with a conversation could never be deleted (stoasystem/stoa-backend#78).
    if account_deletion_repo.is_deletion_tombstone(item):
        return False
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
            db_table.transact(operations, table=target)
        except (db_table.WriteRefused, db_table.TableUnavailable) as exc:
            raise AttachmentRepositoryConflict("conditional_conflict") from exc
    return tombstone


def _require_provider_coordinate(value: object) -> str:
    """Reject malformed provider success coordinates before state can advance."""
    if not isinstance(value, str) or not value.strip():
        raise AttachmentRepositoryConflict("invalid_provider_coordinate")
    return value


def _require_positive_integer(value: object) -> int:
    # Applied to stored part numbers and lengths as well as caller-supplied ones,
    # and DynamoDB returns every stored number as Decimal.
    if isinstance(value, bool):
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    if isinstance(value, int):
        result = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        result = int(value)
    else:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    if result <= 0:
        raise AttachmentRepositoryConflict("invalid_provider_acknowledgement")
    return result


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


def get_attachment(attachment_id: str, *, table: object | None = None) -> dict[str, object] | None:
    response = _get_item(table or get_table(),
        Key=attachment_key(attachment_id), ConsistentRead=True
    )
    return _optional_mapping(response.get("Item"))


# BatchGetItem reads at most this many keys in one call.
_BATCH_GET_KEY_LIMIT = 100


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
    if len(attachment_ids) > _BATCH_GET_KEY_LIMIT:
        found: dict[str, dict[str, object]] = {}
        for start in range(0, len(attachment_ids), _BATCH_GET_KEY_LIMIT):
            found.update(
                get_attachments(
                    attachment_ids[start : start + _BATCH_GET_KEY_LIMIT], table=target
                )
            )
        return found
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
                response = _mapping(db_table.client().batch_get_item(
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


OWNER_INDEX_MAX_PAGES = 100


def _owner_index_attachments(owner_id: str, *, table: object) -> list[dict[str, object]]:
    """Every attachment row GSI-StudentId holds for `owner_id`, across its pages.

    The owner's partition also holds their messages, usage events and uploads; the
    filter drops those after they are read, so reading on until the index runs out
    is what finds every attachment.
    """
    from boto3.dynamodb.conditions import Attr, Key

    request: dict[str, object] = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": Key("student_id").eq(owner_id),
        "FilterExpression": Attr("entity_type").eq("attachment"),
    }
    result: list[dict[str, object]] = []
    seen_cursors: set[tuple[tuple[str, str], ...]] = set()
    for _page in range(OWNER_INDEX_MAX_PAGES):
        try:
            response = _query(table, **request)
        except AttachmentRepositoryConflict:
            raise
        except Exception:
            raise AttachmentRepositoryConflict("dependency_failure") from None
        raw_items = response.get("Items", [])
        if not isinstance(raw_items, list):
            raise AttachmentRepositoryConflict("dependency_failure")
        result.extend(_mapping(raw_item) for raw_item in raw_items)
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            return result
        if not isinstance(cursor, dict) or not cursor:
            raise AttachmentRepositoryConflict("dependency_failure")
        identity = tuple(sorted((str(key), str(value)) for key, value in cursor.items()))
        if identity in seen_cursors:
            raise AttachmentRepositoryConflict("dependency_failure")
        seen_cursors.add(identity)
        request["ExclusiveStartKey"] = cursor
    raise AttachmentRepositoryConflict("dependency_failure")


def list_saved_attachments(
    owner_id: str,
    *,
    limit: int,
    exclusive_start_key: dict[str, str] | None = None,
    table: object | None = None,
) -> tuple[list[dict[str, object]], dict[str, str] | None]:
    """Return a stable page of the owner's active attachments, read from GSI-StudentId.

    Every attachment row carries `student_id` = `owner_id` and `created_at`, so the
    index holds them under the owner. This used to be the exhaustive consistent scan
    retention needs, which reads the whole shared table and gives up past 10,000
    rows, so the list answered 503 in production (#136). The index is
    eventually consistent, which a listing can afford; detail, download and delete
    still read the base table strongly.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise AttachmentRepositoryConflict("conditional_conflict")
    if exclusive_start_key is not None and (
        not isinstance(exclusive_start_key, dict)
        or set(exclusive_start_key) != {"attachment_id"}
        or not isinstance(exclusive_start_key.get("attachment_id"), str)
        or not exclusive_start_key["attachment_id"]
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    items = _owner_index_attachments(owner_id, table=table or get_table())
    active: list[tuple[str, AttachmentItem]] = []
    for item in items:
        attachment_id = item.get("attachment_id")
        if (
            item.get("owner_id") == owner_id
            and item.get("status") == "active"
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
    message_put: dict[str, object],
    fresh: list[tuple[dict[str, object], dict[str, object]]],
    reused: list[dict[str, object]],
    associations: list[dict[str, object]],
    owner_id: str,
    limit_bytes: int,
    now_iso: str,
    trailing_operations: Sequence[TransactionOperation] = (),
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
    # The message's own put, as `learning_session.append` made it (#227).
    operations.append(TransactionOperation(TransactionOperationKind.MESSAGE_PUT, message_put))
    # Each fresh attachment rides with the consume of the upload it was made
    # from, as `uploads.consume_operation` builds it.
    for consume, attachment in fresh:
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.extend(
            [
                TransactionOperation(TransactionOperationKind.UPLOAD_CONSUME, consume),
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
                        "ConditionExpression": _storage_quota_condition(
                            limit_bytes, fresh_bytes
                        )[0],
                        "ExpressionAttributeValues": {
                            ":zero": 0,
                            ":size": fresh_bytes,
                            ":limit": limit_bytes,
                            ":headroom": _storage_quota_condition(
                                limit_bytes, fresh_bytes
                            )[1],
                            ":updated": now_iso,
                        },
                    }
                },
            )
        )
    # What the message's owner writes with it (a question's own rows), built by
    # that owner; they go last.
    operations.extend(trailing_operations)
    return operations


def build_reply_image_operations(
    *,
    fresh: list[tuple[dict[str, object], dict[str, object]]],
    associations: list[dict[str, object]],
    owner_id: str,
    account_fence_generation: int,
    conversation_id: str,
    now_iso: str,
) -> list[dict[str, object]]:
    """A teacher's reply images, as part of the reply's own transaction (#145).

    Each upload is consumed under its uploader, the teacher (the caller passes
    the `uploads.consume_operation` for it), and handed with
    the attachment it becomes to the owner, the student whose conversation it
    is: the upload row's cleanup belongs with the attachment it points at.
    Left the teacher's, it would hold the teacher's account deletion forever,
    since the teacher's purge can neither clean it nor see the attachment that
    keeps it. The student's account fence is the reply's to check: one
    transaction cannot check a row twice. The owner's usage grows by the
    images, but the owner's quota does not refuse them: a teacher cannot free
    a student's storage.
    """
    operations: list[dict[str, object]] = [
        {
            "ConditionCheck": {
                "Key": retention_fence_key(
                    owner_id, resource_type="conversation", resource_id=conversation_id
                ),
                "ConditionExpression": "attribute_not_exists(PK) OR #status=:complete",
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": {":complete": "complete"},
            }
        }
    ]
    for consume, attachment in fresh:
        attachment_id = _required_text(attachment.get("attachment_id"))
        operations.append(consume)
        operations.append(
            {
                "Put": {
                    "Item": {**attachment_key(attachment_id), **attachment},
                    "ConditionExpression": "attribute_not_exists(PK)",
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
    if fresh:
        operations.append(
            {
                "Update": {
                    "Key": storage_key(owner_id),
                    "UpdateExpression": (
                        "SET used_bytes=if_not_exists(used_bytes,:zero)+:size, updated_at=:updated"
                    ),
                    "ExpressionAttributeValues": {
                        ":zero": 0,
                        ":size": sum(
                            _require_positive_integer(attachment.get("content_length"))
                            for _, attachment in fresh
                        ),
                        ":updated": now_iso,
                    },
                }
            }
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
    if (
        not isinstance(item, dict)
        or item.get("owner_id") != owner_id
        or item.get("status") != "active"
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")
    # The stored generation arrives as Decimal, so it goes through the normalizer.
    _required_integer(item.get("generation"), minimum=1)
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
        db_table.transact(transact_items, table=target)
    except db_table.WriteRefused as exc:
        if described:
            raise AttachmentTransactionError(
                _attachment_transaction_outcome(exc, described_operations)
            ) from None
        raise AttachmentRepositoryConflict() from None
    except Exception:
        if described:
            raise AttachmentTransactionError(
                AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY
            ) from None
        raise AttachmentRepositoryConflict("dependency_failure") from None


def _attachment_transaction_outcome(
    refused: db_table.WriteRefused, operations: list[TransactionOperation]
) -> AttachmentTransactionOutcome:
    """Classify from the table's per-operation reasons and the operations' kinds only.

    Provider messages, items, keys, and exception text intentionally never cross
    this function's boundary.
    """
    if refused.code == "ConditionalCheckFailedException":
        return AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT
    if not refused.reasons:
        return AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY

    conditional_kinds: list[TransactionOperationKind] = []
    for operation, reason in zip(operations, refused.reasons, strict=True):
        if reason.kind is db_table.ReasonKind.NOT_THE_CAUSE:
            continue
        if reason.kind is db_table.ReasonKind.CONDITION_FAILED:
            conditional_kinds.append(operation.kind)
            continue
        # Every other reason is answered "try again": a transaction conflict or
        # a capacity limit passes, and for a reason that will not (`OTHER`:
        # ValidationError, or a code nobody has named) the client still has
        # nothing better to do. The gateway has logged that one as an error,
        # which is where a request that can never succeed gets noticed (#271).
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
