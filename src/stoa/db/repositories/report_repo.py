"""DynamoDB access patterns for the WeeklyReport entity."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, ConditionBase, Key
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


REPORT_PRIVATE_ROW_REGISTRY = {
    "report_summary": ("REPORT#", "SUMMARY"),
    "edit_draft": ("REPORT#", "EDIT_DRAFT#"),
    "artifact_edit_draft": ("REPORT#", "ARTIFACT_EDIT_DRAFT#"),
    "artifact_rollback_preview": ("REPORT#", "ARTIFACT_ROLLBACK_PREVIEW#"),
    "report_audit": ("REPORT#", "AUDIT#"),
    "recovery_summary": ("REPORT_RECOVERY_JOB#", "SUMMARY"),
    "recovery_target": ("REPORT_RECOVERY_JOB#", "TARGET#"),
    "recovery_audit": ("REPORT_RECOVERY_JOB#", "AUDIT#"),
    "retention_manifest": ("AUDIT_RETENTION#", "IMMUTABLE_MANIFEST"),
    "retention_audit": ("AUDIT_RETENTION#", "AUDIT#"),
    "support_audit": ("SUPPORT_HANDOFF#", "AUDIT#"),
    "support_delivery": ("SUPPORT_HANDOFF_DELIVERY#", "SUMMARY"),
    "support_delivery_audit": ("SUPPORT_HANDOFF_DELIVERY#", "AUDIT#"),
    "support_crm_message": ("SUPPORT_HANDOFF_DELIVERY#", "CRM_MESSAGE#"),
    "support_delivery_feed": ("SUPPORT_HANDOFF_DELIVERY_FEED", "SUMMARY#"),
    "support_crm_feed": ("SUPPORT_CRM_MESSAGE_FEED", "MESSAGE#"),
    "report_object_intent": ("USER#", "REPORT_OBJECT#"),
    "report_email_intent": ("USER#", "REPORT_EMAIL#"),
}

REPORT_WRITER_REGISTRY = frozenset(
    {
        "put_report",
        "try_claim_report_generation",
        "update_report_status",
        "try_apply_report_edit",
        "put_report_edit_draft",
        "mark_report_edit_draft_applied",
        "put_report_artifact_edit_draft",
        "mark_report_artifact_edit_draft_applied",
        "put_report_artifact_rollback_preview",
        "mark_report_artifact_rollback_preview_applied",
        "try_apply_report_artifact_edit",
        "put_report_audit_event",
        "put_recovery_job",
        "try_claim_recovery_job",
        "update_recovery_job_status",
        "try_claim_recovery_job_target",
        "update_recovery_job_target",
        "put_recovery_job_audit_event",
        "put_audit_retention_manifest",
        "put_audit_retention_audit_event",
        "put_support_handoff_audit_event",
        "put_support_handoff_delivery_record",
        "update_support_handoff_delivery_status",
        "put_support_handoff_delivery_audit_event",
        "put_support_crm_message_event",
    }
)

REPORT_PROVIDER_REGISTRY = frozenset(
    {"s3_put_object", "s3_delete_object", "ses_send_email", "crm_send"}
)

REPORT_PRIVATE_FIELDS = frozenset(
    {
        "summary",
        "strengths",
        "weak_topics",
        "weak_knowledge_points",
        "recommendations",
        "recommendation_items",
        "teacher_note",
        "student_name",
        "parent_email",
        "admin_note",
        "editor_summary",
        "status_note",
        "reason",
        "proposed_fields",
        "diff",
        "before",
        "after",
        "error_message",
        "detail",
        "metadata",
        "filters",
        "student_id",
        "parent_id",
        "actor",
        "created_by",
        "applied_by",
        "requested_by",
        "recipient",
        "subject",
        "body",
        "payload_summary",
        "provider_details",
        "json_s3_key",
        "html_s3_key",
        "s3_key",
        "source_json_s3_key",
        "source_html_s3_key",
        "target_json_s3_key",
        "target_html_s3_key",
        "object_key",
        "body_sha256",
        "etag",
        "version_id",
    }
)

REPORT_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "report_id",
        "job_id",
        "target_id",
        "manifest_id",
        "package_id",
        "delivery_id",
        "message_id",
        "event_id",
        "operation_id",
        "artifact_kind",
        "status",
        "state",
        "owner_deletion_generation",
        "privacy_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
        "accepted_at",
        "provider_acceptance",
        "policy_authority",
        "policy_scope",
        "hold_expires_at",
    }
)


type ReportItem = dict[str, object]


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
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ReportObjectReconciliationClient(Protocol):
    def list_object_versions(self, **kwargs: object) -> object: ...

    def head_object(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ReportObjectDeletionClient(Protocol):
    def delete_object(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ReportObjectVersionLister(Protocol):
    def list_object_versions(self, **kwargs: object) -> object: ...


@runtime_checkable
class _RegisterObjectIntentHook(Protocol):
    def register_report_object_intent(self, item: ReportItem) -> object: ...


@runtime_checkable
class _RecordObjectCoordinateHook(Protocol):
    def record_report_object_coordinate(
        self,
        intent: ReportItem,
        coordinate: dict[str, str],
        now_iso: str,
    ) -> object: ...


@runtime_checkable
class _RegisterEmailIntentHook(Protocol):
    def register_report_email_intent(self, item: ReportItem) -> object: ...


@runtime_checkable
class _ClaimEmailIntentHook(Protocol):
    def claim_report_email_intent(
        self,
        key: dict[str, str],
        generation: int,
        lease_id: str,
    ) -> object: ...


@runtime_checkable
class _ScrubPrivateRowHook(Protocol):
    def scrub_report_private_row(
        self,
        original: ReportItem,
        tombstone: ReportItem,
        owner_id: str,
        generation: int,
    ) -> object: ...


def _dependency_mapping(value: object) -> ReportItem:
    if not isinstance(value, Mapping):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed report dependency response"
        )
    result: ReportItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed report dependency response"
            )
        result[key] = member
    return result


def _optional_item(value: object) -> ReportItem | None:
    if value is None:
        return None
    return _dependency_mapping(value)


def _response_items(response: Mapping[str, object]) -> list[ReportItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise account_deletion_repo.AccountDeletionConflict(
            "malformed report dependency response"
        )
    return [_dependency_mapping(item) for item in raw_items]


def _provider_rows(value: object, error_message: str) -> list[ReportItem]:
    if not isinstance(value, list):
        raise account_deletion_repo.AccountDeletionConflict(error_message)
    try:
        return [_dependency_mapping(item) for item in value]
    except account_deletion_repo.AccountDeletionConflict as exc:
        raise account_deletion_repo.AccountDeletionConflict(error_message) from exc


def _pagination_mapping(value: object) -> ReportItem:
    if not isinstance(value, Mapping):
        raise ValueError("Invalid pagination token")
    result: ReportItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise ValueError("Invalid pagination token")
        result[key] = member
    return result


def _get_item(table: object, **kwargs: object) -> ReportItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "report dependency unavailable"
        )
    return _dependency_mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "report dependency unavailable"
        )
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> ReportItem:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "report dependency unavailable"
        )
    return _dependency_mapping(table.query(**kwargs))


def _scan(table: object, **kwargs: object) -> ReportItem:
    if not isinstance(table, _ScanTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "report dependency unavailable"
        )
    return _dependency_mapping(table.scan(**kwargs))


def _update_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict(
            "report dependency unavailable"
        )
    return table.update_item(**kwargs)


@dataclass(frozen=True, slots=True)
class ReportPrivatePage:
    items: tuple[ReportItem, ...]
    cursor: dict[str, str] | None = None
    unresolved: int = 0


def put_report(item: ReportItem) -> None:
    table = get_table()
    owner_id = item.get("student_id")
    generation = item.get("account_fence_generation")
    if isinstance(owner_id, str) and type(generation) is int and generation > 0:
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(owner_id, generation),
                {
                    "Put": {
                        "Item": {"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item},
                        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                    }
                },
            ],
            table=table,
        )
        return
    _put_item(table, Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item})


def try_claim_report_generation(item: ReportItem) -> bool:
    table = get_table()
    owner_id = item.get("student_id")
    generation = item.get("account_fence_generation")
    if isinstance(owner_id, str) and type(generation) is int and generation > 0:
        try:
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(owner_id, generation),
                    {
                        "Put": {
                            "Item": {"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item},
                            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                        }
                    },
                ],
                table=table,
            )
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True
    try:
        _put_item(
            table,
            Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_report_status(report_id: str, status: str, **fields: object) -> None:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    _update_item(
        table,
        Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def try_apply_report_edit(
    report_id: str,
    *,
    expected_updated_at: str | None,
    status: str,
    fields: ReportItem,
) -> bool:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    if expected_updated_at is None:
        condition = "attribute_not_exists(updated_at)"
    else:
        condition = "updated_at = :expected_updated_at"
        values[":expected_updated_at"] = expected_updated_at
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression="SET " + ", ".join(
                f"{name} = :v{index}" for index, name in enumerate(names)
            ),
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_edit_draft(report_id: str, draft: ReportItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"EDIT_DRAFT#{draft['draft_id']}",
            "entity_type": "REPORT_EDIT_DRAFT",
            **draft,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_edit_draft(report_id: str, draft_id: str) -> ReportItem | None:
    table = get_table()
    response = _get_item(
        table,
        Key={"PK": f"REPORT#{report_id}", "SK": f"EDIT_DRAFT#{draft_id}"}
    )
    return _optional_item(response.get("Item"))


def mark_report_edit_draft_applied(
    report_id: str,
    draft_id: str,
    *,
    applied_at: str,
    applied_by: str,
) -> bool:
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": f"EDIT_DRAFT#{draft_id}"},
            UpdateExpression=(
                "SET #status = :applied, applied_at = :applied_at, "
                "applied_by = :applied_by, updated_at = :applied_at"
            ),
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":applied": "applied",
                ":draft": "draft",
                ":applied_at": applied_at,
                ":applied_by": applied_by,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_artifact_edit_draft(report_id: str, draft: ReportItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"ARTIFACT_EDIT_DRAFT#{draft['draft_id']}",
            "entity_type": "REPORT_ARTIFACT_EDIT_DRAFT",
            **draft,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_artifact_edit_draft(report_id: str, draft_id: str) -> ReportItem | None:
    table = get_table()
    response = _get_item(
        table,
        Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_EDIT_DRAFT#{draft_id}"}
    )
    return _optional_item(response.get("Item"))


def mark_report_artifact_edit_draft_applied(
    report_id: str,
    draft_id: str,
    *,
    applied_at: str,
    applied_by: str,
    artifact_version_id: str,
) -> bool:
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_EDIT_DRAFT#{draft_id}"},
            UpdateExpression=(
                "SET #status = :applied, applied_at = :applied_at, "
                "applied_by = :applied_by, artifact_version_id = :artifact_version_id, "
                "updated_at = :applied_at"
            ),
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":applied": "applied",
                ":draft": "draft",
                ":applied_at": applied_at,
                ":applied_by": applied_by,
                ":artifact_version_id": artifact_version_id,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_artifact_rollback_preview(report_id: str, preview: ReportItem) -> None:
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview['preview_id']}",
            "entity_type": "REPORT_ARTIFACT_ROLLBACK_PREVIEW",
            **preview,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_artifact_rollback_preview(
    report_id: str, preview_id: str
) -> ReportItem | None:
    table = get_table()
    response = _get_item(
        table,
        Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview_id}"}
    )
    return _optional_item(response.get("Item"))


def mark_report_artifact_rollback_preview_applied(
    report_id: str,
    preview_id: str,
    *,
    applied_at: str,
    applied_by: str,
    artifact_version_id: str | None,
) -> bool:
    table = get_table()
    values = {
        ":applied": "applied",
        ":draft": "draft",
        ":applied_at": applied_at,
        ":applied_by": applied_by,
    }
    update_expression = (
        "SET #status = :applied, applied_at = :applied_at, "
        "applied_by = :applied_by, updated_at = :applied_at"
    )
    if artifact_version_id is not None:
        update_expression += ", artifact_version_id = :artifact_version_id"
        values[":artifact_version_id"] = artifact_version_id
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview_id}"},
            UpdateExpression=update_expression,
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def try_apply_report_artifact_edit(
    report_id: str,
    *,
    expected_updated_at: str | None,
    expected_artifact_version_id: str | None,
    expected_json_s3_key: str | None,
    expected_html_s3_key: str | None,
    status: str,
    fields: ReportItem,
) -> bool:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    conditions = []
    if expected_updated_at is None:
        conditions.append("attribute_not_exists(updated_at)")
    else:
        conditions.append("updated_at = :expected_updated_at")
        values[":expected_updated_at"] = expected_updated_at
    if expected_artifact_version_id is None:
        conditions.append("attribute_not_exists(artifact_version_id)")
    else:
        conditions.append("artifact_version_id = :expected_artifact_version_id")
        values[":expected_artifact_version_id"] = expected_artifact_version_id
    if expected_json_s3_key is not None:
        conditions.append("json_s3_key = :expected_json_s3_key")
        values[":expected_json_s3_key"] = expected_json_s3_key
    if expected_html_s3_key is not None:
        conditions.append("html_s3_key = :expected_html_s3_key")
        values[":expected_html_s3_key"] = expected_html_s3_key
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression="SET " + ", ".join(
                f"{name} = :v{index}" for index, name in enumerate(names)
            ),
            ConditionExpression=" AND ".join(conditions),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_audit_event(report_id: str, event: ReportItem) -> None:
    """Append one immutable report audit event."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "REPORT_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_recovery_job_audit_event(job_id: str, event: ReportItem) -> None:
    """Append one immutable recovery job audit event."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT_RECOVERY_JOB#{job_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "REPORT_RECOVERY_JOB_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_support_handoff_audit_event(package_id: str, event: ReportItem) -> None:
    """Append one immutable support handoff audit event."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"SUPPORT_HANDOFF#{package_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "SUPPORT_HANDOFF_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_support_handoff_delivery_record(delivery_id: str) -> ReportItem | None:
    """Return the current support handoff delivery summary, if present."""
    table = get_table()
    response = _get_item(
        table,
        Key={"PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}", "SK": "SUMMARY"},
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def _support_handoff_delivery_feed_item(delivery: ReportItem) -> ReportItem:
    created_at = delivery.get("created_at") or delivery.get("updated_at") or ""
    delivery_id = delivery["delivery_id"]
    return {
        **delivery,
        "PK": "SUPPORT_HANDOFF_DELIVERY_FEED",
        "SK": f"SUMMARY#{created_at}#{delivery_id}",
        "entity_type": "SUPPORT_HANDOFF_DELIVERY_FEED",
    }


def _put_support_handoff_delivery_feed_item(
    table: object, delivery: ReportItem
) -> None:
    _put_item(table, Item=_support_handoff_delivery_feed_item(delivery))


def put_support_handoff_delivery_record(
    delivery_id: str, delivery: ReportItem
) -> tuple[ReportItem, bool]:
    """Persist one provider-neutral support handoff delivery summary.

    Returns `(record, created)`. Duplicate deterministic delivery IDs reuse the
    existing row so repeated requests remain idempotent.
    """
    table = get_table()
    item = {
        "PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}",
        "SK": "SUMMARY",
        "entity_type": "SUPPORT_HANDOFF_DELIVERY",
        **delivery,
    }
    try:
        _put_item(
            table,
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            existing = get_support_handoff_delivery_record(delivery_id)
            if existing:
                _put_support_handoff_delivery_feed_item(table, existing)
                return existing, False
        raise
    _put_support_handoff_delivery_feed_item(table, item)
    return item, True


def update_support_handoff_delivery_status(
    delivery_id: str,
    *,
    status: str,
    updated_at: str,
    actor: str,
    correlation_id: str | None = None,
    retry_count: int | None = None,
    retryable: bool | None = None,
    refusal_reasons: list[str] | None = None,
    failure_reasons: list[str] | None = None,
    extra_updates: ReportItem | None = None,
) -> ReportItem | None:
    """Update one delivery lifecycle status and keep its feed row current."""
    existing = get_support_handoff_delivery_record(delivery_id)
    if not existing:
        return None
    updated = {
        **existing,
        "status": status,
        "lifecycle_status": status,
        "updated_at": updated_at,
        "actor": actor or existing.get("actor"),
        "correlation_id": correlation_id if correlation_id is not None else existing.get("correlation_id"),
        "retry_count": retry_count if retry_count is not None else existing.get("retry_count", 0),
        "retryable": retryable if retryable is not None else existing.get("retryable", False),
        "refusal_reasons": refusal_reasons if refusal_reasons is not None else existing.get("refusal_reasons", []),
        "failure_reasons": failure_reasons if failure_reasons is not None else existing.get("failure_reasons", []),
    }
    if extra_updates:
        updated.update(extra_updates)
    table = get_table()
    _put_item(
        table,
        Item={
            **updated,
            "PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}",
            "SK": "SUMMARY",
            "entity_type": "SUPPORT_HANDOFF_DELIVERY",
        }
    )
    _put_support_handoff_delivery_feed_item(table, updated)
    return updated


def put_support_handoff_delivery_audit_event(
    delivery_id: str, event: ReportItem
) -> None:
    """Append one immutable support handoff delivery lifecycle event."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "SUPPORT_HANDOFF_DELIVERY_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_support_crm_message_event(delivery_id: str, event: ReportItem) -> None:
    """Persist one metadata-only support CRM/customer message outcome."""
    table = get_table()
    item = {
        "PK": f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}",
        "SK": f"CRM_MESSAGE#{event['event_at']}#{event['message_id']}",
        "entity_type": "SUPPORT_CRM_MESSAGE_EVENT",
        **event,
    }
    _put_item(
        table,
        Item=item,
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )
    _put_item(
        table,
        Item={
            **item,
            "PK": "SUPPORT_CRM_MESSAGE_FEED",
            "SK": f"MESSAGE#{event['event_at']}#{event['message_id']}",
            "entity_type": "SUPPORT_CRM_MESSAGE_FEED",
        }
    )


def list_support_crm_message_events(
    *, limit: int = 100, last_key: ReportItem | None = None
) -> ReportItem:
    """List recent metadata-only support CRM/customer message outcomes."""
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq("SUPPORT_CRM_MESSAGE_FEED") & Key("SK").begins_with("MESSAGE#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def list_support_handoff_delivery_summaries(
    *,
    status: str | None = None,
    destination_mode: str | None = None,
    package_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq("SUPPORT_HANDOFF_DELIVERY_FEED")
        & Key("SK").begins_with("SUMMARY#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    filter_expr = _support_handoff_delivery_filter_expression(
        status=status,
        destination_mode=destination_mode,
        package_id=package_id,
        date_from=date_from,
        date_to=date_to,
    )
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    result = _query(table, **kwargs)
    items = _response_items(result)
    if last_key is None and len(items) < limit:
        fallback = _scan_support_handoff_delivery_summaries(
            status=status,
            destination_mode=destination_mode,
            package_id=package_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit - len(items),
        )
        existing_ids = {item.get("delivery_id") for item in items}
        for item in _response_items(fallback):
            if item.get("delivery_id") in existing_ids:
                continue
            _put_support_handoff_delivery_feed_item(table, item)
            items.append(item)
            existing_ids.add(item.get("delivery_id"))
        result["Items"] = items
    return result


def list_support_handoff_delivery_audit_events(
    delivery_id: str,
    *,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"SUPPORT_HANDOFF_DELIVERY#{delivery_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def put_audit_retention_audit_event(manifest_id: str, event: ReportItem) -> None:
    """Append one metadata-only audit retention event."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"AUDIT_RETENTION#{manifest_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "AUDIT_RETENTION_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_audit_retention_manifest(manifest_id: str, manifest: ReportItem) -> bool:
    """Persist one immutable-evidence manifest reference without overwriting."""
    table = get_table()
    try:
        _put_item(
            table,
            Item={
                "PK": f"AUDIT_RETENTION#{manifest_id}",
                "SK": "IMMUTABLE_MANIFEST",
                "entity_type": "AUDIT_RETENTION_IMMUTABLE_MANIFEST",
                **manifest,
            },
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_audit_retention_manifest(manifest_id: str) -> ReportItem | None:
    """Read one persisted immutable-evidence manifest reference."""
    response = _get_item(
        get_table(),
        Key={"PK": f"AUDIT_RETENTION#{manifest_id}", "SK": "IMMUTABLE_MANIFEST"}
    )
    return _optional_item(response.get("Item"))


def update_audit_retention_manifest_status(
    manifest_id: str,
    fields: ReportItem,
    *,
    expected_status: str,
) -> bool:
    """Conditionally transition one immutable-evidence manifest reference."""
    update_fields = dict(fields)
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    names["#status"] = "status"
    values[":expected_status"] = expected_status
    try:
        _update_item(
            get_table(),
            Key={"PK": f"AUDIT_RETENTION#{manifest_id}", "SK": "IMMUTABLE_MANIFEST"},
            UpdateExpression="SET " + ", ".join(
                f"{name} = :v{index}" for index, name in enumerate(names) if name != "#status"
            ),
            ConditionExpression="#status = :expected_status",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_legal_hold_metadata(
    scope_key: str,
    hold: ReportItem,
    *,
    expected_hold_version: int | None = None,
    expected_updated_at: str | None = None,
) -> bool:
    """Conditionally store current metadata-only legal hold state for an evidence scope."""
    values: dict[str, object] = {}
    if expected_hold_version is not None:
        condition = "hold_version = :expected_hold_version"
        values[":expected_hold_version"] = expected_hold_version
    elif expected_updated_at is not None:
        condition = "updated_at = :expected_updated_at"
        values[":expected_updated_at"] = expected_updated_at
    else:
        condition = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    put_kwargs = {
        "Item": {
            "PK": f"LEGAL_HOLD#{scope_key}",
            "SK": "SUMMARY",
            "entity_type": "LEGAL_HOLD_METADATA",
            **hold,
        },
        "ConditionExpression": condition,
    }
    if values:
        put_kwargs["ExpressionAttributeValues"] = values
    try:
        _put_item(get_table(), **put_kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_legal_hold_metadata(scope_key: str) -> ReportItem | None:
    """Read current metadata-only legal hold state for an evidence scope."""
    response = _get_item(
        get_table(),
        Key={"PK": f"LEGAL_HOLD#{scope_key}", "SK": "SUMMARY"},
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def put_legal_hold_audit_event(scope_key: str, event: ReportItem) -> None:
    """Append one metadata-only legal hold audit event."""
    _put_item(
        get_table(),
        Item={
            "PK": f"LEGAL_HOLD#{scope_key}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "LEGAL_HOLD_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_retention_approval_metadata(
    policy_version: str,
    approval: ReportItem,
    *,
    expected_approval_version: int | None = None,
) -> bool:
    """Conditionally store current metadata-only retention approval state."""
    values = {}
    if expected_approval_version is not None:
        condition = "approval_version = :expected_approval_version"
        values[":expected_approval_version"] = expected_approval_version
    else:
        condition = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    put_kwargs = {
        "Item": {
            "PK": f"RETENTION_APPROVAL#{policy_version}",
            "SK": "SUMMARY",
            "entity_type": "RETENTION_APPROVAL_METADATA",
            **approval,
        },
        "ConditionExpression": condition,
    }
    if values:
        put_kwargs["ExpressionAttributeValues"] = values
    try:
        _put_item(get_table(), **put_kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_retention_approval_metadata(policy_version: str) -> ReportItem | None:
    """Read current metadata-only retention approval state."""
    response = _get_item(
        get_table(),
        Key={"PK": f"RETENTION_APPROVAL#{policy_version}", "SK": "SUMMARY"},
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def put_retention_approval_audit_event(
    policy_version: str, event: ReportItem
) -> None:
    """Append one metadata-only retention approval audit event."""
    _put_item(
        get_table(),
        Item={
            "PK": f"RETENTION_APPROVAL#{policy_version}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "RETENTION_APPROVAL_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_legal_hold_review_metadata(
    scope_key: str,
    review: ReportItem,
    *,
    expected_review_version: int | None = None,
) -> bool:
    """Store latest metadata-only legal-hold review state for an evidence scope."""
    values = {}
    if expected_review_version is not None:
        condition = "review_version = :expected_review_version"
        values[":expected_review_version"] = expected_review_version
    else:
        condition = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
    put_kwargs = {
        "Item": {
            "PK": f"LEGAL_HOLD#{scope_key}",
            "SK": "REVIEW_SUMMARY",
            "entity_type": "LEGAL_HOLD_REVIEW_METADATA",
            **review,
        },
        "ConditionExpression": condition,
    }
    if values:
        put_kwargs["ExpressionAttributeValues"] = values
    try:
        _put_item(get_table(), **put_kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_legal_hold_review_metadata(scope_key: str) -> ReportItem | None:
    """Read latest metadata-only legal-hold review state for an evidence scope."""
    response = _get_item(
        get_table(),
        Key={"PK": f"LEGAL_HOLD#{scope_key}", "SK": "REVIEW_SUMMARY"},
        ConsistentRead=True,
    )
    return _optional_item(response.get("Item"))


def put_recovery_job(job: ReportItem, targets: list[ReportItem]) -> None:
    """Persist one recovery job and its stable target snapshot."""
    table = get_table()
    _put_item(
        table,
        Item={
            "PK": f"REPORT_RECOVERY_JOB#{job['job_id']}",
            "SK": "SUMMARY",
            "entity_type": "REPORT_RECOVERY_JOB",
            **job,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )
    for index, target in enumerate(targets):
        _put_item(
            table,
            Item={
                "PK": f"REPORT_RECOVERY_JOB#{job['job_id']}",
                "SK": f"TARGET#{index:05d}#{target['target_id']}",
                "entity_type": "REPORT_RECOVERY_JOB_TARGET",
                "job_id": job["job_id"],
                "target_index": index,
                **target,
            },
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )


def get_recovery_job(job_id: str) -> ReportItem | None:
    table = get_table()
    response = _get_item(
        table,
        Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
    )
    return _optional_item(response.get("Item"))


def list_recovery_jobs(
    *, limit: int = 50, last_key: ReportItem | None = None
) -> ReportItem:
    table = get_table()
    kwargs = {
        "FilterExpression": Attr("PK").begins_with("REPORT_RECOVERY_JOB#") & Attr("SK").eq("SUMMARY"),
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _scan(table, **kwargs)


def list_recovery_job_targets(
    job_id: str,
    *,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT_RECOVERY_JOB#{job_id}") & Key("SK").begins_with("TARGET#"),
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def try_claim_recovery_job(job_id: str, *, started_at: str) -> bool:
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
            UpdateExpression="SET #status = :running, started_at = if_not_exists(started_at, :started_at), updated_at = :started_at",
            ConditionExpression="#status = :queued",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":running": "running",
                ":queued": "queued",
                ":started_at": started_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def request_recovery_job_cancellation(job_id: str, *, requested_by: str, requested_at: str) -> bool:
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :cancellation_requested, "
                "cancellation_requested_by = :requested_by, "
                "cancellation_requested_at = :requested_at, "
                "updated_at = :requested_at"
            ),
            ConditionExpression="#status IN (:queued, :running)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":cancellation_requested": "cancellation_requested",
                ":queued": "queued",
                ":running": "running",
                ":requested_by": requested_by,
                ":requested_at": requested_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_recovery_job_status(job_id: str, status: str, **fields: object) -> None:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    _update_item(
        table,
        Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def try_claim_recovery_job_target(job_id: str, target_sk: str, *, attempted_at: str) -> bool:
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": target_sk},
            UpdateExpression="SET #result = :in_progress, attempted_at = :attempted_at, updated_at = :attempted_at",
            ConditionExpression="#result = :pending",
            ExpressionAttributeNames={"#result": "result"},
            ExpressionAttributeValues={
                ":in_progress": "in_progress",
                ":pending": "pending",
                ":attempted_at": attempted_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_recovery_job_target(
    job_id: str,
    target_sk: str,
    result: str,
    **fields: object,
) -> None:
    table = get_table()
    update_fields = {"result": result, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    _update_item(
        table,
        Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": target_sk},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def list_report_audit_events(
    report_id: str,
    *,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT#{report_id}") & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def list_recovery_job_audit_events(
    job_id: str,
    *,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT_RECOVERY_JOB#{job_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def list_support_handoff_audit_events(
    package_id: str,
    *,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"SUPPORT_HANDOFF#{package_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def try_start_generation_retry(report_id: str, *, operator: str, attempted_at: str) -> bool:
    """Atomically claim a generation-failed report for one admin retry."""
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :retrying, "
                "generation_retry_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            ConditionExpression="#status = :expected",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":retrying": "generation_retrying",
                ":expected": "generation_failed",
                ":attempted_at": attempted_at,
                ":operation": "retry_generation",
                ":operator": operator,
                ":in_progress": "in_progress",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def try_claim_report_resend(report_id: str, *, operator: str, attempted_at: str) -> bool:
    """Atomically claim a failed email report before resend side effects."""
    table = get_table()
    try:
        _update_item(
            table,
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :resending, "
                "resend_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            ConditionExpression="#status = :email_failed OR email_status = :failed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":resending": "email_resending",
                ":email_failed": "email_failed",
                ":failed": "failed",
                ":attempted_at": attempted_at,
                ":operation": "resend_email",
                ":operator": operator,
                ":in_progress": "in_progress",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_report_by_week(parent_id: str, week_start: str) -> ReportItem | None:
    table = get_table()
    resp = _query(
        table,
        IndexName="GSI-ParentId",
        KeyConditionExpression=Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        Limit=1,
    )
    items = _response_items(resp)
    return items[0] if items else None


def get_report_for_child_by_week(
    parent_id: str, student_id: str, week_start: str
) -> ReportItem | None:
    last_key: ReportItem | None = None
    while True:
        result = list_reports_for_parent_week(parent_id, week_start, last_key=last_key)
        for item in _response_items(result):
            if item.get("SK") == "SUMMARY" and item.get("student_id") == student_id:
                return item
        raw_last_key = result.get("LastEvaluatedKey")
        if raw_last_key is None:
            return None
        if not isinstance(raw_last_key, Mapping):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed report dependency response"
            )
        last_key = _dependency_mapping(raw_last_key)


def encode_page_token(last_key: ReportItem | None) -> str | None:
    """Encode a DynamoDB LastEvaluatedKey as an opaque API token."""
    if not last_key:
        return None
    raw = json.dumps(last_key, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_page_token(token: str | None) -> ReportItem | None:
    """Decode an opaque API token into a DynamoDB ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = _pagination_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if not _is_valid_report_page_key(decoded):
        raise ValueError("Invalid pagination token")
    return decoded


def encode_admin_page_token(last_key: ReportItem | None) -> str | None:
    """Encode an admin report-ops page token.

    Cross-parent admin listing uses DynamoDB Scan with a FilterExpression. Scan
    pagination keys can point at any item in the single-table design, not only
    report summary rows. Keep normal report page tokens strict, but allow admin
    report ops to round-trip the scan key it received from DynamoDB.
    """
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "admin_reports", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_admin_page_token(token: str | None) -> ReportItem | None:
    """Decode an admin report-ops page token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = _pagination_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_admin_page_payload(decoded):
        return _pagination_mapping(decoded.get("key"))
    # Backward compatibility for older admin report tokens that encoded the
    # report LastEvaluatedKey directly.
    if _is_valid_report_page_key(decoded):
        return decoded
    raise ValueError("Invalid pagination token")


def encode_audit_page_token(last_key: ReportItem | None) -> str | None:
    """Encode an audit timeline page token."""
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "report_audit", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_audit_page_token(token: str | None) -> ReportItem | None:
    """Decode an audit timeline page token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = _pagination_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_audit_page_payload(decoded):
        return _pagination_mapping(decoded.get("key"))
    raise ValueError("Invalid pagination token")


def encode_recovery_job_page_token(last_key: ReportItem | None) -> str | None:
    """Encode recovery job list/result pagination keys."""
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "recovery_jobs", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_recovery_job_page_token(token: str | None) -> ReportItem | None:
    """Decode recovery job pagination token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = _pagination_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_recovery_job_page_payload(decoded):
        return _pagination_mapping(decoded.get("key"))
    raise ValueError("Invalid pagination token")


def encode_support_handoff_delivery_page_token(
    last_key: ReportItem | None,
) -> str | None:
    """Encode support handoff delivery list/audit pagination keys."""
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "support_handoff_delivery", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_support_handoff_delivery_page_token(
    token: str | None,
) -> ReportItem | None:
    """Decode support handoff delivery pagination token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = _pagination_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_support_handoff_delivery_page_payload(decoded):
        return _pagination_mapping(decoded.get("key"))
    raise ValueError("Invalid pagination token")


def list_reports_for_admin(
    *,
    status: str | None = None,
    week_start: str | None = None,
    parent_id: str | None = None,
    student_id: str | None = None,
    limit: int = 50,
    last_key: ReportItem | None = None,
) -> ReportItem:
    """List report summary rows for admin operations.

    Parent-filtered access uses the existing parent/week GSI where possible.
    Cross-parent admin access uses a bounded scan for pilot volume; callers must
    pass a strict limit and preserve LastEvaluatedKey pagination.
    """
    if parent_id:
        return _list_reports_for_admin_parent_query(
            parent_id=parent_id,
            status=status,
            week_start=week_start,
            student_id=student_id,
            limit=limit,
            last_key=last_key,
        )
    return _list_reports_for_admin_scan(
        status=status,
        week_start=week_start,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
    )


def _list_reports_for_admin_parent_query(
    *,
    parent_id: str,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: ReportItem | None,
) -> ReportItem:
    table = get_table()
    key_expr: ConditionBase = Key("parent_id").eq(parent_id)
    if week_start:
        key_expr = key_expr & Key("week_start").eq(week_start)

    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": key_expr,
        "Limit": limit,
        "ScanIndexForward": False,
    }
    filter_expr = _admin_report_filter_expression(status=status, student_id=student_id)
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def _list_reports_for_admin_scan(
    *,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: ReportItem | None,
) -> ReportItem:
    table = get_table()
    filter_expr = Attr("PK").begins_with("REPORT#") & Attr("SK").eq("SUMMARY")
    extra_filter = _admin_report_filter_expression(
        status=status,
        week_start=week_start,
        student_id=student_id,
    )
    if extra_filter is not None:
        filter_expr = filter_expr & extra_filter
    kwargs = {
        "FilterExpression": filter_expr,
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _scan(table, **kwargs)


def _admin_report_filter_expression(
    *,
    status: str | None = None,
    week_start: str | None = None,
    student_id: str | None = None,
) -> ConditionBase | None:
    filter_expr: ConditionBase | None = None
    if status:
        filter_expr = Attr("status").eq(status)
    if week_start:
        week_filter = Attr("week_start").eq(week_start)
        filter_expr = week_filter if filter_expr is None else filter_expr & week_filter
    if student_id:
        student_filter = Attr("student_id").eq(student_id)
        filter_expr = student_filter if filter_expr is None else filter_expr & student_filter
    return filter_expr


def _support_handoff_delivery_filter_expression(
    *,
    status: str | None,
    destination_mode: str | None,
    package_id: str | None,
    date_from: str | None,
    date_to: str | None,
) -> ConditionBase | None:
    filter_expr: ConditionBase | None = None
    if status:
        filter_expr = Attr("status").eq(status)
    if destination_mode:
        destination_filter = Attr("destination_mode").eq(destination_mode)
        filter_expr = destination_filter if filter_expr is None else filter_expr & destination_filter
    if package_id:
        package_filter = Attr("package_id").eq(package_id)
        filter_expr = package_filter if filter_expr is None else filter_expr & package_filter
    if date_from:
        from_filter = Attr("created_at").gte(date_from)
        filter_expr = from_filter if filter_expr is None else filter_expr & from_filter
    if date_to:
        to_filter = Attr("created_at").lte(date_to)
        filter_expr = to_filter if filter_expr is None else filter_expr & to_filter
    return filter_expr


def _scan_support_handoff_delivery_summaries(
    *,
    status: str | None,
    destination_mode: str | None,
    package_id: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
) -> ReportItem:
    if limit <= 0:
        return {"Items": []}
    table = get_table()
    filter_expr = Attr("PK").begins_with("SUPPORT_HANDOFF_DELIVERY#") & Attr("SK").eq("SUMMARY")
    extra_filter = _support_handoff_delivery_filter_expression(
        status=status,
        destination_mode=destination_mode,
        package_id=package_id,
        date_from=date_from,
        date_to=date_to,
    )
    if extra_filter is not None:
        filter_expr = filter_expr & extra_filter
    result = _scan(table, FilterExpression=filter_expr, Limit=limit)
    items = sorted(
        _response_items(result),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("delivery_id") or "")),
        reverse=True,
    )
    return {"Items": items[:limit]}


def _is_valid_report_page_key(decoded: Mapping[str, object]) -> bool:
    pk = decoded.get("PK")
    sk = decoded.get("SK")
    return (
        isinstance(pk, str)
        and pk.startswith("REPORT#")
        and isinstance(sk, str)
        and sk == "SUMMARY"
    )


def _is_valid_admin_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "admin_reports":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return isinstance(pk, str) and isinstance(sk, str)


def _is_valid_audit_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "report_audit":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return (
        isinstance(pk, str)
        and (
            pk.startswith("REPORT#")
            or pk.startswith("REPORT_RECOVERY_JOB#")
        )
        and isinstance(sk, str)
        and sk.startswith("AUDIT#")
    )


def _is_valid_recovery_job_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "recovery_jobs":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return isinstance(pk, str) and pk.startswith("REPORT_RECOVERY_JOB#") and isinstance(sk, str)


def _is_valid_support_handoff_delivery_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "support_handoff_delivery":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    if not isinstance(pk, str) or not isinstance(sk, str):
        return False
    return (
        pk == "SUPPORT_HANDOFF_DELIVERY_FEED"
        and sk.startswith("SUMMARY#")
    ) or (
        pk.startswith("SUPPORT_HANDOFF_DELIVERY#")
        and sk.startswith("AUDIT#")
    )


def list_reports_for_parent_week(
    parent_id: str,
    week_start: str,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        "FilterExpression": Attr("SK").eq("SUMMARY"),
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def list_reports_for_parent(
    parent_id: str,
    limit: int = 25,
    last_key: ReportItem | None = None,
) -> ReportItem:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id),
        "FilterExpression": Attr("SK").eq("SUMMARY"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def _required_private_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise account_deletion_repo.AccountDeletionConflict(f"{name} is required")
    return value.strip()


def _validated_report_cursor(value: Mapping[str, object]) -> dict[str, str]:
    if set(value) != {"PK", "SK"}:
        raise account_deletion_repo.AccountDeletionConflict("invalid report cursor")
    return {
        "PK": _required_private_string(value.get("PK"), "cursor PK"),
        "SK": _required_private_string(value.get("SK"), "cursor SK"),
    }


def register_report_object_intent(
    *,
    owner_id: str,
    generation: int,
    operation_id: str,
    artifact_kind: str,
    report_id: str | None,
    object_key: str,
    body: bytes,
    now_iso: str,
    table: object | None = None,
    manifest_id: str | None = None,
) -> ReportItem:
    """Persist exact object identity before a private provider write."""
    if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
        raise account_deletion_repo.AccountDeletionConflict("invalid report generation")
    if not isinstance(body, bytes):
        raise account_deletion_repo.AccountDeletionConflict("report object body must be bytes")
    owner = _required_private_string(owner_id, "owner_id")
    operation = _required_private_string(operation_id, "operation_id")
    kind = _required_private_string(artifact_kind, "artifact_kind")
    item = {
        "PK": f"USER#{owner}",
        "SK": f"REPORT_OBJECT#{operation}#{kind}",
        "entity_type": "report_object_intent",
        "schema_version": "report-object-intent.v1",
        "owner_id": owner,
        "account_fence_generation": generation,
        "operation_id": operation,
        "artifact_kind": kind,
        "report_id": report_id,
        "manifest_id": manifest_id,
        "object_key": _required_private_string(object_key, "object_key"),
        "body_sha256": sha256(body).hexdigest(),
        "body_length": len(body),
        "state": "registered",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    target = table or get_table()
    if isinstance(target, _RegisterObjectIntentHook):
        persisted = target.register_report_object_intent(dict(item))
        return _dependency_mapping(persisted) if persisted is not None else item
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(owner, generation),
            {
                "Put": {
                    "Item": item,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ],
        table=target,
    )
    return item


def parse_report_object_ack(response: Mapping[str, object]) -> dict[str, str]:
    version_id = _required_private_string(response.get("VersionId"), "VersionId")
    raw_etag = _required_private_string(response.get("ETag"), "ETag")
    etag = raw_etag.strip('"')
    if not etag or etag != raw_etag.strip().strip('"'):
        raise account_deletion_repo.AccountDeletionConflict("invalid report object ETag")
    return {"version_id": version_id, "etag": etag}


def record_report_object_coordinate(
    intent: Mapping[str, object],
    coordinate: Mapping[str, str],
    *,
    now_iso: str,
    table: object | None = None,
) -> ReportItem:
    """Link only an exact registered intent while its owner remains active."""
    owner = _required_private_string(intent.get("owner_id"), "owner_id")
    generation = intent.get("account_fence_generation")
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise account_deletion_repo.AccountDeletionConflict("invalid object generation")
    version_id = _required_private_string(coordinate.get("version_id"), "version_id")
    etag = _required_private_string(coordinate.get("etag"), "etag")
    updated = {
        **intent,
        "version_id": version_id,
        "etag": etag,
        "state": "linked",
        "updated_at": now_iso,
    }
    target = table or get_table()
    if isinstance(target, _RecordObjectCoordinateHook):
        persisted = target.record_report_object_coordinate(
            dict(intent), dict(coordinate), now_iso
        )
        return _dependency_mapping(persisted) if persisted is not None else updated
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(owner, generation),
            {
                "Update": {
                    "Key": {"PK": str(intent["PK"]), "SK": str(intent["SK"])},
                    "UpdateExpression": (
                        "SET #state=:linked, version_id=:version, etag=:etag, updated_at=:now"
                    ),
                    "ConditionExpression": (
                        "#state=:registered AND account_fence_generation=:generation "
                        "AND body_sha256=:checksum AND object_key=:object_key"
                    ),
                    "ExpressionAttributeNames": {"#state": "state"},
                    "ExpressionAttributeValues": {
                        ":linked": "linked",
                        ":registered": "registered",
                        ":generation": generation,
                        ":checksum": intent["body_sha256"],
                        ":object_key": intent["object_key"],
                        ":version": version_id,
                        ":etag": etag,
                        ":now": now_iso,
                    },
                }
            },
        ],
        table=target,
    )
    return updated


def reconcile_report_object_version(
    *,
    s3_client: object,
    bucket: str,
    object_key: str,
    operation_id: str,
    body_sha256: str,
    body_length: int,
    maximum_pages: int = 100,
) -> dict[str, str]:
    """Recover one commit-then-raise S3 write from exact metadata and bytes."""
    if not isinstance(s3_client, _ReportObjectReconciliationClient):
        raise account_deletion_repo.AccountDeletionConflict(
            "report object dependency unavailable"
        )
    request: dict[str, object] = {"Bucket": bucket, "Prefix": object_key}
    seen: set[tuple[str, str]] = set()
    for _ in range(maximum_pages):
        page = _dependency_mapping(s3_client.list_object_versions(**request))
        for raw in _provider_rows(
            page.get("Versions", []), "malformed object version page"
        ):
            if raw.get("Key") != object_key:
                continue
            version_id = _required_private_string(raw.get("VersionId"), "VersionId")
            head = _dependency_mapping(
                s3_client.head_object(
                    Bucket=bucket,
                    Key=object_key,
                    VersionId=version_id,
                )
            )
            metadata = head.get("Metadata")
            if not isinstance(metadata, Mapping):
                continue
            if (
                metadata.get("operation-id") == operation_id
                and metadata.get("body-sha256") == body_sha256
                and head.get("ContentLength") == body_length
            ):
                parsed = parse_report_object_ack(head)
                if parsed["version_id"] != version_id:
                    raise account_deletion_repo.AccountDeletionConflict("object version mismatch")
                return parsed
        if page.get("IsTruncated") is not True:
            break
        key_marker = _required_private_string(page.get("NextKeyMarker"), "NextKeyMarker")
        version_marker = _required_private_string(
            page.get("NextVersionIdMarker"), "NextVersionIdMarker"
        )
        marker = (key_marker, version_marker)
        if marker in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeating object version marker")
        seen.add(marker)
        request["KeyMarker"] = key_marker
        request["VersionIdMarker"] = version_marker
    raise account_deletion_repo.AccountDeletionConflict("report object response unresolved")


def register_report_email_intent(
    *,
    owner_id: str,
    generation: int,
    operation_id: str,
    report_id: str,
    recipient: str,
    subject: str,
    body: str,
    now_iso: str,
    table: object | None = None,
) -> ReportItem:
    owner = _required_private_string(owner_id, "owner_id")
    operation = _required_private_string(operation_id, "operation_id")
    recipient_value = _required_private_string(recipient, "recipient")
    subject_value = _required_private_string(subject, "subject")
    body_value = _required_private_string(body, "body")
    item = {
        "PK": f"USER#{owner}",
        "SK": f"REPORT_EMAIL#{operation}",
        "entity_type": "report_email_intent",
        "schema_version": "report-email-intent.v1",
        "owner_id": owner,
        "account_fence_generation": generation,
        "operation_id": operation,
        "report_id": _required_private_string(report_id, "report_id"),
        "recipient_digest": sha256(recipient_value.encode()).hexdigest(),
        "content_digest": sha256(
            (subject_value + "\0" + body_value).encode()
        ).hexdigest(),
        "state": "registered",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    target = table or get_table()
    if isinstance(target, _RegisterEmailIntentHook):
        persisted = target.register_report_email_intent(dict(item))
        return _dependency_mapping(persisted) if persisted is not None else item
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(owner, generation),
            {
                "Put": {
                    "Item": item,
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ],
        table=target,
    )
    return item


def claim_report_email_intent(
    intent: Mapping[str, object], *, lease_id: str, table: object | None = None
) -> ReportItem:
    owner = _required_private_string(intent.get("owner_id"), "owner_id")
    generation = intent.get("account_fence_generation")
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise account_deletion_repo.AccountDeletionConflict("invalid email generation")
    target = table or get_table()
    key = {"PK": str(intent["PK"]), "SK": str(intent["SK"])}
    if isinstance(target, _ClaimEmailIntentHook):
        claimed = target.claim_report_email_intent(key, generation, lease_id)
        if claimed is None:
            raise account_deletion_repo.AccountDeletionConflict("email claim unavailable")
        return _dependency_mapping(claimed)
    account_deletion_repo.require_active_account_fence(owner, generation, table=target)
    response = _update_item(
        target,
        Key=key,
        UpdateExpression="SET #state=:claimed, lease_id=:lease",
        ConditionExpression="#state=:registered AND account_fence_generation=:generation",
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues={
            ":claimed": "claimed",
            ":registered": "registered",
            ":generation": generation,
            ":lease": lease_id,
        },
        ReturnValues="ALL_NEW",
    )
    account_deletion_repo.require_active_account_fence(owner, generation, table=target)
    attributes = response.get("Attributes") if isinstance(response, Mapping) else None
    return dict(attributes) if isinstance(attributes, Mapping) else {**intent, "state": "claimed"}


def classify_report_delivery_outcome(
    *, response: Mapping[str, object] | None, error: Exception | None
) -> str:
    if error is not None:
        return "provider_acceptance_unknown"
    if not isinstance(response, Mapping):
        raise account_deletion_repo.AccountDeletionConflict("malformed provider acceptance")
    message_id = response.get("MessageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise account_deletion_repo.AccountDeletionConflict("malformed provider acceptance")
    return "accepted"


def scan_report_private_rows(
    owner_id: str,
    *,
    table: object | None = None,
    cursor: Mapping[str, object] | None = None,
    maximum_pages: int = 20,
    page_limit: int = 100,
) -> ReportPrivatePage:
    """Strong base-table scan for report and denormalized support copies."""
    if maximum_pages <= 0 or page_limit <= 0:
        raise account_deletion_repo.AccountDeletionConflict("invalid report scan bound")
    target = table or get_table()
    current = _validated_report_cursor(cursor) if cursor is not None else None
    seen = {(current["PK"], current["SK"])} if current else set()
    rows: list[ReportItem] = []
    unresolved = 0
    for _ in range(maximum_pages):
        request: dict[str, object] = {"ConsistentRead": True, "Limit": page_limit}
        if current:
            request["ExclusiveStartKey"] = current
        page = _scan(target, **request)
        for item in _response_items(page):
            pk = str(item.get("PK") or "")
            sk = str(item.get("SK") or "")
            registered = any(
                (pk == prefix or pk.startswith(prefix)) and sk.startswith(sk_prefix)
                for prefix, sk_prefix in REPORT_PRIVATE_ROW_REGISTRY.values()
            )
            if not registered or item.get("privacy_deleted") is True:
                continue
            if item.get("student_id") == owner_id or item.get("owner_id") == owner_id:
                rows.append(item)
            elif pk.startswith(("SUPPORT_", "AUDIT_RETENTION#", "REPORT_RECOVERY_JOB#")):
                unresolved += 1
        raw_cursor = page.get("LastEvaluatedKey")
        if raw_cursor is None:
            return ReportPrivatePage(tuple(rows), None, unresolved)
        if not isinstance(raw_cursor, Mapping):
            raise account_deletion_repo.AccountDeletionConflict("invalid report cursor")
        next_cursor = _validated_report_cursor(raw_cursor)
        marker = (next_cursor["PK"], next_cursor["SK"])
        if marker in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeating report cursor")
        seen.add(marker)
        current = next_cursor
    return ReportPrivatePage(tuple(rows), current, unresolved)


def scrub_report_private_row(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> ReportItem:
    if item.get("student_id") not in {None, owner_id} and item.get("owner_id") != owner_id:
        raise account_deletion_repo.AccountDeletionConflict("report owner mismatch")
    tombstone = {
        key: value
        for key, value in item.items()
        if key in REPORT_TOMBSTONE_ALLOWLIST and key not in REPORT_PRIVATE_FIELDS
    }
    tombstone.update(
        {
            "PK": _required_private_string(item.get("PK"), "PK"),
            "SK": _required_private_string(item.get("SK"), "SK"),
            "privacy_deleted": True,
            "owner_deletion_generation": generation,
            "deleted_at": now_iso,
            "updated_at": now_iso,
        }
    )
    if not set(tombstone) <= REPORT_TOMBSTONE_ALLOWLIST:
        raise account_deletion_repo.AccountDeletionConflict("report tombstone allowlist violation")
    target = table or get_table()
    if isinstance(target, _ScrubPrivateRowHook):
        target.scrub_report_private_row(dict(item), tombstone, owner_id, generation)
        return tombstone
    account_deletion_repo.transact(
        [
            account_deletion_repo.deletion_fence_condition(owner_id, generation),
            {
                "Put": {
                    "Item": tombstone,
                    "ConditionExpression": "attribute_exists(PK) AND attribute_exists(SK)",
                }
            },
        ],
        table=target,
    )
    return tombstone


def prove_report_object_version_absent(
    *,
    s3_client: object,
    bucket: str,
    object_key: str,
    version_id: str,
    maximum_pages: int = 100,
) -> bool:
    if not isinstance(s3_client, _ReportObjectVersionLister):
        raise account_deletion_repo.AccountDeletionConflict(
            "report object dependency unavailable"
        )
    request: dict[str, object] = {"Bucket": bucket, "Prefix": object_key}
    seen: set[tuple[str, str]] = set()
    for _ in range(maximum_pages):
        page = _dependency_mapping(s3_client.list_object_versions(**request))
        candidates = [
            *_provider_rows(page.get("Versions", []), "malformed absence page"),
            *_provider_rows(page.get("DeleteMarkers", []), "malformed absence page"),
        ]
        for raw in candidates:
            if (
                isinstance(raw, Mapping)
                and raw.get("Key") == object_key
                and raw.get("VersionId") == version_id
            ):
                return False
        if page.get("IsTruncated") is not True:
            return True
        marker = (
            _required_private_string(page.get("NextKeyMarker"), "NextKeyMarker"),
            _required_private_string(page.get("NextVersionIdMarker"), "NextVersionIdMarker"),
        )
        if marker in seen:
            raise account_deletion_repo.AccountDeletionConflict("repeating absence marker")
        seen.add(marker)
        request["KeyMarker"], request["VersionIdMarker"] = marker
    raise account_deletion_repo.AccountDeletionConflict("absence scan bound exceeded")


def classify_report_retention(manifest: Mapping[str, object]) -> ReportItem:
    if manifest.get("legal_hold_active") is True:
        return {
            "status": "legal_retention_blocked",
            "quiescent": False,
            "purged_count": 0,
            "policy_authority": manifest.get("policy_authority"),
            "policy_scope": manifest.get("policy_scope"),
            "hold_expires_at": manifest.get("hold_expires_at"),
        }
    return {"status": "purgeable", "quiescent": False, "purged_count": 0}


def purge_report_object_intent(
    intent: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    bucket: str,
    s3_client: object,
    now_iso: str,
    table: object | None = None,
) -> ReportItem:
    """Delete one exact purgeable version and retain coordinates until absence."""
    if not isinstance(s3_client, _ReportObjectDeletionClient):
        raise account_deletion_repo.AccountDeletionConflict(
            "report object dependency unavailable"
        )
    if intent.get("owner_id") != owner_id:
        raise account_deletion_repo.AccountDeletionConflict("report object owner mismatch")
    if intent.get("account_fence_generation") != generation:
        raise account_deletion_repo.AccountDeletionConflict("report object generation mismatch")
    retention = classify_report_retention(intent)
    if retention["status"] == "legal_retention_blocked":
        # The access fence remains permanent. Exact provider coordinates stay as
        # policy debt and never enter an absence or purge count.
        return retention
    account_deletion_repo.require_deletion_account_fence(
        owner_id, generation, table=table
    )
    key = _required_private_string(intent.get("object_key"), "object_key")
    version_id = _required_private_string(intent.get("version_id"), "version_id")
    s3_client.delete_object(Bucket=bucket, Key=key, VersionId=version_id)
    if not prove_report_object_version_absent(
        s3_client=s3_client,
        bucket=bucket,
        object_key=key,
        version_id=version_id,
    ):
        return {"status": "retryable", "quiescent": False, "purged_count": 0}
    scrub_report_private_row(
        intent,
        owner_id=owner_id,
        generation=generation,
        now_iso=now_iso,
        table=table,
    )
    return {"status": "purged", "quiescent": True, "purged_count": 1}
