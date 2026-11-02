"""The conversation's own rows as a question reads them: the record, its messages.

#205 来取: these belong to the learning-session partition and move there with
#205. They sit here, apart from the question's own rows, only so the package
does not import the router (#218).
"""
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Protocol, cast

from boto3.dynamodb.conditions import Key

from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import attachment_repo
from stoa.models.attachment import AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import attachment_service
from stoa.services.ask_question.models import MessageQuote, _stored_quote


class _DynamoConversationTable(Protocol):
    def query(self, **kwargs: object) -> dict[str, object]: ...

    def get_item(self, **kwargs: object) -> dict[str, object]: ...


def _conversation_response_items(
    response: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list) or any(
        not isinstance(item, dict) for item in raw_items
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return [dict(cast(Mapping[str, object], item)) for item in raw_items]


def _conversation_response_item(
    response: Mapping[str, object],
) -> dict[str, object] | None:
    item = response.get("Item")
    if item is None:
        return None
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return dict(cast(Mapping[str, object], item))


def _conversation_grade(record: Mapping[str, object]) -> str:
    """The year group the conversation was opened for, which may be none yet.

    A grade is asked for on the learning profile, not when an account is opened,
    so a student an administrator opened has none and the console sends an empty
    one. Creation accepted it, every later read refused it, and the conversation
    existed in a state it could never be read out of: the assistant's reply
    failed with `upload_service_unavailable` on a request with no upload in it.

    Blank is safe downstream - a grade of whitespace produces a reply - so what
    was wrong was refusing here what the door accepted. A value of the wrong
    type is still refused.
    """
    value = record.get("grade")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _conv_pk(conv_id: str) -> str:
    return f"CONV#{conv_id}"


def _msg_sk(msg_id: str) -> str:
    return f"MSG#{msg_id}"


def _get_conversation(conv_id: str) -> dict | None:
    table = cast(_DynamoConversationTable, get_table())
    resp = table.get_item(Key={"PK": _conv_pk(conv_id), "SK": "CONV"})
    return _conversation_response_item(resp)


def _get_messages(conv_id: str) -> list[dict]:
    return _load_anchored_message_history(
        conversation_id=conv_id,
        owner_id=None,
        expected_message_ids=None,
        expected_fingerprint=None,
        table=get_table(),
    )


def _history_snapshot_fingerprint(messages: list[dict]) -> str:
    projection = [
        {
            "message_id": item["message_id"],
            "conversation_id": item["conversation_id"],
            "student_id": item["student_id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": item["created_at"],
        }
        for item in messages
    ]
    encoded = json.dumps(
        projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_history_message(
    item: Any, *, conversation_id: str, owner_id: str | None
) -> dict:
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    message_id = item.get("message_id")
    if (
        not isinstance(message_id, str)
        or not message_id
        or item.get("PK") != _conv_pk(conversation_id)
        or item.get("SK") != _msg_sk(message_id)
        or item.get("conversation_id") != conversation_id
        or (owner_id is not None and item.get("student_id") != owner_id)
        or not isinstance(item.get("student_id"), str)
        or not item["student_id"]
        or item.get("role") not in {"student", "assistant", "teacher", "system"}
        or not isinstance(item.get("content"), str)
        or not isinstance(item.get("created_at"), str)
        or not item["created_at"]
        or item.get("entity_type") != "conversation_message"
        or item.get("schema_version") != "conversation-message.v1"
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return item


def _load_anchored_message_history(
    *,
    conversation_id: str,
    owner_id: str | None,
    expected_message_ids: list[str] | None,
    expected_fingerprint: str | None,
    table,
) -> list[dict]:
    """Load one consistent bounded history and optionally prove an exact snapshot."""
    if expected_message_ids is not None and (
        any(not isinstance(value, str) or not value for value in expected_message_ids)
        or len(set(expected_message_ids)) != len(expected_message_ids)
        or not isinstance(expected_fingerprint, str)
        or len(expected_fingerprint) != 64
        or any(value not in "0123456789abcdef" for value in expected_fingerprint)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    items: list[dict] = []
    cursor = None
    for _page in range(64):
        request = {
            "KeyConditionExpression": (
                Key("PK").eq(_conv_pk(conversation_id))
                & Key("SK").begins_with("MSG#")
            ),
            "ScanIndexForward": True,
            "ConsistentRead": True,
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        response = table.query(**request)
        if not isinstance(response, dict) or not isinstance(response.get("Items", []), list):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        page = response.get("Items", [])
        items.extend(
            _validate_history_message(
                item, conversation_id=conversation_id, owner_id=owner_id
            )
            for item in page
        )
        if len(items) > 2_000:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            break
        if not isinstance(cursor, dict) or not cursor:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    else:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    ordered = sorted(items, key=lambda value: (value["created_at"], value["message_id"]))
    if expected_message_ids is None:
        if len({item["message_id"] for item in ordered}) != len(ordered):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        return ordered
    selected: dict[str, dict] = {}
    expected = set(expected_message_ids)
    for item in ordered:
        message_id = item["message_id"]
        if message_id not in expected:
            continue
        if message_id in selected:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        selected[message_id] = item
    if set(selected) != expected:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    snapshot = [selected[message_id] for message_id in expected_message_ids]
    if _history_snapshot_fingerprint(snapshot) != expected_fingerprint:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return snapshot


def _validate_replay_attachment(
    item: Any, *, attachment_id: str, owner_id: str
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    text_fields = (
        "immutable_object_key",
        "immutable_version_id",
        "immutable_etag",
        "detected_type",
        "original_filename",
    )
    checksum = item.get("content_sha256")
    source_fingerprint = item.get("source_fingerprint")
    if (
        item.get("PK") != attachment_repo.attachment_key(attachment_id)["PK"]
        or item.get("SK") != "META"
        or item.get("attachment_id") != attachment_id
        or item.get("owner_id") != owner_id
        or item.get("student_id") != owner_id
        or item.get("status") != "active"
        or item.get("entity_type") != "attachment"
        or item.get("schema_version") != "attachment.v1"
        or any(
            not isinstance(item.get(field), str) or not item[field]
            for field in text_fields
        )
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or any(value not in "0123456789abcdef" for value in checksum)
        or (stored_length := stored_int(item.get("content_length"))) is None
        or stored_length <= 0
        or (
            source_fingerprint is not None
            and (
                not isinstance(source_fingerprint, str)
                or len(source_fingerprint) != 64
                or any(value not in "0123456789abcdef" for value in source_fingerprint)
            )
        )
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return item


def _conversation_repository_call(
    operation, *, conflict_code: AttachmentErrorCode = AttachmentErrorCode.UPLOAD_NOT_FOUND
):
    """Keep conversation repository transport behind one closed public boundary."""
    try:
        return operation()
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentTransactionError as exc:
        code = {
            attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED: (
                AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
            ),
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY: (
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ),
            attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT: (
                conflict_code
            ),
        }[exc.outcome]
        raise AttachmentDecisionError(code) from None
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "dependency_failure":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        raise AttachmentDecisionError(conflict_code) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None


def _stored_student_message(
    *,
    conv_id: str,
    student_id: str,
    student_msg_id: str,
    created_at: str,
    expected_content: str | None,
    table: Any,
    expected_quote: MessageQuote | None = None,
) -> tuple[str, list, list[AttachmentSummary], MessageQuote | None]:
    """Read back a committed student message and its attachments, checked.

    Returns its content, the attachments as generation prepares them, their
    summaries and the quote stored with it. `expected_content` and
    `expected_quote` are the request's, when there is a request.
    """
    stored_student = _conversation_repository_call(
        lambda: table.get_item(
            Key={"PK": _conv_pk(conv_id), "SK": _msg_sk(student_msg_id)},
            ConsistentRead=True,
        ).get("Item")
    )
    if (
        not isinstance(stored_student, dict)
        or stored_student.get("PK") != _conv_pk(conv_id)
        or stored_student.get("SK") != _msg_sk(student_msg_id)
        or stored_student.get("entity_type") != "conversation_message"
        or stored_student.get("schema_version") != "conversation-message.v1"
        or stored_student.get("message_id") != student_msg_id
        or stored_student.get("conversation_id") != conv_id
        or stored_student.get("student_id") != student_id
        or stored_student.get("role") != "student"
        or not isinstance(stored_student.get("content"), str)
        or (
            expected_content is not None
            and stored_student.get("content") != expected_content
        )
        or stored_student.get("created_at") != created_at
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    raw_attachment_ids = stored_student.get("attachment_ids", [])
    if (
        not isinstance(raw_attachment_ids, list)
        or any(
            not isinstance(value, str) or not value
            for value in raw_attachment_ids
        )
        or len(set(raw_attachment_ids)) != len(raw_attachment_ids)
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    attachment_ids = list(raw_attachment_ids)
    stored_attachments = _conversation_repository_call(
        lambda: attachment_repo.get_attachments(attachment_ids, table=table)
    )
    if len(stored_attachments) != len(attachment_ids) or set(
        stored_attachments
    ) != set(attachment_ids):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
    prepared = [
        (
            "attachment",
            _validate_replay_attachment(
                stored_attachments[value],
                attachment_id=value,
                owner_id=student_id,
            ),
        )
        for value in attachment_ids
    ]
    attachments = attachment_service.attachment_summaries_for_records(
        attachment_ids, stored_attachments
    )
    raw_quote = stored_student.get("quote")
    quote = _stored_quote(raw_quote)
    if (raw_quote is not None and quote is None) or (
        expected_quote is not None and quote != expected_quote
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return str(stored_student["content"]), prepared, attachments, quote
