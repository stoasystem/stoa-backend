"""A session's messages as they are read back: checked, ordered, typed.

Moved from the question package's transcript module (#226). `_validate_history_message` is
still the read side's check on every row; step 2 of #205 makes it the append's
invariant and leaves a defensive check for older rows here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services.learning_session import _store
from stoa.services.learning_session._store import conv_pk, msg_sk

Role = Literal["student", "assistant", "teacher", "system"]


@dataclass(frozen=True, slots=True)
class Message:
    """One stored message of a learning session, whoever wrote it.

    The student API's `ChatMessage` and the teacher API's `MessageOut` are both
    built from it. `quote` and `structured` are as stored; each view parses
    what it shows.
    """

    id: str
    conversation_id: str
    student_id: str
    role: Role
    content: str
    created_at: str
    status: str = "sent"
    attachment_ids: tuple[str, ...] = ()
    # A teacher's reply: who wrote it, as named when it was written (#65), and
    # its rich content.
    author_name: str | None = None
    teacher_response_rich: Mapping[str, object] | None = None
    teacher_response_format: str | None = None
    # A student's message: what it quotes. An assistant's: its sections and the
    # unit it points to.
    quote: object = None
    structured: object = None
    target_unit_id: str | None = None
    # A system message: which event wrote it.
    system_event: str | None = None


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def message_from_row(row: Mapping[str, Any]) -> Message:
    """The typed message for a row `_validate_history_message` accepted."""
    raw_ids = row.get("attachment_ids", [])
    rich = row.get("teacher_response_rich")
    return Message(
        id=row["message_id"],
        conversation_id=row["conversation_id"],
        student_id=row["student_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        attachment_ids=tuple(str(value) for value in raw_ids)
        if isinstance(raw_ids, list)
        else (),
        author_name=_optional_text(row.get("author_name")),
        teacher_response_rich=dict(rich) if isinstance(rich, Mapping) else None,
        teacher_response_format=_optional_text(row.get("teacher_response_format")),
        quote=row.get("quote"),
        structured=row.get("structured"),
        target_unit_id=_optional_text(row.get("target_unit_id")),
        system_event=_optional_text(row.get("system_event")),
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
        or item.get("PK") != conv_pk(conversation_id)
        or item.get("SK") != msg_sk(message_id)
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
        response = _store.message_page(conversation_id, cursor)
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
