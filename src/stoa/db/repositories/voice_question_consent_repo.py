"""A child's "voice questions allowed" switch and the record of every change to it.

Both rows live in the student's own partition (`STUDENT#<student>`), which
account deletion already sweeps, and carry `student_id` so it takes them:

- `STUDENT#<student>/VOICE_QUESTIONS`: the switch as it stands - the value, and
  who changed it last and when.
- `STUDENT#<student>/VOICE_QUESTIONS_CHANGE#<changed_at>#<change_id>`: one row
  per change, never rewritten. This is the consent record.

The rows avoid `created_at`: GSI-StudentId is keyed on (student_id,
created_at), and a row carrying both would show up in the index that lists a
student's questions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from boto3.dynamodb.conditions import Key

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, parent_link_repo


ENTITY_TYPE: Final = "voice_question_consent"
CHANGE_ENTITY_TYPE: Final = "voice_question_consent_change"

STATE_SK: Final = "VOICE_QUESTIONS"
CHANGE_SK_PREFIX: Final = "VOICE_QUESTIONS_CHANGE#"


class VoiceConsentConflict(RuntimeError):
    """The change lost to a closed relationship or an account being deleted."""


def _partition(student_id: str) -> str:
    if not isinstance(student_id, str) or not student_id.strip():
        raise ValueError("student_id is required")
    return f"STUDENT#{student_id}"


def state_key(student_id: str) -> dict[str, str]:
    return {"PK": _partition(student_id), "SK": STATE_SK}


def change_key(student_id: str, changed_at: str, change_id: str) -> dict[str, str]:
    return {"PK": _partition(student_id), "SK": f"{CHANGE_SK_PREFIX}{changed_at}#{change_id}"}


def get_state(student_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    """The switch as stored, or `None` when no parent has ever changed it."""
    item = db_table.get(
        table=table or db_table.table(), Key=state_key(student_id), ConsistentRead=True
    )
    if item is None or item.get("entity_type") != ENTITY_TYPE:
        return None
    return item


def list_changes(student_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    """Every recorded change, oldest first."""
    rows: list[dict[str, Any]] = []
    for page in db_table.pages(
        "query",
        table=table or db_table.table(),
        KeyConditionExpression=Key("PK").eq(_partition(student_id))
        & Key("SK").begins_with(CHANGE_SK_PREFIX),
        ConsistentRead=True,
    ):
        rows.extend(row for row in page.items if row.get("entity_type") == CHANGE_ENTITY_TYPE)
    return rows


def _link_still_current(
    key: Mapping[str, str], relationship_version: str
) -> dict[str, Any]:
    return {
        "ConditionCheck": {
            "Key": dict(key),
            "ConditionExpression": (
                "attribute_exists(PK) AND #status = :expected_status"
                " AND link_updated_at = :expected_link_updated_at"
            ),
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {
                ":expected_status": parent_link_repo.STATUS_ACTIVE,
                ":expected_link_updated_at": relationship_version,
            },
        }
    }


def record_change(
    *,
    student_id: str,
    parent_id: str,
    allowed: bool,
    changed_at: str,
    change_id: str,
    relationship_version: str,
    table: Any | None = None,
) -> dict[str, Any]:
    """Set the switch and record the change, in one transaction.

    The last change wins: the state row is overwritten without a condition on
    what it held. The write holds only while both link rows still stand at the
    version the parent was authorized on, and while both accounts are writable,
    so a parent whose relationship was closed in between cannot slip a change in.
    """
    if not isinstance(allowed, bool):
        raise ValueError("allowed must be a boolean")
    if not relationship_version:
        raise ValueError("relationship_version is required")
    body = {
        "student_id": student_id,
        "allowed": allowed,
        "changed_by": parent_id,
        "changed_at": changed_at,
    }
    state = {**state_key(student_id), "entity_type": ENTITY_TYPE, **body}
    change = {
        **change_key(student_id, changed_at, change_id),
        "entity_type": CHANGE_ENTITY_TYPE,
        "change_id": change_id,
        **body,
    }
    operations = [
        _link_still_current(
            parent_link_repo.parent_side_key(parent_id, student_id), relationship_version
        ),
        _link_still_current(
            parent_link_repo.student_side_key(student_id, parent_id), relationship_version
        ),
        {"Put": {"Item": state}},
        {
            "Put": {
                "Item": change,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        },
    ]
    try:
        db_table.fenced(
            student_id,
            operations,
            also={parent_id: None},
            table=table or db_table.table(),
        )
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise VoiceConsentConflict("an account is not writable") from exc
    except db_table.WriteRefused as exc:
        raise VoiceConsentConflict("the relationship changed") from exc
    return state
