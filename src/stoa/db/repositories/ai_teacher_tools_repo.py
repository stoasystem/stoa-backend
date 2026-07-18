"""DynamoDB access patterns for reviewed AI teacher tool drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from boto3.dynamodb.conditions import Attr

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


DRAFT_ENTITY = "ai_teacher_draft"
AI_DRAFT_PRIVATE_ROW_REGISTRY = frozenset({"ai_teacher_draft"})
AI_DRAFT_WRITER_REGISTRY = frozenset({"put_draft", "update_draft"})
AI_DRAFT_PRIVATE_FIELDS = frozenset(
    {
        "student_id",
        "question_id",
        "subject",
        "topic_ids",
        "session_summary",
        "misconception_summary",
        "suggested_teaching_focus",
        "draft_followup_explanation",
        "items",
        "answer_key",
        "explanations",
        "source_context",
        "review_note",
    }
)
AI_DRAFT_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "draft_id",
        "status",
        "owner_deletion_generation",
        "created_at",
        "deleted_at",
    }
)


@dataclass(frozen=True, slots=True)
class AIDraftPrivatePage:
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
        raise account_deletion_repo.AccountDeletionConflict("AI draft owner is required")
    supplied = item.get("account_fence_generation")
    if type(supplied) is int and supplied > 0:
        return owner, int(supplied)
    if _atomic_table(table):
        fence = account_deletion_repo.require_active_account_fence(owner, table=table)
        return owner, int(fence["generation"])
    return owner, 1


def build_ai_draft_write_transaction(
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
        raise ValueError("AI draft write mode is invalid")
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    values.update({":owner": owner_id, ":generation": generation})
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


def draft_pk(draft_id: str) -> str:
    return f"AI_TEACHER_DRAFT#{draft_id}"


def put_draft(item: dict[str, Any]) -> None:
    table = get_table()
    stored = {**item, "PK": draft_pk(item["draft_id"]), "SK": "META"}
    owner, generation = _generation(stored, table)
    operations = build_ai_draft_write_transaction(
        item=stored, owner_id=owner, generation=generation
    )
    if _atomic_table(table):
        account_deletion_repo.transact(operations, table=table)
    else:
        table.put_item(Item=operations[1]["Put"]["Item"])
    item.update(owner_id=owner, account_fence_generation=generation)


def get_draft(draft_id: str) -> dict[str, Any] | None:
    response = get_table().get_item(Key={"PK": draft_pk(draft_id), "SK": "META"})
    return response.get("Item")


def update_draft(
    draft_id: str,
    updates: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    existing = existing or get_draft(draft_id)
    if not existing:
        return None
    if not updates:
        return existing
    table = get_table()
    owner, generation = _generation(existing, table)
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    if _atomic_table(table):
        operations = build_ai_draft_write_transaction(
            item=existing,
            owner_id=owner,
            generation=generation,
            mode="update",
            updates=updates,
        )
        account_deletion_repo.transact(operations, table=table)
    else:
        table.update_item(
            Key={"PK": draft_pk(draft_id), "SK": "META"},
            UpdateExpression="SET " + ", ".join(f"#{key} = :{key}" for key in updates),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=Attr("PK").exists() & Attr("student_id").eq(owner),
        )
    return {
        **existing,
        **updates,
        "owner_id": owner,
        "account_fence_generation": generation,
    }


def list_drafts(
    *,
    student_id: str | None = None,
    status: str | None = None,
    draft_type: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    filter_expr = Attr("entity_type").eq(DRAFT_ENTITY)
    if student_id is not None:
        filter_expr = filter_expr & Attr("student_id").eq(student_id)
    if status is not None:
        filter_expr = filter_expr & Attr("status").eq(status)
    if draft_type is not None:
        filter_expr = filter_expr & Attr("draft_type").eq(draft_type)
    scan_kwargs: dict[str, Any] = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[dict[str, Any]] = []
    while True:
        response = get_table().scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=lambda item: item.get("created_at", ""), reverse=True)


def scan_ai_draft_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, Any] | None = None,
    maximum_pages: int = 1,
    table: Any | None = None,
) -> AIDraftPrivatePage:
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
                "malformed AI draft deletion page"
            )
        found.extend(
            dict(item)
            for item in items
            if isinstance(item, Mapping)
            and item.get("entity_type") == DRAFT_ENTITY
            and owner_id in {item.get("student_id"), item.get("owner_id")}
        )
        raw_next = response.get("LastEvaluatedKey")
        if raw_next is None:
            return AIDraftPrivatePage(tuple(found))
        next_marker = _cursor(raw_next)
        if next_marker == marker:
            raise account_deletion_repo.AccountDeletionConflict(
                "AI draft deletion cursor did not advance"
            )
        marker = next_marker
    return AIDraftPrivatePage(tuple(found), marker)


def scrub_ai_draft_private_row(
    item: Mapping[str, Any],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    if owner_id not in {item.get("student_id"), item.get("owner_id")}:
        raise account_deletion_repo.AccountDeletionConflict("AI draft owner changed")
    candidate = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": "ai_teacher_draft_deletion_tombstone",
        "schema_version": "ai-draft-deletion-tombstone.v1",
        "draft_id": item.get("draft_id"),
        "status": "deleted",
        "owner_deletion_generation": generation,
        "created_at": item.get("created_at"),
        "deleted_at": now_iso,
    }
    tombstone = {
        key: value
        for key, value in candidate.items()
        if key in AI_DRAFT_TOMBSTONE_ALLOWLIST and value is not None
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


def _cursor(value: Mapping[str, Any] | None) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"PK", "SK"}
        or any(not isinstance(value.get(key), str) or not value.get(key) for key in ("PK", "SK"))
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid AI draft deletion cursor"
        )
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}
