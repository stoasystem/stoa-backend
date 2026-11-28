"""DynamoDB access patterns for adaptive learning memory and assignments."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import account_deletion_repo


# Nothing writes or reads these any more (#675); the account deletion still
# reaches rows stored before.
MEMORY_ENTITY = "learning_memory_snapshot"
ASSIGNMENT_ENTITY = "learning_assignment"
ADAPTIVE_WRITER_REGISTRY = frozenset(
    {
        "put_assignment",
        "put_assignment_if_absent",
        "update_assignment",
    }
)
ADAPTIVE_PRIVATE_FIELDS = frozenset(
    {
        "student_id",
        "subject",
        "topic_id",
        "topic_ids",
        "items",
        "answer_key",
        "rationale",
        "note",
        "student_answer",
        "completion_result",
        "sequencing_feedback",
        "skip_note",
        "archive_note",
        "source_context",
        "strengths",
        "weak_topics",
        "mastered_concepts",
        "struggling_concepts",
        "recent_questions",
        "recent_attempts",
        "notes",
        "recommendations",
        "metadata",
    }
)


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def _response(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed adaptive learning dependency response"
        )
    return dict(value)


def _get_item(table: object, **kwargs: object) -> dict[str, Any]:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning dependency unavailable"
        )
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning dependency unavailable"
        )
    return db_table.put(table=table, **kwargs)


def _query(table: object, **kwargs: object) -> dict[str, Any]:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning dependency unavailable"
        )
    return _response(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> dict[str, Any]:
    """The attributes the update hands back; a condition that fails is `WriteRefused`."""
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning dependency unavailable"
        )
    return db_table.update(table=table, **kwargs)


def _atomic_table(table: Any) -> bool:
    return db_table.transactional(table)


def _generation(item: Mapping[str, Any], table: Any) -> tuple[str, int]:
    owner = str(item.get("student_id") or item.get("owner_id") or "").strip()
    if not owner:
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning owner is required"
        )
    supplied = stored_int(item.get("account_fence_generation"))
    if supplied is not None and supplied > 0:
        return owner, supplied
    if _atomic_table(table):
        fence = account_deletion_repo.require_active_account_fence(owner, table=table)
        return owner, int(fence["generation"])
    return owner, 1


def build_adaptive_write_transaction(
    *,
    item: Mapping[str, Any],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stored = {
        **dict(item),
        "owner_id": owner_id,
        "account_fence_generation": generation,
    }
    operations: list[dict[str, Any]] = []
    if mode == "put":
        if stored.get("source_type") == "ai_draft" and stored.get("source_id"):
            operations.append(
                {
                    "ConditionCheck": {
                        "Key": {
                            "PK": f"AI_TEACHER_DRAFT#{stored['source_id']}",
                            "SK": "META",
                        },
                        "ConditionExpression": (
                            "attribute_exists(PK) AND student_id=:owner AND "
                            "owner_id=:owner AND account_fence_generation=:generation "
                            "AND #status=:accepted"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":owner": owner_id,
                            ":generation": generation,
                            ":accepted": "accepted",
                        },
                    }
                }
            )
        operations.append(
            {
                "Put": {
                    "Item": stored,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
        )
        return operations
    if mode != "update" or not updates:
        raise ValueError("adaptive write mode is invalid")
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    values[":owner"] = owner_id
    values[":generation"] = generation
    operations.append(
        {
            "Update": {
                "Key": {"PK": stored["PK"], "SK": stored["SK"]},
                "UpdateExpression": "SET "
                + ", ".join(f"#{key}=:{key}" for key in updates),
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND "
                    "owner_id=:owner AND account_fence_generation=:generation"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }
    )
    return operations


def put_assignment(item: dict[str, Any]) -> None:
    table = db_table.table()
    stored = {
            "PK": f"ASSIGNMENT#{item['assignment_id']}",
            "SK": "META",
            "entity_type": ASSIGNMENT_ENTITY,
            **item,
        }
    owner, generation = _generation(stored, table)
    operations = build_adaptive_write_transaction(
        item=stored, owner_id=owner, generation=generation
    )
    if _atomic_table(table):
        db_table.fenced(owner, operations, generation=generation, table=table)
    else:
        _put_item(table, Item=operations[-1]["Put"]["Item"])
    item.update(owner_id=owner, account_fence_generation=generation)


def put_assignment_if_absent(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    table = db_table.table()
    stored = {
        "PK": f"ASSIGNMENT#{item['assignment_id']}",
        "SK": "META",
        "entity_type": ASSIGNMENT_ENTITY,
        **item,
    }
    owner, generation = _generation(stored, table)
    operations = build_adaptive_write_transaction(
        item=stored, owner_id=owner, generation=generation
    )
    atomic = _atomic_table(table)
    try:
        if atomic:
            db_table.fenced(owner, operations, generation=generation, table=table)
        else:
            _put_item(
                table,
                Item=operations[-1]["Put"]["Item"],
                ConditionExpression=Attr("PK").not_exists(),
            )
    except (
        account_deletion_repo.AccountDeletionConflict,
        db_table.WriteRefused,
        db_table.TableUnavailable,
    ) as exc:
        # A plain write that the table did not refuse could not be made at all.
        if isinstance(exc, db_table.TableUnavailable) and not atomic:
            raise
        existing = get_assignment(str(item["assignment_id"]))
        return existing or item, False
    item.update(owner_id=owner, account_fence_generation=generation)
    return operations[-1]["Put"]["Item"], True


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    table = db_table.table()
    resp = _get_item(
        table, Key={"PK": f"ASSIGNMENT#{assignment_id}", "SK": "META"}
    )
    return resp.get("Item")


def update_assignment(
    assignment_id: str,
    updates: dict[str, Any],
    *,
    expected_status: str | None = None,
    expected_pending_token: str | None = None,
    expected_pending_state: str | None = None,
) -> dict[str, Any] | None:
    table = db_table.table()
    existing = get_assignment(assignment_id)
    if not existing:
        return None
    owner, generation = _generation(existing, table)
    update_expr = "SET " + ", ".join(f"#{key} = :{key}" for key in updates)
    kwargs: dict[str, Any] = {
        "Key": {"PK": f"ASSIGNMENT#{assignment_id}", "SK": "META"},
        "UpdateExpression": update_expr,
        "ExpressionAttributeNames": {f"#{key}": key for key in updates},
        "ExpressionAttributeValues": {f":{key}": value for key, value in updates.items()},
        "ReturnValues": "ALL_NEW",
    }
    condition = Attr("PK").exists() & Attr("student_id").eq(owner)
    if expected_status is not None:
        condition = condition & Attr("status").eq(expected_status)
    if expected_pending_token is not None:
        pending_condition = Attr("pending_sequencing_effect.transitionToken").eq(expected_pending_token)
        condition = condition & pending_condition
    if expected_pending_state is not None:
        state_condition = Attr("pending_sequencing_effect.state").eq(expected_pending_state)
        condition = condition & state_condition
    kwargs["ConditionExpression"] = condition
    atomic = _atomic_table(table)
    try:
        if atomic:
            operations = build_adaptive_write_transaction(
                item=existing,
                owner_id=owner,
                generation=generation,
                mode="update",
                updates=updates,
            )
            mutation = operations[-1]["Update"]
            if expected_status is not None:
                mutation["ConditionExpression"] += " AND #expected_status=:expected_status"
                mutation["ExpressionAttributeNames"]["#expected_status"] = "status"
                mutation["ExpressionAttributeValues"][":expected_status"] = expected_status
            db_table.fenced(
                owner,
                operations,
                generation=generation,
                rows=owner_registry.rows_after(existing, operations),
                table=table,
            )
            return get_assignment(assignment_id) or {**existing, **updates}
        attributes = _update_item(table, **kwargs)
    except (
        account_deletion_repo.AccountDeletionConflict,
        db_table.WriteRefused,
        db_table.TableUnavailable,
    ) as exc:
        # A plain write that the table did not refuse could not be made at all.
        if isinstance(exc, db_table.TableUnavailable) and not atomic:
            raise
        return get_assignment(assignment_id)
    return attributes or None


# GSI-StudentId continues from its own key as well as the table's.
_STUDENT_INDEX_KEY = ("PK", "SK", "student_id", "created_at")


def list_assignments(
    *,
    student_id: str,
    status: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    """The student's assignments, newest first, at most `limit` of them.

    Read from `GSI-StudentId`: every assignment row carries the student and
    `created_at`, so the index holds them all. This was a filtered scan of the
    whole table, read twice for every learning memory - the Ask page's among
    them - and it grew with every curriculum row published (#496).
    """
    table = db_table.table()
    filter_expr = Attr("entity_type").eq(ASSIGNMENT_ENTITY)
    if status:
        filter_expr = filter_expr & Attr("status").eq(status)
    if not include_archived:
        filter_expr = filter_expr & Attr("status").ne("archived")
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning dependency unavailable"
        )
    items = db_table.rows(
        "query",
        table=table,
        want=limit or None,
        key=_STUDENT_INDEX_KEY,
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq(student_id),
        FilterExpression=filter_expr,
        ScanIndexForward=False,
    )
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def _owned(item: Mapping[str, Any], owner_id: str) -> bool:
    """One of the student's assignments or learning memories, by the data type catalog."""
    return item.get("entity_type") in {ASSIGNMENT_ENTITY, MEMORY_ENTITY} and data_catalog.owns(
        item, account_deletion_repo.deletion_account(owner_id)
    )
