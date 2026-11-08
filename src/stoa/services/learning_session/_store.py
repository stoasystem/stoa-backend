"""The learning session's rows on the table: its record and its messages.

The only module that reaches the table for `CONV#{id}`/`CONV` and
`CONV#{id}`/`MSG#…` rows (#226, step 1 of #205). The record's fenced writes
moved here from `attachment_repo` with their bodies unchanged; the reads moved
from the question package's transcript module, `routers/teachers.py`, `moderation_service`,
`teacher_assistance_service` and `upload_code_repo`, each of which queried the
partition itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from boto3.dynamodb.conditions import Key

from stoa.db import table as db_table
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode

RECORD_SORT_KEY = "CONV"
MESSAGE_PREFIX = "MSG#"


def conv_pk(conv_id: str) -> str:
    return f"CONV#{conv_id}"


def msg_sk(msg_id: str) -> str:
    return f"{MESSAGE_PREFIX}{msg_id}"


def record_key(conversation_id: str) -> dict[str, str]:
    return {"PK": conv_pk(conversation_id), "SK": RECORD_SORT_KEY}


def table() -> Any:
    """The table the session's rows live on, for a transaction that spans them."""
    return get_table()


# ── Reads ─────────────────────────────────────────────────────────────────────


def get_record(conversation_id: str) -> dict[str, object] | None:
    """The record, read strongly; `None` when there is none."""
    response = get_table().get_item(Key=record_key(conversation_id), ConsistentRead=True)
    if not isinstance(response, Mapping):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    item = response.get("Item")
    if item is None:
        return None
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return dict(item)


def get_message(conversation_id: str, message_id: str) -> object:
    """One message row as stored, read strongly; `None` when there is none."""
    return get_table().get_item(
        Key={"PK": conv_pk(conversation_id), "SK": msg_sk(message_id)},
        ConsistentRead=True,
    ).get("Item")


def message_page(conversation_id: str, cursor: object | None) -> object:
    """One page of the message rows, strongly read, ascending by sort key."""
    request: dict[str, object] = {
        "KeyConditionExpression": (
            Key("PK").eq(conv_pk(conversation_id))
            & Key("SK").begins_with("MSG#")
        ),
        "ScanIndexForward": True,
        "ConsistentRead": True,
    }
    if cursor is not None:
        request["ExclusiveStartKey"] = cursor
    return get_table().query(**request)


# ── Fenced writes of the record (moved from attachment_repo) ──────────────────


def build_conversation_write_transaction(
    *,
    item: dict[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
) -> list[dict[str, object]]:
    """Build one owner-stamped conversation write behind the permanent fence.

    Message rows no longer go through it: `append` (in `_write`) makes them.
    """
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
    if not db_table.transactional(target) and hasattr(target, "put_item") and mode == "put":
        # Narrow compatibility for inherited in-memory fakes. Production tables
        # always execute the two-item transaction above.
        put = attachment_repo._mapping(operations[1].get("Put"))
        attachment_repo._put_item(target, Item=attachment_repo._mapping(put.get("Item")))
    else:
        try:
            db_table.transact(operations, table=target)
        except (db_table.WriteRefused, db_table.TableUnavailable) as exc:
            raise AttachmentRepositoryConflict("conditional_conflict") from exc
    return attachment_repo._mapping(attachment_repo._mapping(operations[1].get("Put")).get("Item"))


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


def owns_conversation(
    conversation_id: str, owner_id: str, *, table: object | None = None
) -> bool:
    """Whether this learning session exists, is the owner's own, and is not deleted."""
    target = table or get_table()
    item = attachment_repo._optional_mapping(
        attachment_repo._get_item(
            target,
            Key={"PK": f"CONV#{conversation_id}", "SK": "CONV"},
            ConsistentRead=True,
        ).get("Item")
    )
    return (
        item is not None
        and item.get("entity_type") == "conversation"
        and item.get("student_id") == owner_id
        and item.get("status") != "deleted"
    )


def retitle_conversation(
    conversation_id: str,
    *,
    title: str,
    expected_title: str,
    now_iso: str,
    table: object | None = None,
) -> bool:
    """Replace a conversation's placeholder title with the question it holds.

    Conditional on the placeholder still being present, so a title a student
    chose is never overwritten. Returns whether the title was adopted.
    """
    target = table or get_table()
    update_item = getattr(target, "update_item", None)
    if not callable(update_item):
        return False
    try:
        update_item(
            Key={"PK": f"CONV#{conversation_id}", "SK": "CONV"},
            UpdateExpression="SET title=:title, updated_at=:now",
            ConditionExpression="title=:expected",
            ExpressionAttributeValues={
                ":title": title,
                ":expected": expected_title,
                ":now": now_iso,
            },
        )
    except Exception:
        return False
    return True
