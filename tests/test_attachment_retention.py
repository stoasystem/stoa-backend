"""Releasing an attachment's references, and deleting it with the last one.

A conversation released keeps an attachment another conversation still holds,
deletes the last holder's exactly once, and a student's purge releases them all
and is safe to repeat. Moved here from `test_attachment_security.py` (#254).
"""

from stoa.config import Settings
from stoa.db.repositories import attachment_repo
from stoa.services.attachment_service import (
    purge_student_attachments,
    release_resource_attachments,
)


def _saved_attachment(owner="student-1") -> dict:
    return {
        "attachment_id": "attachment-saved",
        "owner_id": owner,
        "immutable_object_key": "objects/private/saved-provider-coordinate.pdf",
        "immutable_version_id": "immutable-version-saved",
        "immutable_etag": "immutable-etag-saved",
        "content_sha256": "0" * 64,
        "original_filename": "saved.pdf",
        "detected_type": "application/pdf",
        "content_length": 777,
        "status": "active",
        "created_at": "2026-07-16T00:00:00+00:00",
    }


class _ReadBody:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, limit: int) -> bytes:
        value = self.data[self.offset : self.offset + limit]
        self.offset += len(value)
        return value

    def close(self) -> None:
        return None


class _PrivateS3:
    def __init__(
        self,
        objects: dict[str, bytes | tuple[bytes, str] | tuple[bytes, str, str]] | None = None,
    ) -> None:
        self.objects = objects or {}
        self.deleted: list[tuple[str, str, str]] = []

    def get_object(self, Bucket, Key, VersionId):
        value = self.objects[Key]
        data, etag = value if isinstance(value, tuple) else (value, "immutable-etag")
        return {"Body": _ReadBody(data), "ETag": etag, "ContentLength": len(data)}

    def delete_object(self, Bucket, Key, VersionId):
        self.deleted.append((Bucket, Key, VersionId))

    def list_object_versions(self, Bucket, Prefix, MaxKeys, **_kwargs):
        deleted_versions = {(key, version) for _, key, version in self.deleted}
        versions = []
        for key, value in self.objects.items():
            if key != Prefix:
                continue
            version = value[2] if isinstance(value, tuple) and len(value) > 2 else None
            if version is not None and (key, version) not in deleted_versions:
                versions.append({"Key": key, "VersionId": version, "ETag": "immutable-etag"})
        return {"Versions": versions, "DeleteMarkers": [], "IsTruncated": False}


class _RetentionRepository:
    build_release_reference_transaction = staticmethod(
        attachment_repo.build_release_reference_transaction
    )
    build_finalize_deletion_transaction = staticmethod(
        attachment_repo.build_finalize_deletion_transaction
    )

    def __init__(self) -> None:
        attachment = {
            **attachment_repo.attachment_key("attachment-1"),
            **_saved_attachment(),
            "attachment_id": "attachment-1",
            "student_id": "student-1",
            "entity_type": "attachment",
            "ref_count": 2,
        }
        self.items = {(attachment["PK"], attachment["SK"]): attachment}
        for resource in ("conv-1", "conv-2"):
            association = {
                **attachment_repo.association_key(
                    "attachment-1", "conversation", resource, f"message-{resource}"
                ),
                "attachment_id": "attachment-1",
                "owner_id": "student-1",
                "student_id": "student-1",
                "entity_type": "attachment_association",
                "resource_type": "conversation",
                "resource_id": resource,
                "message_id": f"message-{resource}",
            }
            self.items[(association["PK"], association["SK"])] = association

    def list_owner_attachment_items(self, owner_id):
        return [dict(item) for item in self.items.values() if item.get("student_id") == owner_id]

    def transact(self, operations):
        for operation in operations:
            if "Delete" in operation:
                key = operation["Delete"]["Key"]
                self.items.pop((key["PK"], key["SK"]), None)
            elif "Update" in operation:
                update = operation["Update"]
                key = update["Key"]
                item = self.items.get((key["PK"], key["SK"]))
                if not item or not key["PK"].startswith("ATTACHMENT#"):
                    continue
                expression = update["UpdateExpression"]
                if "ref_count=ref_count-" in expression:
                    item["ref_count"] -= 1
                elif "deletion_resource_type" in expression:
                    values = update["ExpressionAttributeValues"]
                    item["status"] = "deletion_pending"
                    item["deletion_resource_type"] = values[":resource_type"]
                    item["deletion_resource_id"] = values[":resource_id"]


def test_reference_release_preserves_multi_reference_then_deletes_last_once() -> None:
    repository = _RetentionRepository()
    s3 = _PrivateS3()
    settings = Settings(s3_images_bucket="private-bucket")
    first = release_resource_attachments(
        "student-1",
        "conversation",
        "conv-1",
        s3=s3,
        settings=settings,
        repository=repository,
    )
    assert first == {"released": 1, "deleted": 0}
    assert s3.deleted == []
    second = release_resource_attachments(
        "student-1",
        "conversation",
        "conv-2",
        s3=s3,
        settings=settings,
        repository=repository,
    )
    assert second == {"released": 1, "deleted": 1}
    assert len(s3.deleted) == 1
    assert s3.deleted[0][1:] == (
        "objects/private/saved-provider-coordinate.pdf",
        "immutable-version-saved",
    )
    assert repository.list_owner_attachment_items("student-1") == []
    assert purge_student_attachments(
        "student-1", s3=s3, settings=settings, repository=repository
    ) == {"released": 0, "deleted": 0}
    assert len(s3.deleted) == 1


def test_student_purge_releases_all_references_idempotently() -> None:
    repository = _RetentionRepository()
    s3 = _PrivateS3()
    settings = Settings(s3_images_bucket="private-bucket")
    result = purge_student_attachments("student-1", s3=s3, settings=settings, repository=repository)
    assert result == {"released": 2, "deleted": 1}
    assert len(s3.deleted) == 1
    assert purge_student_attachments(
        "student-1", s3=s3, settings=settings, repository=repository
    ) == {"released": 0, "deleted": 0}
