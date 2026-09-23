"""Parent-student links stored in both directions, written as one transaction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from boto3.dynamodb.conditions import Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


ENTITY_TYPE: Final = "parent_student_link"

STATUS_PENDING: Final = "pending"
STATUS_ACTIVE: Final = "active"
STATUS_REJECTED: Final = "rejected"
KNOWN_STATUSES: Final = frozenset({STATUS_PENDING, STATUS_ACTIVE, STATUS_REJECTED})

INITIATOR_ADMIN: Final = "admin"
INITIATOR_PARENT: Final = "parent"
INITIATOR_STUDENT: Final = "student"
KNOWN_INITIATORS: Final = frozenset({INITIATOR_ADMIN, INITIATOR_PARENT, INITIATOR_STUDENT})

# The link rows deliberately avoid `created_at`: GSI-StudentId is keyed on
# (student_id, created_at), so a row carrying both would be projected into the
# index that lists a student's questions, and the consumers that read it without
# filtering would hand out the other party's user id.
_LINK_FIELDS: Final = (
    "entity_type",
    "parent_id",
    "student_id",
    "relationship",
    "status",
    "initiator_role",
    "created_by",
    "linked_at",
    "updated_by",
    "link_updated_at",
)


class ParentLinkConflict(RuntimeError):
    """A link write lost to a concurrent or contradicting stored state."""


type LinkItem = dict[str, Any]


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _checked_status(value: object) -> str:
    status = _required(value, "status")
    if status not in KNOWN_STATUSES:
        raise ValueError("unknown link status")
    return status


def parent_side_key(parent_id: str, student_id: str) -> dict[str, str]:
    return {"PK": f"PARENT#{parent_id}", "SK": f"CHILD#{student_id}"}


def student_side_key(student_id: str, parent_id: str) -> dict[str, str]:
    return {"PK": f"STUDENT#{student_id}", "SK": f"PARENT#{parent_id}"}


def _link_body(
    *,
    parent_id: str,
    student_id: str,
    relationship: str,
    status: str,
    initiator_role: str,
    created_by: str,
    linked_at: str,
    updated_by: str,
    link_updated_at: str,
) -> dict[str, Any]:
    if initiator_role not in KNOWN_INITIATORS:
        raise ValueError("unknown link initiator")
    return {
        "entity_type": ENTITY_TYPE,
        "parent_id": parent_id,
        "student_id": student_id,
        "relationship": relationship,
        "status": status,
        "initiator_role": initiator_role,
        "created_by": created_by,
        "linked_at": linked_at,
        "updated_by": updated_by,
        "link_updated_at": link_updated_at,
    }


def _optional_item(value: object) -> LinkItem | None:
    return dict(value) if isinstance(value, Mapping) else None


def _items(values: object) -> list[LinkItem]:
    if not isinstance(values, list):
        return []
    return [dict(value) for value in values if isinstance(value, Mapping)]


def get_parent_side_link(
    parent_id: str, student_id: str, *, table: Any | None = None
) -> LinkItem | None:
    target = table or get_table()
    response = target.get_item(
        Key=parent_side_key(_required(parent_id, "parent_id"), _required(student_id, "student_id")),
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def get_student_side_link(
    student_id: str, parent_id: str, *, table: Any | None = None
) -> LinkItem | None:
    target = table or get_table()
    response = target.get_item(
        Key=student_side_key(_required(student_id, "student_id"), _required(parent_id, "parent_id")),
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def list_links_for_parent(parent_id: str, *, table: Any | None = None) -> list[LinkItem]:
    target = table or get_table()
    response = target.query(
        KeyConditionExpression=Key("PK").eq(f"PARENT#{_required(parent_id, 'parent_id')}")
        & Key("SK").begins_with("CHILD#"),
        ConsistentRead=True,
    )
    return _items(response.get("Items", []))


def list_links_for_student(student_id: str, *, table: Any | None = None) -> list[LinkItem]:
    target = table or get_table()
    response = target.query(
        KeyConditionExpression=Key("PK").eq(f"STUDENT#{_required(student_id, 'student_id')}")
        & Key("SK").begins_with("PARENT#"),
        ConsistentRead=True,
    )
    return _items(response.get("Items", []))


def _participant_fence_conditions(
    parent_id: str, student_id: str, *, target: Any
) -> list[dict[str, Any]]:
    """Both accounts must still be writable, judged inside the write itself.

    A profile stays active and readable after a deletion is accepted; the fence
    is what closes at acceptance. Checking the profile therefore admitted a new
    private relationship into an account already being deleted, and the two
    relationship rows were the only things the transaction conditioned on.
    """
    conditions: list[dict[str, Any]] = []
    for user_id in (parent_id, student_id):
        try:
            fence = account_deletion_repo.require_active_account_fence(
                user_id, table=target
            )
        except account_deletion_repo.AccountDeletionConflict as exc:
            raise ParentLinkConflict("parent link participant is not writable") from exc
        conditions.append(
            account_deletion_repo.active_fence_condition(
                user_id, int(fence["generation"])
            )
        )
    return conditions


def _both_sides(body: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    parent_id = str(body["parent_id"])
    student_id = str(body["student_id"])
    forward = {**parent_side_key(parent_id, student_id), **body}
    reverse = {**student_side_key(student_id, parent_id), **body}
    return forward, reverse


def create_link(
    *,
    parent_id: str,
    student_id: str,
    status: str,
    initiator_role: str,
    created_by: str,
    linked_at: str,
    relationship: str = "child",
    table: Any | None = None,
) -> LinkItem:
    """Write both directions or neither; a partial link would be an invisible half-grant."""
    body = _link_body(
        parent_id=_required(parent_id, "parent_id"),
        student_id=_required(student_id, "student_id"),
        relationship=_required(relationship, "relationship"),
        status=_checked_status(status),
        initiator_role=_required(initiator_role, "initiator_role"),
        created_by=_required(created_by, "created_by"),
        linked_at=_required(linked_at, "linked_at"),
        updated_by=_required(created_by, "created_by"),
        link_updated_at=_required(linked_at, "linked_at"),
    )
    target = table or get_table()
    forward, reverse = _both_sides(body)
    operations = _participant_fence_conditions(
        str(body["parent_id"]), str(body["student_id"]), target=target
    )
    operations.extend(
        {
            "Put": {
                "Item": item,
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }
        for item in (forward, reverse)
    )
    try:
        account_deletion_repo.transact(operations, table=target)
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise ParentLinkConflict("parent link already exists") from exc
    return dict(body)


def _both_sides_stored(
    parent_id: str, student_id: str, target: Any
) -> tuple[LinkItem, LinkItem]:
    current = get_parent_side_link(parent_id, student_id, table=target)
    mirror = get_student_side_link(student_id, parent_id, table=target)
    if current is None or mirror is None:
        raise ParentLinkConflict("parent link is not fully stored")
    return current, mirror


def _conditional_rewrite(
    *,
    body: Mapping[str, Any],
    condition: str,
    values: Mapping[str, Any],
    target: Any,
    refusal: str,
) -> LinkItem:
    forward, reverse = _both_sides(body)
    operations = _participant_fence_conditions(
        str(body["parent_id"]), str(body["student_id"]), target=target
    )
    operations.extend(
        {
            "Put": {
                "Item": item,
                "ConditionExpression": condition,
                "ExpressionAttributeNames": {"#status": "status"},
                "ExpressionAttributeValues": dict(values),
            }
        }
        for item in (forward, reverse)
    )
    try:
        account_deletion_repo.transact(operations, table=target)
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise ParentLinkConflict(refusal) from exc
    return dict(body)


def transition_link(
    *,
    parent_id: str,
    student_id: str,
    expected_status: str,
    next_status: str,
    updated_by: str,
    link_updated_at: str,
    table: Any | None = None,
) -> LinkItem:
    """Move both rows out of `expected_status` together, or leave both untouched."""
    parent_id = _required(parent_id, "parent_id")
    student_id = _required(student_id, "student_id")
    expected_status = _checked_status(expected_status)
    next_status = _checked_status(next_status)
    if expected_status == next_status:
        raise ValueError("link transition must change the status")

    target = table or get_table()
    current, mirror = _both_sides_stored(parent_id, student_id, target)
    if current.get("status") != expected_status or mirror.get("status") != expected_status:
        raise ParentLinkConflict("parent link is no longer in the expected status")

    body = _link_body(
        parent_id=parent_id,
        student_id=student_id,
        relationship=str(current.get("relationship") or "child"),
        status=next_status,
        initiator_role=str(current.get("initiator_role") or INITIATOR_ADMIN),
        created_by=str(current.get("created_by") or updated_by),
        linked_at=str(current.get("linked_at") or link_updated_at),
        updated_by=_required(updated_by, "updated_by"),
        link_updated_at=_required(link_updated_at, "link_updated_at"),
    )
    return _conditional_rewrite(
        body=body,
        condition="attribute_exists(PK) AND #status = :expected_status",
        values={":expected_status": expected_status},
        target=target,
        refusal="parent link transition refused",
    )


def reclaim_link(
    *,
    parent_id: str,
    student_id: str,
    expected_status: str,
    expected_link_updated_at: str,
    status: str,
    initiator_role: str,
    created_by: str,
    linked_at: str,
    relationship: str = "child",
    table: Any | None = None,
) -> LinkItem:
    """Put a settled pair back into use by rewriting both rows, keys and all.

    The key is never released. Releasing it would mean letting a create
    overwrite what is stored, and `create_link`'s `attribute_not_exists` is the
    only arbiter two concurrent first writes have. Reuse is therefore an
    explicit rewrite fenced on the status *and* the `link_updated_at` that was
    read, so two racers reclaiming the same settled pair cannot both win.
    """
    parent_id = _required(parent_id, "parent_id")
    student_id = _required(student_id, "student_id")
    expected_status = _checked_status(expected_status)
    expected_link_updated_at = _required(expected_link_updated_at, "expected_link_updated_at")
    if _required(linked_at, "linked_at") == expected_link_updated_at:
        # The fence is the stamp changing; a reclaim that reuses it lets both racers win.
        raise ValueError("reclaim must advance link_updated_at")

    target = table or get_table()
    current, mirror = _both_sides_stored(parent_id, student_id, target)
    for side in (current, mirror):
        if side.get("status") != expected_status:
            raise ParentLinkConflict("parent link is no longer in the expected status")
        if side.get("link_updated_at") != expected_link_updated_at:
            raise ParentLinkConflict("parent link changed since it was read")

    body = _link_body(
        parent_id=parent_id,
        student_id=student_id,
        relationship=_required(relationship, "relationship"),
        status=_checked_status(status),
        initiator_role=_required(initiator_role, "initiator_role"),
        created_by=_required(created_by, "created_by"),
        linked_at=_required(linked_at, "linked_at"),
        updated_by=_required(created_by, "created_by"),
        link_updated_at=_required(linked_at, "linked_at"),
    )
    return _conditional_rewrite(
        body=body,
        condition=(
            "attribute_exists(PK) AND #status = :expected_status"
            " AND link_updated_at = :expected_link_updated_at"
        ),
        values={
            ":expected_status": expected_status,
            ":expected_link_updated_at": expected_link_updated_at,
        },
        target=target,
        refusal="parent link reclaim refused",
    )


def link_fields(item: Mapping[str, Any]) -> dict[str, Any]:
    """Project a stored row down to the link contract, dropping table keys."""
    return {field: item.get(field) for field in _LINK_FIELDS}
