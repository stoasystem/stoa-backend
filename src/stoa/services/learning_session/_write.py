"""Appending a message to a learning session, and the row contract it keeps.

Every message row of a session is made here (#227, step 2 of #205): the
student's question, the assistant's answer, a teacher's reply and the system
message that opens a help request. `append` builds the row and returns the
conditional put that writes it, for the caller's own transaction; it does not
touch the table.

`validate_message_row` is the row contract. `append` holds every row it makes
to it, so a row written here always reads back; the readers in `_history` keep
calling it as a defensive check on rows written before this module wrote them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services.learning_session._store import conv_pk, msg_sk

Role = Literal["student", "assistant", "teacher", "system"]

ENTITY_TYPE = "conversation_message"
SCHEMA_VERSION = "conversation-message.v1"
ROLES: frozenset[str] = frozenset({"student", "assistant", "teacher", "system"})

# The keyword arguments each role takes, and which of them it must be given.
_ROLE_FIELDS: dict[str, frozenset[str]] = {
    "student": frozenset({"attachment_ids", "quote"}),
    "assistant": frozenset({"structured", "target_unit_id", "allowance"}),
    "teacher": frozenset(
        {"teacher_response_rich", "teacher_response_format", "author_name", "attachment_ids"}
    ),
    "system": frozenset({"system_event", "escalation_message"}),
}
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "student": frozenset({"attachment_ids"}),
    "assistant": frozenset({"structured"}),
    "teacher": frozenset({"teacher_response_rich", "teacher_response_format"}),
    "system": frozenset({"system_event"}),
}

_NEW_ROW_CONDITION = "attribute_not_exists(PK) AND attribute_not_exists(SK)"


def validate_message_row(
    item: Any, *, conversation_id: str, owner_id: str | None
) -> dict:
    """The row, if it is a message of this session (and `owner_id`'s, when given).

    Refused with `UPLOAD_SERVICE_UNAVAILABLE` otherwise.
    """
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
        or item.get("role") not in ROLES
        or not isinstance(item.get("content"), str)
        or not isinstance(item.get("created_at"), str)
        or not item["created_at"]
        or item.get("entity_type") != ENTITY_TYPE
        or item.get("schema_version") != SCHEMA_VERSION
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return item


def _id_list(value: object, *, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of ids")
    return list(value)


def append(
    conversation_id: str,
    *,
    role: Role,
    message_id: str,
    student_id: str,
    generation: int,
    content: str,
    created_at: str,
    **fields: object,
) -> dict[str, object]:
    """The put that appends one message, written by `role`, to the session.

    Returns `{"Put": {...}}` for the caller's transaction, conditional on the
    row not existing yet. It is not fenced on its own: every transaction a
    message is written in already checks the student's account fence once
    (`db_table.fenced(student_id, ..., generation=generation)`), and the row is
    stamped with that `generation`.

    The row is stamped with its key, the schema, the student as owner and the
    fence generation. Each role takes its own keyword arguments, refused for
    any other role (`ValueError`):

    - student: `attachment_ids` (required, stored as a list also when empty),
      `quote` (stored when not `None`).
    - assistant: `structured` (required, stored as given), `target_unit_id`
      (stored when set), `allowance` (its keys merged into the row; a key the
      row already has is refused).
    - teacher: `teacher_response_rich` and `teacher_response_format`
      (required), `author_name` (stored stripped, when it is non-blank text),
      `attachment_ids` (stored when given).
    - system: `system_event` (required), `escalation_message` (always stored,
      also when `None`).

    A student id that is empty or a generation that is not a positive int is
    refused as `AttachmentRepositoryConflict`, as the session's other fenced
    writes refuse it.
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")
    unexpected = set(fields) - _ROLE_FIELDS[role]
    if unexpected:
        raise ValueError(f"{role} message does not take {sorted(unexpected)}")
    missing = _REQUIRED_FIELDS[role] - set(fields)
    if missing:
        raise ValueError(f"{role} message requires {sorted(missing)}")
    if (
        not isinstance(student_id, str)
        or not student_id
        or type(generation) is not int
        or generation <= 0
    ):
        raise AttachmentRepositoryConflict("conditional_conflict")

    row: dict[str, object] = {
        "PK": conv_pk(conversation_id),
        "SK": msg_sk(message_id),
        "entity_type": ENTITY_TYPE,
        "schema_version": SCHEMA_VERSION,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "student_id": student_id,
        "owner_id": student_id,
        "account_fence_generation": generation,
        "role": role,
        "content": content,
        "created_at": created_at,
    }
    if role == "student":
        row["attachment_ids"] = _id_list(fields["attachment_ids"], field="attachment_ids")
        if fields.get("quote") is not None:
            row["quote"] = fields["quote"]
    elif role == "assistant":
        row["structured"] = fields["structured"]
        if fields.get("target_unit_id"):
            row["target_unit_id"] = fields["target_unit_id"]
        allowance = fields.get("allowance")
        if allowance is not None:
            if not isinstance(allowance, Mapping):
                raise ValueError("allowance must be a mapping")
            colliding = set(allowance) & set(row)
            if colliding:
                raise ValueError(f"allowance may not set {sorted(colliding)}")
            row.update(allowance)
    elif role == "teacher":
        row["teacher_response_rich"] = fields["teacher_response_rich"]
        row["teacher_response_format"] = fields["teacher_response_format"]
        author_name = fields.get("author_name")
        if isinstance(author_name, str) and author_name.strip():
            row["author_name"] = author_name.strip()
        if fields.get("attachment_ids") is not None:
            row["attachment_ids"] = _id_list(fields["attachment_ids"], field="attachment_ids")
    else:
        row["system_event"] = fields["system_event"]
        row["escalation_message"] = fields.get("escalation_message")

    validate_message_row(row, conversation_id=conversation_id, owner_id=student_id)
    return {"Put": {"Item": row, "ConditionExpression": _NEW_ROW_CONDITION}}
