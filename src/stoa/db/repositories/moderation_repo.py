"""DynamoDB access patterns for moderation cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


MODERATION_ROW_REGISTRY = {
    "summary": ("MODERATION#", "SUMMARY"),
    "event": ("MODERATION#", "EVENT#"),
}
MODERATION_WRITER_REGISTRY = {"put_case", "update_case", "put_event"}
MODERATION_PRIVATE_FIELDS = frozenset(
    {
        "question_context",
        "report_note",
        "resolution_note",
        "history",
        "note",
        "changes",
        "reason",
        "surface",
        "severity",
        "actor_id",
        "actor_role",
        "reporter_id",
        "reporter_role",
        "assigned_admin_id",
        "student_id",
    }
)
MODERATION_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "case_id",
        "event_id",
        "question_id",
        "event_type",
        "status",
        "privacy_deleted",
        "privacy_generation",
        "created_at",
        "updated_at",
        "deleted_at",
    }
)


@dataclass(frozen=True, slots=True)
class ModerationPrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None
    unresolved: int = 0


def _required_owner(item: Mapping[str, Any]) -> tuple[str, int]:
    student_id = item.get("student_id")
    generation = item.get("privacy_generation")
    if (
        not isinstance(student_id, str)
        or not student_id.strip()
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation row has no authoritative owner"
        )
    return student_id.strip(), generation


def _summary_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "PK": f"MODERATION#{item['case_id']}",
        "SK": "SUMMARY",
        **dict(item),
    }


def _event_item(
    case_id: str,
    event: Mapping[str, Any],
    *,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    student_id, generation = _required_owner(summary)
    return {
        "PK": f"MODERATION#{case_id}",
        "SK": f"EVENT#{event['event_id']}",
        "entity_type": "moderation_event",
        **dict(event),
        "case_id": case_id,
        "question_id": summary.get("question_id"),
        "student_id": student_id,
        "privacy_generation": generation,
    }


def _validated_cursor(value: Any) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"PK", "SK"}
        or any(
            not isinstance(value.get(field), str) or not value[field]
            for field in ("PK", "SK")
        )
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid moderation continuation cursor"
        )
    return {"PK": value["PK"], "SK": value["SK"]}


def _strong_item(
    target: Any, *, pk: str, sk: str
) -> dict[str, Any] | None:
    response = target.get_item(
        Key={"PK": pk, "SK": sk}, ConsistentRead=True
    )
    item = response.get("Item") if isinstance(response, Mapping) else None
    return dict(item) if isinstance(item, Mapping) else None


def _resolve_private_owner(
    target: Any, row: Mapping[str, Any]
) -> tuple[str, int] | None:
    case_id = str(row.get("case_id") or "")
    if not case_id and str(row.get("PK") or "").startswith("MODERATION#"):
        case_id = str(row["PK"])[len("MODERATION#") :]
    summary = (
        dict(row)
        if row.get("SK") == "SUMMARY"
        else _strong_item(target, pk=f"MODERATION#{case_id}", sk="SUMMARY")
    )
    if not summary:
        return None
    question_id = str(summary.get("question_id") or "")
    question = (
        _strong_item(target, pk=f"QUESTION#{question_id}", sk="META")
        if question_id
        else None
    )
    if not question:
        return None
    owner = question.get("student_id")
    generation = question.get("account_fence_generation")
    if (
        not isinstance(owner, str)
        or not owner
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation <= 0
    ):
        return None
    for candidate in (summary, row):
        declared_owner = candidate.get("student_id")
        declared_generation = candidate.get("privacy_generation")
        if declared_owner not in {None, "", owner}:
            return None
        if declared_generation not in {None, generation}:
            return None
    return owner, generation


def scan_moderation_private_rows(
    user_id: str,
    *,
    table: Any | None = None,
    cursor: dict[str, str] | None = None,
    maximum_pages: int = 1,
    page_limit: int = 100,
) -> ModerationPrivatePage:
    """Strongly discover owner-bound summaries and legacy events from base pages."""
    if maximum_pages <= 0 or page_limit <= 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid moderation scan bound"
        )
    target = table or get_table()
    current = _validated_cursor(cursor) if cursor is not None else None
    seen_cursors = (
        {(current["PK"], current["SK"])} if current is not None else set()
    )
    items: list[dict[str, Any]] = []
    unresolved = 0
    for _ in range(maximum_pages):
        request: dict[str, Any] = {
            "ConsistentRead": True,
            "Limit": page_limit,
        }
        if current is not None:
            request["ExclusiveStartKey"] = current
        response = target.scan(**request)
        raw_items = response.get("Items", []) if isinstance(response, Mapping) else None
        if not isinstance(raw_items, list):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed moderation row page"
            )
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                raise account_deletion_repo.AccountDeletionConflict(
                    "malformed moderation row"
                )
            pk = str(raw.get("PK") or "")
            sk = str(raw.get("SK") or "")
            if not pk.startswith("MODERATION#") or not (
                sk == "SUMMARY" or sk.startswith("EVENT#")
            ):
                continue
            if raw.get("privacy_deleted") is True:
                continue
            owner = _resolve_private_owner(target, raw)
            if owner is None:
                claimed_owner = raw.get("student_id")
                if sk.startswith("EVENT#"):
                    case_id = str(raw.get("case_id") or pk[len("MODERATION#") :])
                    summary = _strong_item(
                        target, pk=f"MODERATION#{case_id}", sk="SUMMARY"
                    )
                    if summary:
                        claimed_owner = summary.get("student_id")
                if claimed_owner == user_id:
                    unresolved += 1
                continue
            student_id, generation = owner
            if student_id != user_id:
                continue
            normalized = dict(raw)
            normalized["student_id"] = student_id
            normalized["privacy_generation"] = generation
            items.append(normalized)
        raw_cursor = response.get("LastEvaluatedKey")
        if raw_cursor is None:
            return ModerationPrivatePage(tuple(items), None, unresolved)
        next_cursor = _validated_cursor(raw_cursor)
        cursor_identity = (next_cursor["PK"], next_cursor["SK"])
        if cursor_identity in seen_cursors:
            raise account_deletion_repo.AccountDeletionConflict(
                "repeating moderation continuation cursor"
            )
        seen_cursors.add(cursor_identity)
        current = next_cursor
    return ModerationPrivatePage(tuple(items), current, unresolved)


def scrub_moderation_row(
    item: Mapping[str, Any],
    *,
    user_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    """Replace one resolved moderation row with a strict noncontent tombstone."""
    target = table or get_table()
    key = _validated_cursor({"PK": item.get("PK"), "SK": item.get("SK")})
    if not key["PK"].startswith("MODERATION#") or not (
        key["SK"] == "SUMMARY" or key["SK"].startswith("EVENT#")
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "row is not registered moderation content"
        )
    tombstone = {
        key_name: value
        for key_name, value in dict(item).items()
        if key_name in MODERATION_TOMBSTONE_ALLOWLIST and value is not None
    }
    tombstone.update(
        {
            "PK": key["PK"],
            "SK": key["SK"],
            "entity_type": (
                "moderation_case"
                if key["SK"] == "SUMMARY"
                else "moderation_event"
            ),
            "privacy_deleted": True,
            "privacy_generation": generation,
            "updated_at": now_iso,
            "deleted_at": now_iso,
        }
    )
    hook = getattr(target, "scrub_moderation_row", None)
    if callable(hook):
        hook(dict(item), tombstone, user_id, generation)
        return tombstone
    account_deletion_repo.require_deletion_account_fence(
        user_id, generation, table=target
    )
    account_deletion_repo.transact(
        [
            account_deletion_repo.deletion_fence_condition(user_id, generation),
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) "
                        "AND (attribute_not_exists(student_id) OR student_id=:owner) "
                        "AND (attribute_not_exists(privacy_generation) OR "
                        "privacy_generation=:generation)"
                    ),
                    "ExpressionAttributeValues": {
                        ":owner": user_id,
                        ":generation": generation,
                    },
                }
            },
        ],
        table=target,
    )
    return tombstone


def put_case(
    item: dict[str, Any],
    event: dict[str, Any] | None = None,
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    target = table or get_table()
    student_id, generation = _required_owner(item)
    account_deletion_repo.require_active_account_fence(
        student_id, generation, table=target
    )
    summary = _summary_item(item)
    operations: list[dict[str, Any]] = [
        account_deletion_repo.active_fence_condition(student_id, generation),
        {
            "Put": {
                "Item": summary,
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        },
    ]
    if event is not None:
        operations.append(
            {
                "Put": {
                    "Item": _event_item(str(item["case_id"]), event, summary=summary),
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
        )
    account_deletion_repo.transact(operations, table=target)
    return summary


def put_event(
    case_id: str,
    event: dict[str, Any],
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    target = table or get_table()
    summary = get_case(case_id, table=target)
    if not summary:
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation case does not exist"
        )
    student_id, generation = _required_owner(summary)
    account_deletion_repo.require_active_account_fence(
        student_id, generation, table=target
    )
    persisted = _event_item(case_id, event, summary=summary)
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(student_id, generation),
            {
                "Put": {
                    "Item": persisted,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            {
                "ConditionCheck": {
                    "Key": {"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"},
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) "
                        "AND student_id=:owner AND privacy_generation=:generation"
                    ),
                    "ExpressionAttributeValues": {
                        ":owner": student_id,
                        ":generation": generation,
                    },
                }
            },
        ],
        table=target,
    )
    return persisted


def get_case(
    case_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    target = table or get_table()
    resp = target.get_item(
        Key={"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"},
        ConsistentRead=True,
    )
    item = resp.get("Item")
    if not isinstance(item, Mapping) or item.get("privacy_deleted") is True:
        return None
    return dict(item)


def list_case_events(case_id: str, limit: int = 100) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"MODERATION#{case_id}") & Key("SK").begins_with("EVENT#"),
        Limit=limit,
        ScanIndexForward=True,
    )
    return [
        dict(item)
        for item in resp.get("Items", [])
        if isinstance(item, Mapping) and item.get("privacy_deleted") is not True
    ]


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    table = get_table()
    resp = table.scan(
        FilterExpression=Attr("entity_type").eq("moderation_case"),
        Limit=limit,
    )
    return [
        dict(item)
        for item in resp.get("Items", [])
        if isinstance(item, Mapping) and item.get("privacy_deleted") is not True
    ]


def update_case(
    case_id: str,
    attrs: dict[str, Any],
    *,
    table: Any | None = None,
) -> dict[str, Any] | None:
    if not attrs:
        return get_case(case_id, table=table)
    target = table or get_table()
    existing = get_case(case_id, table=target)
    if not existing:
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation case does not exist"
        )
    student_id, generation = _required_owner(existing)
    account_deletion_repo.require_active_account_fence(
        student_id, generation, table=target
    )
    names = {f"#{key}": key for key in attrs}
    values = {f":{key}": value for key, value in attrs.items()}
    values.update({":owner": student_id, ":generation": generation})
    expression = "SET " + ", ".join(f"#{key} = :{key}" for key in attrs)
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(student_id, generation),
            {
                "Update": {
                    "Key": {"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"},
                    "UpdateExpression": expression,
                    "ConditionExpression": (
                        "attribute_exists(PK) AND attribute_exists(SK) "
                        "AND student_id=:owner AND privacy_generation=:generation"
                    ),
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": values,
                }
            },
        ],
        table=target,
    )
    return {**existing, **attrs}
