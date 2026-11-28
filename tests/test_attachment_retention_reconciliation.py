from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fakes.dynamodb import FakeTable, from_wire
from stoa.config import Settings
from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo
from stoa.services import attachment_service, learning_session
from stoa.services.uploads import _store as upload_store


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


def _condition_checks(operations: list[Any]) -> list[dict[str, Any]]:
    return [
        operation.item["ConditionCheck"]
        for operation in operations
        if "ConditionCheck" in operation.item
    ]


def test_message_association_transaction_checks_the_account_fence_alone() -> None:
    """Binding checks the owner's account fence and no fence of the resource (#636, #655)."""
    operations = attachment_repo.build_message_attachment_transaction(
        message_put=learning_session.append(
            "1",
            role="student",
            message_id="1",
            student_id=OWNER,
            generation=1,
            content="a question",
            created_at="2026-07-17T00:00:00+00:00",
            attachment_ids=[],
        ),
        fresh=[],
        reused=[_attachment()],
        associations=[_association()],
        owner_id=OWNER,
        limit_bytes=100,
        now_iso="2026-07-17T00:00:00+00:00",
    )

    assert _condition_checks(operations) == []

    # The account fence is the table gateway's to add, first, when it is sent.
    sent: list[dict[str, Any]] = []

    class _Capture:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            sent.extend(from_wire(TransactItems))

    attachment_repo.transact(operations, owner=OWNER, generation=1, table=_Capture())
    account = sent[0]["ConditionCheck"]
    assert account["Key"] == {"PK": f"USER#{OWNER}", "SK": "ACCOUNT_FENCE"}
    assert account["ConditionExpression"] == "#status=:active AND generation=:generation"
    assert len([operation for operation in sent if "ConditionCheck" in operation]) == 1


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


class _FinalizeTable(FakeTable):
    """The shared table, whose finalize transaction fails or commits and loses its answer."""

    def __init__(self, *, commit_then_raise: bool = False, fail: bool = False) -> None:
        super().__init__()
        self.commit_then_raise = commit_then_raise
        self.fail = fail
        self.finalize_calls = 0
        self.seed(
            {**_attachment(status="deletion_pending"), "deletion_stage": "object_deletion_pending"},
            {**attachment_repo.storage_key(OWNER), "used_bytes": 9},
        )

    def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
        self.finalize_calls += 1
        if self.fail:
            raise RuntimeError("provider-private-finalize-failure")
        super().transact_write_items(TransactItems=TransactItems)
        if self.commit_then_raise:
            raise RuntimeError("provider-private-commit-then-raise")

    def row(self) -> dict[str, Any] | None:
        return self.rows.get(("ATTACHMENT#attachment-retention", "META"))


def test_delete_commit_then_raise_reconciles_exact_absence_and_finalize_once() -> None:
    s3 = _VersionListingS3(retained=True, raise_after_delete=True)
    table = _FinalizeTable(commit_then_raise=True)
    db_table.install(table)

    assert attachment_service._finish_pending_deletion(
        _attachment(status="deletion_pending"),
        s3=s3,
        settings=Settings(s3_images_bucket="private-bucket"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )
    assert table.finalize_calls == 1
    assert s3.delete_calls == 1
    assert table.row() is None
    assert table.rows[("STORAGE#" + OWNER, "USAGE")]["used_bytes"] == 0


def test_quota_finalize_failure_retains_resumable_tombstone() -> None:
    s3 = _VersionListingS3(retained=False)
    table = _FinalizeTable(fail=True)
    db_table.install(table)

    assert not attachment_service._finish_pending_deletion(
        _attachment(status="deletion_pending"),
        s3=s3,
        settings=Settings(s3_images_bucket="private-bucket"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )
    row = table.row()
    assert row is not None
    assert row["status"] == "deletion_pending"
    assert row["deletion_stage"] == "object_absence_proven"

    # The next run carries on from the recorded proof and finishes.
    table.fail = False
    assert attachment_service._finish_pending_deletion(
        row,
        s3=s3,
        settings=Settings(s3_images_bucket="private-bucket"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )
    assert table.row() is None


class _CaptureUpdateTable:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {}


def test_promotion_success_persists_cleanup_debt_before_staging_delete() -> None:
    table = _CaptureUpdateTable()

    assert upload_store.record_immutable_version(
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
    assert "staging_cleanup_status" in table.calls[0]["ExpressionAttributeNames"].values()
    assert "pending" in values.values()
