"""A learning session: a student's conversation, its record and its messages.

The partition `CONV#{id}` holds the record (`SK=CONV`) and the messages
(`SK=MSG#…`) every role writes. The package is being given its one owner in
three steps (#205). Step 1 (#226) moved the reads and the record here: the
conversation reads from the question package's transcript module (now gone), the
message queries of the teacher routes, moderation and the AI teacher tools, the
record read of the phone upload codes, and the record's fenced writes from
`attachment_repo`. `_store` is the only module that reaches the table for these
rows. Step 2 (#205) moves the message writers here. The entry points:

- `open` starts a session for a student behind their account fence and returns
  its stored record.
- `read` is the record, or `None`; `owned_by` says whether it is the student's.
- `retitle` replaces a placeholder title.
- `history` is every message, oldest first, as `Message` values; the student's
  `ChatMessage` and the teacher's `MessageOut` are built from them.
- `history_rows` and `anchored_history` are the question's: the checked rows
  it fingerprints, and the exact snapshot a committed command names.

A record or message the session cannot be read back from raises
`AttachmentDecisionError` (`UPLOAD_SERVICE_UNAVAILABLE`).
"""

import uuid
from collections.abc import Mapping
from typing import Any, Protocol, cast

from stoa.db.repositories import account_deletion_repo
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services.learning_session import _history, _store
from stoa.services.learning_session._history import Message, Role, message_from_row
from stoa.services.learning_session._store import (
    build_conversation_write_transaction,
    conv_pk,
    msg_sk,
)

__all__ = [
    "DynamoConversationTable",
    "Message",
    "Role",
    "active_conversation_generation",
    "anchored_history",
    "build_conversation_write_transaction",
    "conv_pk",
    "conversation_grade",
    "conversation_response_items",
    "history",
    "history_fingerprint",
    "history_rows",
    "message_from_row",
    "msg_sk",
    "open",
    "owned_by",
    "read",
    "required_conversation_text",
    "retitle",
    "stored_message",
]


class DynamoConversationTable(Protocol):
    def query(self, **kwargs: object) -> dict[str, object]: ...

    def get_item(self, **kwargs: object) -> dict[str, object]: ...


# ── The record ───────────────────────────────────────────────────────────────


def active_conversation_generation(owner_id: str, table: Any) -> int:
    """Resolve one exact active generation before a private conversation effect."""
    try:
        fence = account_deletion_repo.require_active_account_fence(owner_id, table=table)
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    return int(fence["generation"])


def open(
    student_id: str, *, subject: str, grade: str, title: str, now: str
) -> dict[str, object]:
    """Start a session for the student, behind their account fence.

    Returns the record as stored: owner-stamped, with the fence generation it
    was written under in `account_fence_generation`. A student whose account
    is being deleted is refused (`UPLOAD_NOT_FOUND`).
    """
    conversation_id = str(uuid.uuid4())
    table = _store.table()
    record: dict[str, object] = {
        **_store.record_key(conversation_id),
        "conversation_id": conversation_id,
        "student_id": student_id,
        "entity_type": "conversation",
        "subject": subject,
        "grade": grade,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    generation = active_conversation_generation(student_id, table)
    return _store.create_conversation_record(
        record,
        owner_id=student_id,
        generation=generation,
        table=table,
    )


def read(conversation_id: str) -> dict | None:
    """The session's record, read strongly; `None` when there is none."""
    return _store.get_record(conversation_id)


def owned_by(conversation_id: str, student_id: str) -> bool:
    """Whether this learning session exists and is the student's own."""
    return _store.owns_conversation(conversation_id, student_id)


def retitle(conversation_id: str, *, title: str, expected_title: str, now_iso: str) -> bool:
    """Replace the title if it is still `expected_title`; whether it was."""
    return _store.retitle_conversation(
        conversation_id, title=title, expected_title=expected_title, now_iso=now_iso
    )


def conversation_response_items(
    response: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list) or any(
        not isinstance(item, dict) for item in raw_items
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return [dict(cast(Mapping[str, object], item)) for item in raw_items]


def required_conversation_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def conversation_grade(record: Mapping[str, object]) -> str:
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


# ── The messages ─────────────────────────────────────────────────────────────


def history(conversation_id: str) -> list[Message]:
    """Every message of the session, oldest first, each row checked.

    Read strongly, every page, ordered by `created_at` then id.
    """
    return [message_from_row(row) for row in history_rows(conversation_id)]


def history_rows(conversation_id: str) -> list[dict]:
    """The checked rows `history` is made of, as the question fingerprints them."""
    return _history._load_anchored_message_history(
        conversation_id=conversation_id,
        owner_id=None,
        expected_message_ids=None,
        expected_fingerprint=None,
    )


def anchored_history(
    conversation_id: str,
    *,
    owner_id: str,
    message_ids: list[str],
    fingerprint: str,
) -> list[dict]:
    """Exactly the rows `message_ids` names, in that order, proven by `fingerprint`.

    Every row must be `owner_id`'s; a row missing, repeated or changed since
    the fingerprint was taken is refused.
    """
    return _history._load_anchored_message_history(
        conversation_id=conversation_id,
        owner_id=owner_id,
        expected_message_ids=message_ids,
        expected_fingerprint=fingerprint,
    )


def history_fingerprint(rows: list[dict]) -> str:
    """The fingerprint `anchored_history` proves a snapshot of `rows` by."""
    return _history._history_snapshot_fingerprint(rows)


def stored_message(conversation_id: str, message_id: str) -> object:
    """One message row as stored, unchecked; `None` when there is none."""
    return _store.get_message(conversation_id, message_id)
