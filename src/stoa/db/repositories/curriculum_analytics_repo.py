"""DynamoDB helpers for bounded curriculum quality analytics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, ConditionBase

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


SIGNAL_ENTITY = "curriculum_analytics_signal"
METRIC_ENTITY = "curriculum_analytics_metric"
OWNER_MANIFEST_ENTITY = "curriculum_signal_owner_manifest"
RECONCILIATION_ENTITY = "curriculum_signal_reconciliation"
CURRICULUM_SIGNAL_WRITER_REGISTRY = frozenset(
    {"record_curriculum_signal", "reconcile_curriculum_signal"}
)
CURRICULUM_SIGNAL_PRIVATE_FIELDS = frozenset(
    {"student_id", "studentHash", "correct", "behavior", "metadata"}
)


type CurriculumSignalItem = dict[str, object]


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


@dataclass(frozen=True, slots=True)
class CurriculumSignalPage:
    items: tuple[CurriculumSignalItem, ...]
    cursor: dict[str, str] | None = None


def _mapping(value: object) -> CurriculumSignalItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed curriculum signal dependency response"
        )
    item: CurriculumSignalItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed curriculum signal dependency response"
            )
        item[key] = member
    return item


def _items(value: object) -> list[CurriculumSignalItem]:
    if not isinstance(value, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed curriculum signal dependency response"
        )
    return [_mapping(item) for item in value]


def _get_item(table: object, **kwargs: object) -> CurriculumSignalItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "curriculum signal dependency unavailable"
        )
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "curriculum signal dependency unavailable"
        )
    return table.put_item(**kwargs)


def _scan(table: object, **kwargs: object) -> CurriculumSignalItem:
    if not isinstance(table, _ScanTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "curriculum signal dependency unavailable"
        )
    return _mapping(table.scan(**kwargs))


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "curriculum signal dependency unavailable"
        )
    return table.update_item(**kwargs)


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise account_deletion_repo.AccountDeletionConflict(f"invalid curriculum signal {field}")
    return value


def _atomic_table(table: object) -> bool:
    return callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None) and getattr(table, "name", None)
    )


def _generation(student_id: str, supplied: int | None, table: object) -> int:
    if type(supplied) is int and supplied > 0:
        return supplied
    if _atomic_table(table):
        fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
        return _positive_int(fence.get("generation"), field="fence generation")
    return 1


def build_curriculum_signal_transaction(
    *, student_id: str, generation: int, item: Mapping[str, object]
) -> list[CurriculumSignalItem]:
    """Atomically persist an opaque signal, owner manifest, and contribution."""
    raw_metadata = item.get("metadata")
    metadata = {} if raw_metadata is None else _mapping(raw_metadata)
    clean_metadata = {
        str(key): value
        for key, value in metadata.items()
        if key not in {"studentHash", "student_id", "owner_id"}
    }
    signal = {
        key: value
        for key, value in dict(item).items()
        if key not in {"student_id", "owner_id", "studentHash"}
    }
    signal["metadata"] = clean_metadata
    signal.update(
        PK=f"CURRICULUM_SIGNAL#{signal['public_id']}",
        SK=f"SIGNAL#{signal['created_at']}#{signal['signal_id']}",
        entity_type=SIGNAL_ENTITY,
    )
    metric_pk = f"CURRICULUM_METRIC#{signal['content_type']}#{signal['public_id']}"
    metric_sk = f"VERSION#{signal.get('version_id') or 'unknown'}"
    manifest = {
        "PK": f"CURRICULUM_SIGNAL_OWNER#{student_id}",
        "SK": f"SIGNAL#{signal['signal_id']}",
        "entity_type": OWNER_MANIFEST_ENTITY,
        "signal_id": signal["signal_id"],
        "signal_pk": signal["PK"],
        "signal_sk": signal["SK"],
        "metric_pk": metric_pk,
        "metric_sk": metric_sk,
        "signal_type": signal["signal_type"],
        "source_type": signal["source_type"],
        "account_fence_generation": generation,
        "created_at": signal["created_at"],
    }
    signal_field = f"signal_{signal['signal_type']}_count"
    source_field = f"source_{signal['source_type']}_count"
    return [
        account_deletion_repo.active_fence_condition(student_id, generation),
        {
            "Put": {
                "Item": signal,
                "ConditionExpression": ("attribute_not_exists(PK) AND attribute_not_exists(SK)"),
            }
        },
        {
            "Put": {
                "Item": manifest,
                "ConditionExpression": ("attribute_not_exists(PK) AND attribute_not_exists(SK)"),
            }
        },
        {
            "Update": {
                "Key": {"PK": metric_pk, "SK": metric_sk},
                "UpdateExpression": (
                    "SET #entity_type=:entity_type, #public_id=:public_id, "
                    "#content_type=:content_type, #version_id=:version_id, "
                    "#subject_id=:subject_id, #topic_id=:topic_id, "
                    "#updated_at=:updated_at ADD #total_count :one, "
                    "#signal_count :one, #source_count :one"
                ),
                "ExpressionAttributeNames": {
                    "#entity_type": "entity_type",
                    "#public_id": "public_id",
                    "#content_type": "content_type",
                    "#version_id": "version_id",
                    "#subject_id": "subject_id",
                    "#topic_id": "topic_id",
                    "#updated_at": "updated_at",
                    "#total_count": "total_count",
                    "#signal_count": signal_field,
                    "#source_count": source_field,
                },
                "ExpressionAttributeValues": {
                    ":entity_type": METRIC_ENTITY,
                    ":public_id": signal["public_id"],
                    ":content_type": signal["content_type"],
                    ":version_id": signal.get("version_id") or "unknown",
                    ":subject_id": signal.get("subject_id") or "",
                    ":topic_id": signal.get("topic_id") or "",
                    ":updated_at": signal["created_at"],
                    ":one": 1,
                },
            }
        },
    ]


def record_student_signal(
    item: CurriculumSignalItem,
    *,
    student_id: str,
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> None:
    target = table or get_table()
    generation = _generation(student_id, account_fence_generation, target)
    operations = build_curriculum_signal_transaction(
        student_id=student_id, generation=generation, item=item
    )
    if _atomic_table(target):
        account_deletion_repo.transact(operations, table=target)
    else:
        # Compatibility for focused unit fakes; production always uses one transaction.
        first_put = _mapping(operations[1].get("Put"))
        second_put = _mapping(operations[2].get("Put"))
        update = _mapping(operations[3].get("Update"))
        _put_item(target, Item=_mapping(first_put.get("Item")))
        _put_item(target, Item=_mapping(second_put.get("Item")))
        _update_item(target, **update)


def put_signal(item: CurriculumSignalItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_SIGNAL#{item['public_id']}",
            "SK": f"SIGNAL#{item['created_at']}#{item['signal_id']}",
            "entity_type": SIGNAL_ENTITY,
            **item,
        },
    )


def increment_metric(item: CurriculumSignalItem) -> None:
    table = get_table()
    signal_field = f"signal_{item['signal_type']}_count"
    source_field = f"source_{item['source_type']}_count"
    names = {
        "#entity_type": "entity_type",
        "#public_id": "public_id",
        "#content_type": "content_type",
        "#version_id": "version_id",
        "#subject_id": "subject_id",
        "#topic_id": "topic_id",
        "#updated_at": "updated_at",
        "#total_count": "total_count",
        "#signal_count": signal_field,
        "#source_count": source_field,
    }
    values: CurriculumSignalItem = {
        ":entity_type": METRIC_ENTITY,
        ":public_id": item["public_id"],
        ":content_type": item["content_type"],
        ":version_id": item.get("version_id") or "unknown",
        ":subject_id": item.get("subject_id") or "",
        ":topic_id": item.get("topic_id") or "",
        ":updated_at": item["created_at"],
        ":one": 1,
    }
    _update_item(
        table,
        Key={
            "PK": f"CURRICULUM_METRIC#{item['content_type']}#{item['public_id']}",
            "SK": f"VERSION#{item.get('version_id') or 'unknown'}",
        },
        UpdateExpression=(
            "SET #entity_type = :entity_type, #public_id = :public_id, "
            "#content_type = :content_type, #version_id = :version_id, "
            "#subject_id = :subject_id, #topic_id = :topic_id, #updated_at = :updated_at "
            "ADD #total_count :one, #signal_count :one, #source_count :one"
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def list_metrics(
    *,
    content_type: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
    limit: int | None = 100,
) -> list[CurriculumSignalItem]:
    table = get_table()
    filter_expr: ConditionBase = Attr("entity_type").eq(METRIC_ENTITY)
    if content_type:
        filter_expr = filter_expr & Attr("content_type").eq(content_type)
    if subject_id:
        filter_expr = filter_expr & Attr("subject_id").eq(subject_id)
    if topic_id:
        filter_expr = filter_expr & Attr("topic_id").eq(topic_id)
    scan_kwargs: CurriculumSignalItem = {"FilterExpression": filter_expr}
    if limit:
        scan_kwargs["Limit"] = limit
    items: list[CurriculumSignalItem] = []
    while True:
        resp = _scan(table, **scan_kwargs)
        items.extend(_items(resp.get("Items", [])))
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return items


def scan_curriculum_signal_manifests(
    owner_id: str,
    *,
    cursor: Mapping[str, object] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> CurriculumSignalPage:
    """Strongly scan owner manifests plus legacy deterministic-hash signals."""
    target = table or get_table()
    marker = _cursor(cursor) if cursor is not None else None
    legacy_hash = _legacy_student_hash(owner_id)
    found: list[CurriculumSignalItem] = []
    for _ in range(maximum_pages):
        kwargs: CurriculumSignalItem = {"ConsistentRead": True}
        if marker:
            kwargs["ExclusiveStartKey"] = marker
        response = _scan(target, **kwargs)
        items = response.get("Items", [])
        for item in _items(items):
            if item.get("PK") == f"CURRICULUM_SIGNAL_OWNER#{owner_id}":
                found.append(item)
                continue
            metadata = item.get("metadata")
            if (
                item.get("entity_type") == SIGNAL_ENTITY
                and isinstance(metadata, Mapping)
                and metadata.get("studentHash") == legacy_hash
            ):
                found.append(_legacy_manifest(item, owner_id))
        raw_next = response.get("LastEvaluatedKey")
        if raw_next is None:
            return CurriculumSignalPage(tuple(found))
        next_marker = _cursor(raw_next)
        if next_marker == marker:
            raise account_deletion_repo.AccountDeletionConflict(
                "curriculum signal deletion cursor did not advance"
            )
        marker = next_marker
    return CurriculumSignalPage(tuple(found), marker)


def reconcile_curriculum_signal(
    manifest: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> str:
    """Delete one signal and reverse its metric contribution exactly once."""
    target = table or get_table()
    signal_id = str(manifest.get("signal_id") or "").strip()
    if not signal_id:
        raise account_deletion_repo.AccountDeletionConflict(
            "curriculum signal manifest is malformed"
        )
    operation_key = {
        "PK": f"CURRICULUM_SIGNAL_RECONCILE#{signal_id}",
        "SK": "RESULT",
    }
    if isinstance(target, _GetTable):
        existing = _get_item(target, Key=operation_key, ConsistentRead=True).get("Item")
        if isinstance(existing, Mapping) and existing.get("status") == "complete":
            return "reconciled"
    signal_field = f"signal_{manifest['signal_type']}_count"
    source_field = f"source_{manifest['source_type']}_count"
    operation = {
        **operation_key,
        "entity_type": RECONCILIATION_ENTITY,
        "signal_id": signal_id,
        "status": "complete",
        "reconciled_at": now_iso,
    }
    operations = [
        account_deletion_repo.deletion_fence_condition(owner_id, generation),
        {
            "Delete": {
                "Key": {
                    "PK": str(manifest["signal_pk"]),
                    "SK": str(manifest["signal_sk"]),
                },
                "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
            }
        },
        {
            "Update": {
                "Key": {
                    "PK": str(manifest["metric_pk"]),
                    "SK": str(manifest["metric_sk"]),
                },
                "UpdateExpression": (
                    "ADD #total_count :minus_one, #signal_count :minus_one, "
                    "#source_count :minus_one"
                ),
                "ConditionExpression": (
                    "attribute_exists(PK) AND #total_count >= :one AND "
                    "#signal_count >= :one AND #source_count >= :one"
                ),
                "ExpressionAttributeNames": {
                    "#total_count": "total_count",
                    "#signal_count": signal_field,
                    "#source_count": source_field,
                },
                "ExpressionAttributeValues": {":minus_one": -1, ":one": 1},
            }
        },
        {
            "Delete": {
                "Key": {"PK": str(manifest["PK"]), "SK": str(manifest["SK"])},
                "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
            }
        },
        {
            "Put": {
                "Item": operation,
                "ConditionExpression": ("attribute_not_exists(PK) AND attribute_not_exists(SK)"),
            }
        },
    ]
    try:
        account_deletion_repo.transact(operations, table=target)
    except account_deletion_repo.AccountDeletionConflict:
        if isinstance(target, _GetTable):
            existing = _get_item(target, Key=operation_key, ConsistentRead=True).get("Item")
            if isinstance(existing, Mapping) and existing.get("status") == "complete":
                return "reconciled"
        raise
    return "reconciled"


def _legacy_manifest(item: Mapping[str, object], owner_id: str) -> CurriculumSignalItem:
    signal_id = str(item.get("signal_id") or "")
    content_type = str(item.get("content_type") or "unknown")
    public_id = str(item.get("public_id") or "unknown")
    version_id = str(item.get("version_id") or "unknown")
    return {
        "PK": f"CURRICULUM_SIGNAL_OWNER#{owner_id}",
        "SK": f"SIGNAL#{signal_id}",
        "entity_type": OWNER_MANIFEST_ENTITY,
        "signal_id": signal_id,
        "signal_pk": item["PK"],
        "signal_sk": item["SK"],
        "metric_pk": f"CURRICULUM_METRIC#{content_type}#{public_id}",
        "metric_sk": f"VERSION#{version_id}",
        "signal_type": item["signal_type"],
        "source_type": item["source_type"],
        "legacy": True,
    }


def _legacy_student_hash(owner_id: str) -> str:
    from hashlib import sha256

    return f"student:{sha256(owner_id.encode('utf-8')).hexdigest()[:12]}"


def _cursor(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"PK", "SK"}:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid curriculum signal deletion cursor"
        )
    pk = value.get("PK")
    sk = value.get("SK")
    if not isinstance(pk, str) or not pk or not isinstance(sk, str) or not sk:
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid curriculum signal deletion cursor"
        )
    return {"PK": pk, "SK": sk}
