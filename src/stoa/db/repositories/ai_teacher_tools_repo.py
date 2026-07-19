"""DynamoDB access patterns for reviewed AI teacher tool drafts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, ConditionBase

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


type AIDraftItem = dict[str, object]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _TombstoneTable(Protocol):
    def replace_learning_tombstone(
        self,
        item: AIDraftItem,
        tombstone: AIDraftItem,
        owner_id: str,
        generation: int,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class AIDraftPrivatePage:
    items: tuple[AIDraftItem, ...]
    cursor: dict[str, str] | None = None


def _mapping(value: object) -> AIDraftItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed AI draft dependency response"
        )
    item: AIDraftItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed AI draft dependency response"
            )
        item[key] = member
    return item


def _items(value: object) -> list[AIDraftItem]:
    if not isinstance(value, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed AI draft dependency response"
        )
    return [_mapping(item) for item in value]


def _get_item(table: object, **kwargs: object) -> AIDraftItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict("AI draft dependency unavailable")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict("AI draft dependency unavailable")
    return table.put_item(**kwargs)


def _scan(table: object, **kwargs: object) -> AIDraftItem:
    if not isinstance(table, _ScanTable):
        raise account_deletion_repo.AccountDeletionConflict("AI draft dependency unavailable")
    return _mapping(table.scan(**kwargs))


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict("AI draft dependency unavailable")
    return table.update_item(**kwargs)


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise account_deletion_repo.AccountDeletionConflict(f"invalid AI draft {field}")
    return value


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise account_deletion_repo.AccountDeletionConflict(f"invalid AI draft {field}")
    return value


def _created_at(item: AIDraftItem) -> str:
    value = item.get("created_at", "")
    if not isinstance(value, str):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed AI draft dependency response"
        )
    return value


def _atomic_table(table: object) -> bool:
    return callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None) and getattr(table, "name", None)
    )


def _generation(item: Mapping[str, object], table: object) -> tuple[str, int]:
    owner = str(item.get("student_id") or item.get("owner_id") or "").strip()
    if not owner:
        raise account_deletion_repo.AccountDeletionConflict("AI draft owner is required")
    supplied = item.get("account_fence_generation")
    if type(supplied) is int and supplied > 0:
        return owner, supplied
    if _atomic_table(table):
        fence = account_deletion_repo.require_active_account_fence(owner, table=table)
        return owner, _positive_int(fence.get("generation"), field="fence generation")
    return owner, 1


def build_ai_draft_write_transaction(
    *,
    item: Mapping[str, object],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, object] | None = None,
) -> list[AIDraftItem]:
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
                "UpdateExpression": "SET " + ", ".join(f"#{key}=:{key}" for key in updates),
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


def put_draft(item: AIDraftItem) -> None:
    table = get_table()
    stored = {
        **item,
        "PK": draft_pk(_required_text(item.get("draft_id"), field="identifier")),
        "SK": "META",
    }
    owner, generation = _generation(stored, table)
    operations = build_ai_draft_write_transaction(
        item=stored, owner_id=owner, generation=generation
    )
    if _atomic_table(table):
        account_deletion_repo.transact(operations, table=table)
    else:
        put = _mapping(operations[1].get("Put"))
        _put_item(table, Item=_mapping(put.get("Item")))
    item.update(owner_id=owner, account_fence_generation=generation)


def get_draft(draft_id: str) -> AIDraftItem | None:
    response = _get_item(get_table(), Key={"PK": draft_pk(draft_id), "SK": "META"})
    item = response.get("Item")
    return _mapping(item) if item is not None else None


def update_draft(
    draft_id: str,
    updates: AIDraftItem,
    *,
    existing: AIDraftItem | None = None,
) -> AIDraftItem | None:
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
        _update_item(
            table,
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
) -> list[AIDraftItem]:
    filter_expr: ConditionBase = Attr("entity_type").eq(DRAFT_ENTITY)
    if student_id is not None:
        filter_expr = filter_expr & Attr("student_id").eq(student_id)
    if status is not None:
        filter_expr = filter_expr & Attr("status").eq(status)
    if draft_type is not None:
        filter_expr = filter_expr & Attr("draft_type").eq(draft_type)
    scan_kwargs: AIDraftItem = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[AIDraftItem] = []
    while True:
        response = _scan(get_table(), **scan_kwargs)
        items.extend(_items(response.get("Items", [])))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return sorted(items, key=_created_at, reverse=True)


def scan_ai_draft_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, object] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> AIDraftPrivatePage:
    target = table or get_table()
    marker = _cursor(cursor) if cursor is not None else None
    found: list[AIDraftItem] = []
    for _ in range(maximum_pages):
        kwargs: AIDraftItem = {"ConsistentRead": True}
        if marker:
            kwargs["ExclusiveStartKey"] = marker
        response = _scan(target, **kwargs)
        items = response.get("Items", [])
        if not isinstance(items, list):
            raise account_deletion_repo.AccountDeletionConflict("malformed AI draft deletion page")
        for raw in items:
            if not isinstance(raw, Mapping):
                continue
            item = _mapping(raw)
            if item.get("entity_type") == DRAFT_ENTITY and owner_id in {
                item.get("student_id"),
                item.get("owner_id"),
            }:
                found.append(item)
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
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> AIDraftItem:
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
    if isinstance(target, _TombstoneTable):
        target.replace_learning_tombstone(_mapping(item), tombstone, owner_id, generation)
    else:
        account_deletion_repo.transact(
            [
                account_deletion_repo.deletion_fence_condition(owner_id, generation),
                {
                    "Put": {
                        "Item": tombstone,
                        "ConditionExpression": ("attribute_exists(PK) AND attribute_exists(SK)"),
                    }
                },
            ],
            table=target,
        )
    return tombstone


def _cursor(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"PK", "SK"}:
        raise account_deletion_repo.AccountDeletionConflict("invalid AI draft deletion cursor")
    pk = value.get("PK")
    sk = value.get("SK")
    if not isinstance(pk, str) or not pk or not isinstance(sk, str) or not sk:
        raise account_deletion_repo.AccountDeletionConflict("invalid AI draft deletion cursor")
    return {"PK": pk, "SK": sk}
