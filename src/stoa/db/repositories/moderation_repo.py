"""DynamoDB access patterns for moderation cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import data_catalog, listing_index, owner_registry
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
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
        # A refused image's case (#139): its hits, uploader and session, and
        # where the image is kept.
        "image_context",
        "image_object_key",
        "image_version_id",
        "image_sha256",
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


# The admin queue, the image retention and the operator's review count read
# every live case. A case summary carries the keys of GSI-Listing from its
# first write, so those reads query this list instead of scanning the table
# (card 135). An update only SETs its own fields, and a privacy tombstone,
# which keeps neither key, leaves the list.
CASE_LISTING = "moderation_case"


def listing_fields(item: Mapping[str, Any]) -> dict[str, str]:
    """The GSI-Listing keys of a live case summary; none for any other row."""
    if item.get("entity_type") != "moderation_case" or item.get("privacy_deleted") is True:
        return {}
    created_at = item.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        return {}
    return {"listing": CASE_LISTING, "listed_at": created_at}


@dataclass(frozen=True, slots=True)
class ModerationPrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None
    unresolved: int = 0


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


def _response(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed moderation dependency response"
        )
    return dict(value)


def _get_item(table: object, **kwargs: object) -> dict[str, Any]:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation dependency unavailable"
        )
    return _response(table.get_item(**kwargs))


def _query(table: object, **kwargs: object) -> dict[str, Any]:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation dependency unavailable"
        )
    return _response(table.query(**kwargs))


def _required_owner(item: Mapping[str, Any]) -> tuple[str, int]:
    student_id = item.get("student_id")
    generation = stored_int(item.get("privacy_generation"))
    if (
        not isinstance(student_id, str)
        or not student_id.strip()
        or generation is None
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
        **listing_fields(item),
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


def _strong_item(
    target: Any, *, pk: str, sk: str
) -> dict[str, Any] | None:
    response = _get_item(
        target,
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
    if summary.get("surface") == "image_upload":
        # A refused image's case has no question. It was written under its
        # uploader's active fence, so its own owner is the authority (#139).
        owner = summary.get("student_id")
        generation = stored_int(summary.get("privacy_generation"))
    else:
        question_id = str(summary.get("question_id") or "")
        question = (
            _strong_item(target, pk=f"QUESTION#{question_id}", sk="META")
            if question_id
            else None
        )
        if not question:
            return None
        owner = question.get("student_id")
        generation = stored_int(question.get("account_fence_generation"))
    if not isinstance(owner, str) or not owner or generation is None or generation <= 0:
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
    """Strongly discover the account's moderation summaries and events from base pages."""
    if maximum_pages <= 0 or page_limit <= 0:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid moderation scan bound"
        )
    user_id = account_deletion_repo.deletion_account(user_id)
    target: object = table if table is not None else db_table.table()
    current = (
        account_deletion_repo.continuation_key(cursor, "moderation continuation")
        if cursor is not None
        else None
    )
    seen_cursors = (
        {(current["PK"], current["SK"])} if current is not None else set()
    )
    items: list[dict[str, Any]] = []
    unresolved = 0
    for page in account_deletion_repo.sweep_pages(
        "moderation continuation",
        table=target,
        cursor=current,
        page_limit=page_limit,
        maximum_pages=maximum_pages,
    ):
        for raw in page.items:
            pk = str(raw.get("PK") or "")
            sk = str(raw.get("SK") or "")
            if not pk.startswith("MODERATION#") or not (
                sk == "SUMMARY" or sk.startswith("EVENT#")
            ):
                continue
            if raw.get("privacy_deleted") is True:
                continue
            # Whose it is: the row's own `student_id`, read by the data type
            # catalog like every other row (#586 decision 3, #588).
            if not data_catalog.owns(raw, user_id):
                continue
            # Before taking it, confirm that against the question (or the
            # refused image's case) it was written for. A row whose owner the
            # check cannot confirm is left in place and counted as unresolved,
            # which keeps the branch from sealing.
            owner = _resolve_private_owner(target, raw)
            if owner is None or owner[0] != user_id:
                unresolved += 1
                continue
            student_id, generation = owner
            normalized = dict(raw)
            normalized["student_id"] = student_id
            normalized["privacy_generation"] = generation
            items.append(normalized)
        if page.last_key is None:
            return ModerationPrivatePage(tuple(items), None, unresolved)
        next_cursor = page.last_key
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
    target: object = table if table is not None else db_table.table()
    key = account_deletion_repo.continuation_key(
        {"PK": item.get("PK"), "SK": item.get("SK")}, "moderation continuation"
    )
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
    db_table.transact(
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
    target = table or db_table.table()
    student_id, generation = _required_owner(item)
    summary = _summary_item(item)
    operations: list[dict[str, Any]] = [
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
    db_table.fenced(student_id, operations, generation=generation, table=target)
    return summary


def put_event(
    case_id: str,
    event: dict[str, Any],
    *,
    table: Any | None = None,
) -> dict[str, Any]:
    target = table or db_table.table()
    summary = get_case(case_id, table=target)
    if not summary:
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation case does not exist"
        )
    student_id, generation = _required_owner(summary)
    persisted = _event_item(case_id, event, summary=summary)
    db_table.fenced(
        student_id,
        [
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
        generation=generation,
        table=target,
    )
    return persisted


def get_case(
    case_id: str, *, table: Any | None = None
) -> dict[str, Any] | None:
    target: object = table if table is not None else db_table.table()
    resp = _get_item(
        target,
        Key={"PK": f"MODERATION#{case_id}", "SK": "SUMMARY"},
        ConsistentRead=True,
    )
    item = resp.get("Item")
    if not isinstance(item, Mapping) or item.get("privacy_deleted") is True:
        return None
    return dict(item)


def list_case_events(case_id: str, limit: int = 100) -> list[dict[str, Any]]:
    resp = _query(
        db_table.table(),
        KeyConditionExpression=Key("PK").eq(f"MODERATION#{case_id}") & Key("SK").begins_with("EVENT#"),
        Limit=limit,
        ScanIndexForward=True,
    )
    return [
        dict(item)
        for item in resp.get("Items", [])
        if isinstance(item, Mapping) and item.get("privacy_deleted") is not True
    ]


def list_cases(
    limit: int | None = 50, *, table: Any | None = None
) -> list[dict[str, Any]]:
    """Live cases, newest first, at most `limit` of them; every one when it is None.

    Read from GSI-Listing once the backfill has put the cases written before
    card 135 there; until then from the scan this replaced.
    """
    # The cap is applied after the privacy filter, not before it: a page of
    # deleted cases must not be what a reader gets instead of live ones.
    if listing_index.backfilled(CASE_LISTING, table=table):
        rows = db_table.rows(
            "query",
            table=table,
            key=listing_index.INDEX_KEY,
            IndexName=listing_index.INDEX,
            KeyConditionExpression=Key("listing").eq(CASE_LISTING),
            ScanIndexForward=False,
        )
    else:
        rows = db_table.rows(
            "scan",
            table=table,
            FilterExpression=Attr("entity_type").eq("moderation_case"),
        )
    cases = [
        item
        for item in rows
        if item.get("entity_type") == "moderation_case"
        and item.get("privacy_deleted") is not True
    ]
    return cases[:limit]


def update_case(
    case_id: str,
    attrs: dict[str, Any],
    *,
    table: Any | None = None,
) -> dict[str, Any] | None:
    if not attrs:
        return get_case(case_id, table=table)
    target = table or db_table.table()
    existing = get_case(case_id, table=target)
    if not existing:
        raise account_deletion_repo.AccountDeletionConflict(
            "moderation case does not exist"
        )
    student_id, generation = _required_owner(existing)
    names = {f"#{key}": key for key in attrs}
    values = {f":{key}": value for key, value in attrs.items()}
    values.update({":owner": student_id, ":generation": generation})
    expression = "SET " + ", ".join(f"#{key} = :{key}" for key in attrs)
    operations = [
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
    ]
    db_table.fenced(
        student_id,
        operations,
        generation=generation,
        rows=owner_registry.rows_after(existing, operations),
        table=target,
    )
    return {**existing, **attrs}
