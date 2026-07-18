"""DynamoDB access patterns for adaptive learning memory and assignments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


MEMORY_ENTITY = "learning_memory_snapshot"
ASSIGNMENT_ENTITY = "learning_assignment"
ADAPTIVE_PRIVATE_ROW_REGISTRY = frozenset({"assignment", "learning_memory"})
ADAPTIVE_WRITER_REGISTRY = frozenset(
    {
        "put_assignment",
        "put_assignment_if_absent",
        "update_assignment",
        "put_memory_snapshot",
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
ADAPTIVE_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "assignment_id",
        "status",
        "owner_deletion_generation",
        "created_at",
        "deleted_at",
    }
)


@dataclass(frozen=True, slots=True)
class AdaptivePrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None


def _atomic_table(table: Any) -> bool:
    return callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )


def _generation(item: Mapping[str, Any], table: Any) -> tuple[str, int]:
    owner = str(item.get("student_id") or item.get("owner_id") or "").strip()
    if not owner:
        raise account_deletion_repo.AccountDeletionConflict(
            "adaptive learning owner is required"
        )
    supplied = item.get("account_fence_generation")
    if type(supplied) is int and supplied > 0:
        return owner, int(supplied)
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
    operations = [account_deletion_repo.active_fence_condition(owner_id, generation)]
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


def put_memory_snapshot(item: dict[str, Any]) -> None:
    table = get_table()
    stored = {
            "PK": f"LEARNING_MEMORY#{item['student_id']}",
            "SK": f"SUBJECT#{item['subject']}#TOPIC#{item['topic_id']}",
            "entity_type": MEMORY_ENTITY,
            **item,
        }
    owner, generation = _generation(stored, table)
    existing = None
    if _atomic_table(table):
        existing = table.get_item(
            Key={"PK": stored["PK"], "SK": stored["SK"]}, ConsistentRead=True
        ).get("Item")
    operations = build_adaptive_write_transaction(
        item=stored,
        owner_id=owner,
        generation=generation,
        mode="update" if existing else "put",
        updates={key: value for key, value in stored.items() if key not in {"PK", "SK"}}
        if existing
        else None,
    )
    if _atomic_table(table):
        account_deletion_repo.transact(operations, table=table)
    else:
        table.put_item(Item=operations[-1]["Put"]["Item"])
    item.update(owner_id=owner, account_fence_generation=generation)


def list_memory_snapshots(student_id: str, subject: str | None = None) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"LEARNING_MEMORY#{student_id}") & Key("SK").begins_with("SUBJECT#")
        )
    )
    items = resp.get("Items", [])
    if subject:
        items = [item for item in items if item.get("subject") == subject]
    return items


def put_assignment(item: dict[str, Any]) -> None:
    table = get_table()
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
        account_deletion_repo.transact(operations, table=table)
    else:
        table.put_item(Item=operations[-1]["Put"]["Item"])
    item.update(owner_id=owner, account_fence_generation=generation)


def put_assignment_if_absent(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    table = get_table()
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
    try:
        if _atomic_table(table):
            account_deletion_repo.transact(operations, table=table)
        else:
            table.put_item(
                Item=operations[-1]["Put"]["Item"],
                ConditionExpression=Attr("PK").not_exists(),
            )
    except (ClientError, account_deletion_repo.AccountDeletionConflict) as exc:
        if isinstance(exc, account_deletion_repo.AccountDeletionConflict) or exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            existing = get_assignment(str(item["assignment_id"]))
            return existing or item, False
        raise
    item.update(owner_id=owner, account_fence_generation=generation)
    return operations[-1]["Put"]["Item"], True


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    table = get_table()
    resp = table.get_item(Key={"PK": f"ASSIGNMENT#{assignment_id}", "SK": "META"})
    return resp.get("Item")


def update_assignment(
    assignment_id: str,
    updates: dict[str, Any],
    *,
    expected_status: str | None = None,
    expected_pending_token: str | None = None,
    expected_pending_state: str | None = None,
) -> dict[str, Any] | None:
    table = get_table()
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
    try:
        if _atomic_table(table):
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
            account_deletion_repo.transact(operations, table=table)
            return get_assignment(assignment_id) or {**existing, **updates}
        resp = table.update_item(**kwargs)
    except (ClientError, account_deletion_repo.AccountDeletionConflict) as exc:
        if isinstance(exc, account_deletion_repo.AccountDeletionConflict) or exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return get_assignment(assignment_id)
        raise
    return resp.get("Attributes")


def list_assignments(
    *,
    student_id: str,
    status: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    table = get_table()
    filter_expr = Attr("entity_type").eq(ASSIGNMENT_ENTITY) & Attr("student_id").eq(student_id)
    if status:
        filter_expr = filter_expr & Attr("status").eq(status)
    if not include_archived:
        filter_expr = filter_expr & Attr("status").ne("archived")
    scan_kwargs: dict[str, Any] = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[dict[str, Any]] = []
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def scan_adaptive_private_rows(
    owner_id: str,
    *,
    family: str | None = None,
    cursor: Mapping[str, Any] | None = None,
    maximum_pages: int = 1,
    table: Any | None = None,
) -> AdaptivePrivatePage:
    target = table or get_table()
    marker = _cursor(cursor) if cursor is not None else None
    found: list[dict[str, Any]] = []
    for _ in range(maximum_pages):
        kwargs: dict[str, Any] = {"ConsistentRead": True}
        if marker:
            kwargs["ExclusiveStartKey"] = marker
        response = target.scan(**kwargs)
        items = response.get("Items", [])
        if not isinstance(items, list):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed adaptive deletion page"
            )
        for item in items:
            if not isinstance(item, Mapping) or not _owned(item, owner_id):
                continue
            entity = str(item.get("entity_type") or "")
            if family == "assignment" and entity != ASSIGNMENT_ENTITY:
                continue
            if family == "learning_memory" and entity != MEMORY_ENTITY:
                continue
            found.append(dict(item))
        raw_next = response.get("LastEvaluatedKey")
        if raw_next is None:
            return AdaptivePrivatePage(tuple(found))
        next_marker = _cursor(raw_next)
        if next_marker == marker:
            raise account_deletion_repo.AccountDeletionConflict(
                "adaptive deletion cursor did not advance"
            )
        marker = next_marker
    return AdaptivePrivatePage(tuple(found), marker)


def scrub_adaptive_private_row(
    item: Mapping[str, Any],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    if not _owned(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict("adaptive row owner changed")
    candidate = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": f"{item.get('entity_type') or 'adaptive'}_deletion_tombstone",
        "schema_version": "adaptive-deletion-tombstone.v1",
        "assignment_id": item.get("assignment_id"),
        "status": "deleted",
        "owner_deletion_generation": generation,
        "created_at": item.get("created_at"),
        "deleted_at": now_iso,
    }
    tombstone = {
        key: value
        for key, value in candidate.items()
        if key in ADAPTIVE_TOMBSTONE_ALLOWLIST and value is not None
    }
    target = table or get_table()
    hook = getattr(target, "replace_learning_tombstone", None)
    if callable(hook):
        hook(dict(item), tombstone, owner_id, generation)
    else:
        account_deletion_repo.transact(
            [
                account_deletion_repo.deletion_fence_condition(owner_id, generation),
                {
                    "Put": {
                        "Item": tombstone,
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK)"
                        ),
                    }
                },
            ],
            table=target,
        )
    return tombstone


def _owned(item: Mapping[str, Any], owner_id: str) -> bool:
    return owner_id in {
        item.get("student_id"),
        item.get("owner_id"),
    } or str(item.get("PK") or "").startswith(f"LEARNING_MEMORY#{owner_id}")


def _cursor(value: Mapping[str, Any] | None) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"PK", "SK"}
        or any(not isinstance(value.get(key), str) or not value.get(key) for key in ("PK", "SK"))
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid adaptive deletion cursor"
        )
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
