from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from stoa.config import Settings
from stoa.db.repositories import attachment_repo
from stoa.services import attachment_service


OWNER = "student-retention"
RESOURCE = "conversation-retention"


def _attachment(
    attachment_id: str = "attachment-retention",
    *,
    ref_count: int = 1,
    status: str = "active",
) -> dict[str, Any]:
    return {
        **attachment_repo.attachment_key(attachment_id),
        "attachment_id": attachment_id,
        "owner_id": OWNER,
        "student_id": OWNER,
        "entity_type": "attachment",
        "schema_version": "attachment.v1",
        "status": status,
        "ref_count": ref_count,
        "immutable_object_key": "objects/private/retention.bin",
        "immutable_version_id": "version-retention",
        "immutable_etag": "etag-retention",
        "content_sha256": "a" * 64,
        "content_length": 9,
        "detected_type": "application/pdf",
        "original_filename": "retention.pdf",
        "created_at": "2026-07-17T00:00:00+00:00",
    }


def _association(
    attachment_id: str = "attachment-retention",
    *,
    resource_id: str = RESOURCE,
) -> dict[str, Any]:
    return {
        **attachment_repo.association_key(
            attachment_id,
            "conversation",
            resource_id,
            f"message-{attachment_id}",
        ),
        "attachment_id": attachment_id,
        "owner_id": OWNER,
        "student_id": OWNER,
        "entity_type": "attachment_association",
        "resource_type": "conversation",
        "resource_id": resource_id,
        "message_id": f"message-{attachment_id}",
        "created_at": "2026-07-17T00:00:00+00:00",
    }


class _StrongPagedTable:
    name = "stoa-test"

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def query(self, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("eventually consistent owner GSI must not authorize absence")

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        return self.pages[index]


def test_strong_owner_enumeration_joins_metadata_and_associations_across_pages() -> None:
    attachment = _attachment()
    association = _association()
    table = _StrongPagedTable(
        [
            {"Items": [association], "LastEvaluatedKey": {"PK": "cursor", "SK": "1"}},
            {"Items": [attachment]},
        ]
    )

    items = attachment_repo.list_owner_attachment_items(OWNER, table=table)

    assert {item["entity_type"] for item in items} == {
        "attachment",
        "attachment_association",
    }
    assert len(table.calls) == 2
    assert all(call["ConsistentRead"] is True for call in table.calls)
    assert table.calls[1]["ExclusiveStartKey"] == {"PK": "cursor", "SK": "1"}


@pytest.mark.parametrize(
    "second_cursor",
    [
        {"PK": "cursor", "SK": "1"},
        {"PK": "cursor"},
        "not-a-key",
    ],
)
def test_strong_owner_enumeration_rejects_repeating_or_malformed_cursors(
    second_cursor: Any,
) -> None:
    table = _StrongPagedTable(
        [
            {"Items": [], "LastEvaluatedKey": {"PK": "cursor", "SK": "1"}},
            {"Items": [], "LastEvaluatedKey": second_cursor},
        ]
    )

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
        attachment_repo.list_owner_attachment_items(OWNER, table=table)


def _condition_checks(operations: list[Any]) -> list[dict[str, Any]]:
    return [
        operation.item["ConditionCheck"]
        for operation in operations
        if "ConditionCheck" in operation.item
    ]


def test_message_association_transaction_checks_resource_and_account_fences() -> None:
    operations = attachment_repo.build_message_attachment_transaction(
        message={"PK": "CONV#1", "SK": "MSG#1", "message_id": "message-1"},
        fresh=[],
        reused=[_attachment()],
        associations=[_association()],
        owner_id=OWNER,
        limit_bytes=100,
        now_iso="2026-07-17T00:00:00+00:00",
    )

    checks = _condition_checks(operations)
    assert len(checks) == 2
    assert {check["Key"]["SK"] for check in checks} == {
        "RETENTION#ACCOUNT",
        f"RETENTION#RESOURCE#conversation#{RESOURCE}",
    }
    assert all("attribute_not_exists" in check["ConditionExpression"] for check in checks)


def test_question_association_transaction_checks_resource_and_account_fences() -> None:
    prepared = {"kind": "attachment", "record": _attachment()}
    operations = attachment_repo.build_question_attachment_transaction(
        question={"PK": "STUDENT#1", "SK": "QUESTION#question-1", "question_id": "question-1"},
        prepared=prepared,
        attachment=_attachment(),
        association={**_association(resource_id="question-1"), "resource_type": "question"},
        owner_id=OWNER,
        limit_bytes=100,
        now_iso="2026-07-17T00:00:00+00:00",
    )

    checks = _condition_checks(operations)
    assert {check["Key"]["SK"] for check in checks} == {
        "RETENTION#ACCOUNT",
        "RETENTION#RESOURCE#question#question-1",
    }


class _VersionListingS3:
    def __init__(self, *, retained: bool, raise_after_delete: bool = False) -> None:
        self.retained = retained
        self.raise_after_delete = raise_after_delete
        self.delete_calls = 0

    def delete_object(self, **_kwargs: Any) -> dict[str, Any]:
        self.delete_calls += 1
        self.retained = False
        if self.raise_after_delete:
            raise RuntimeError("provider-private-commit-then-raise")
        return {}

    def list_object_versions(self, **_kwargs: Any) -> dict[str, Any]:
        versions = []
        if self.retained:
            versions.append(
                {
                    "Key": "objects/private/retention.bin",
                    "VersionId": "version-retention",
                }
            )
        return {"Versions": versions, "DeleteMarkers": [], "IsTruncated": False}


class _FinalizeRepository:
    build_finalize_deletion_transaction = staticmethod(
        attachment_repo.build_finalize_deletion_transaction
    )

    def __init__(self, *, commit_then_raise: bool = False, fail: bool = False) -> None:
        self.row: dict[str, Any] | None = _attachment(status="deletion_pending")
        self.commit_then_raise = commit_then_raise
        self.fail = fail
        self.finalize_calls = 0

    def mark_deletion_absence_proven(self, *_args: Any, **_kwargs: Any) -> bool:
        assert self.row is not None
        self.row["deletion_stage"] = "object_absence_proven"
        return True

    def transact(self, _operations: list[dict[str, Any]]) -> None:
        self.finalize_calls += 1
        if self.fail:
            raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")
        self.row = None
        if self.commit_then_raise:
            raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")

    def get_attachment(self, _attachment_id: str) -> dict[str, Any] | None:
        return self.row


def test_delete_commit_then_raise_reconciles_exact_absence_and_finalize_once() -> None:
    s3 = _VersionListingS3(retained=True, raise_after_delete=True)
    repository = _FinalizeRepository(commit_then_raise=True)

    assert attachment_service._finish_pending_deletion(
        _attachment(status="deletion_pending"),
        s3=s3,
        settings=Settings(s3_images_bucket="private-bucket"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
        repository=repository,
    )
    assert repository.finalize_calls == 1
    assert s3.delete_calls == 1


def test_quota_finalize_failure_retains_resumable_tombstone() -> None:
    s3 = _VersionListingS3(retained=False)
    repository = _FinalizeRepository(fail=True)

    assert not attachment_service._finish_pending_deletion(
        _attachment(status="deletion_pending"),
        s3=s3,
        settings=Settings(s3_images_bucket="private-bucket"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
        repository=repository,
    )
    assert repository.row is not None
    assert repository.row["status"] == "deletion_pending"
    assert repository.row["deletion_stage"] == "object_absence_proven"


class _CaptureUpdateTable:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {}


def test_promotion_success_persists_cleanup_debt_before_staging_delete() -> None:
    table = _CaptureUpdateTable()

    assert attachment_repo.record_immutable_version(
        "upload-1",
        OWNER,
        4,
        operation_fence="fence-1",
        immutable_version_id="immutable-version",
        immutable_etag="immutable-etag",
        validated_at="2026-07-17T00:00:00+00:00",
        table=table,
    )
    values = table.calls[0]["ExpressionAttributeValues"]
    assert "staging_cleanup_status" in table.calls[0]["UpdateExpression"]
    assert values[":staging_cleanup_pending"] == "pending"


def test_retention_outcome_contract_is_closed_and_typed() -> None:
    assert {member.value for member in attachment_service.RetentionDisposition} == {
        "complete",
        "incomplete_retryable",
        "conflict",
        "concealed_missing",
    }
    assert {member.value for member in attachment_service.RetentionStage} >= {
        "fenced",
        "references_releasing",
        "object_deletion_pending",
        "object_absence_proven",
        "quota_finalize_pending",
        "complete",
        "retryable",
        "conflict",
    }
