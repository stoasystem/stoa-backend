"""Adversarial provider acknowledgement and recovery state machines for Phase 473."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from stoa.config import DOCUMENT_MAX_BYTES, Settings
from stoa.db.repositories import attachment_repo
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services.attachment_service import (
    _exact_object_versions,
    _matching_exact_version,
    _provider_parts,
    _validate_and_promote_completed,
)


PRIVATE_CANARIES = (
    "private-bucket-canary",
    "staging/private-coordinate-canary.txt",
    "provider-upload-id-canary",
    "provider-diagnostic-canary",
)
_UPLOAD_NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _actor() -> Actor:
    return Actor(
        user_id="student-1",
        issuer="https://issuer.example",
        subject="subject-1",
        role=CanonicalRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        cognito_group="student",
    )


def _pending_upload(*, expected_size: int = 3) -> dict[str, Any]:
    return {
        "upload_id": "upload-1",
        "owner_id": "student-1",
        "staging_object_key": "staging/private-coordinate-canary.txt",
        "multipart_upload_id": "provider-upload-id-canary",
        "original_filename": "notes.txt",
        "declared_type": "text/plain",
        "expected_kind": "conversation_attachment",
        "max_bytes": DOCUMENT_MAX_BYTES,
        "expected_size": expected_size,
        "part_count": 1,
        "status": "pending_upload",
        "version": 2,
        "expires_at": int(_UPLOAD_NOW.timestamp()) + 1800,
    }


def _provider_checksum(value: bytes) -> str:
    return base64.b64encode(hashlib.sha256(value).digest()).decode("ascii")


class _ForbiddenTable:
    def update_item(self, **kwargs: Any) -> Any:
        raise AssertionError("repository mutation must not run for an invalid acknowledgement")


@pytest.mark.parametrize(
    ("part_number", "etag", "checksum"),
    [
        (0, '"etag"', _provider_checksum(b"abc")),
        (-1, '"etag"', _provider_checksum(b"abc")),
        (True, '"etag"', _provider_checksum(b"abc")),
        ("1", '"etag"', _provider_checksum(b"abc")),
        (1, " ", _provider_checksum(b"abc")),
        (1, '"etag"', "not-base64"),
    ],
)
def test_complete_upload_part_acknowledgement_repository_rejects_invalid_invariants_before_write(
    part_number: Any, etag: Any, checksum: Any
) -> None:
    with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
        attachment_repo.complete_upload_part(
            "upload-1",
            part_number,
            "lease-owner",
            provider_etag=etag,
            provider_checksum=checksum,
            expected_checksum_sha256=hashlib.sha256(b"abc").hexdigest(),
            content_length=3,
            table=_ForbiddenTable(),
        )


class _ListPartsProvider:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.requests: list[dict[str, Any]] = []

    def list_parts(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(dict(kwargs))
        return dict(self.pages[len(self.requests) - 1])


# The tests below keep their `reconcile_provider_part` names: the phase-473
# boundary inventory names them as selectors. The listing they exercise is
# `_provider_parts`, which completion uses to adopt the parts S3 holds.
def _reconcile(provider: _ListPartsProvider) -> dict[int, tuple[int, str, str]]:
    return _provider_parts(
        _pending_upload(),
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
    )


def test_reconcile_provider_part_list_parts_paginates_with_strict_progressing_marker() -> None:
    provider = _ListPartsProvider(
        [
            {"Parts": [], "IsTruncated": True, "NextPartNumberMarker": 1},
            {
                "Parts": [
                    {
                        "PartNumber": 1,
                        "Size": 3,
                        "ETag": '"etag"',
                        "ChecksumSHA256": _provider_checksum(b"abc"),
                    }
                ],
                "IsTruncated": False,
            },
        ]
    )

    parts = _reconcile(provider)

    assert parts == {1: (3, '"etag"', _provider_checksum(b"abc"))}
    assert provider.requests[1]["PartNumberMarker"] == 1


@pytest.mark.parametrize("marker", [None, 0, -1, True, "1", "", [], {}])
def test_reconcile_provider_part_list_parts_rejects_invalid_continuation_marker(marker: Any) -> None:
    provider = _ListPartsProvider(
        [{"Parts": [], "IsTruncated": True, "NextPartNumberMarker": marker}]
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        _reconcile(provider)

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    "field,value",
    [
        ("PartNumber", 0),
        ("PartNumber", -1),
        ("PartNumber", True),
        ("PartNumber", "1"),
        ("Size", 0),
        ("Size", -1),
        ("Size", True),
        ("Size", "3"),
        ("ETag", " "),
        ("ChecksumSHA256", "not-base64"),
    ],
)
def test_reconcile_provider_part_list_parts_rejects_malformed_success_scalars(
    field: str, value: Any
) -> None:
    part = {
        "PartNumber": 1,
        "Size": 3,
        "ETag": '"etag"',
        "ChecksumSHA256": _provider_checksum(b"abc"),
    }
    part[field] = value
    provider = _ListPartsProvider([{"Parts": [part], "IsTruncated": False}])

    with pytest.raises(AttachmentDecisionError) as captured:
        _reconcile(provider)

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


def test_reconcile_provider_part_list_parts_rejects_duplicate_conflicting_part() -> None:
    valid = {
        "PartNumber": 1,
        "Size": 3,
        "ETag": '"etag-a"',
        "ChecksumSHA256": _provider_checksum(b"abc"),
    }
    conflicting = {**valid, "ETag": '"etag-b"'}
    provider = _ListPartsProvider(
        [{"Parts": [valid, conflicting], "IsTruncated": False}]
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        _reconcile(provider)

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


class _VersionProvider:
    def __init__(self, pages: list[dict[str, Any]], heads: dict[str, dict[str, Any]] | None = None):
        self.pages = pages
        self.heads = heads or {}
        self.requests: list[dict[str, Any]] = []

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(dict(kwargs))
        return dict(self.pages[len(self.requests) - 1])

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        return dict(self.heads[kwargs["VersionId"]])


def test_object_versions_paginates_validated_marker_pair() -> None:
    provider = _VersionProvider(
        [
            {
                "Versions": [{"Key": "key", "VersionId": "version-1", "ETag": '"e1"'}],
                "DeleteMarkers": [],
                "IsTruncated": True,
                "NextKeyMarker": "key",
                "NextVersionIdMarker": "version-1",
            },
            {
                "Versions": [{"Key": "key", "VersionId": "version-2", "ETag": '"e2"'}],
                "DeleteMarkers": [],
                "IsTruncated": False,
            },
        ]
    )

    versions = _exact_object_versions(
        provider, Settings(s3_images_bucket="private-bucket-canary"), "key"
    )

    assert [value["VersionId"] for value in versions] == ["version-1", "version-2"]
    assert provider.requests[1]["KeyMarker"] == "key"
    assert provider.requests[1]["VersionIdMarker"] == "version-1"


@pytest.mark.parametrize(
    ("key_marker", "version_marker"),
    [(None, "version-1"), ("key", None), ("", "version-1"), ("key", True)],
)
def test_object_versions_rejects_malformed_marker_pair(
    key_marker: Any, version_marker: Any
) -> None:
    provider = _VersionProvider(
        [
            {
                "Versions": [],
                "DeleteMarkers": [],
                "IsTruncated": True,
                "NextKeyMarker": key_marker,
                "NextVersionIdMarker": version_marker,
            }
        ]
    )
    with pytest.raises(AttachmentDecisionError) as captured:
        _exact_object_versions(
            provider, Settings(s3_images_bucket="private-bucket-canary"), "key"
        )
    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


def test_recovery_match_refuses_multiple_exact_provider_versions() -> None:
    versions = [
        {"Key": "key", "VersionId": "version-1", "ETag": '"e1"'},
        {"Key": "key", "VersionId": "version-2", "ETag": '"e2"'},
    ]
    heads = {
        version["VersionId"]: {
            "ContentLength": 3,
            "ETag": version["ETag"],
            "ChecksumSHA256": _provider_checksum(b"abc"),
            "Metadata": {"upload-id": "upload-1"},
        }
        for version in versions
    }
    provider = _VersionProvider(
        [{"Versions": versions, "DeleteMarkers": [], "IsTruncated": False}], heads
    )

    with pytest.raises(AttachmentDecisionError) as captured:
        _matching_exact_version(
            provider,
            Settings(s3_images_bucket="private-bucket-canary"),
            "key",
            expected_length=3,
            metadata_name="upload-id",
            metadata_value="upload-1",
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


class _PromotionRepository:
    def __init__(self) -> None:
        self.item = {
            **_pending_upload(),
            "status": "validating",
            "version": 4,
            "staging_version_id": "staging-version-1",
            "staging_etag": '"staging-etag"',
        }
        self.recorded: dict[str, Any] | None = None
        self.cleared = False

    def begin_immutable_promotion(
        self, upload_id: str, owner_id: str, version: int, now_epoch: int, **values: Any
    ) -> bool:
        self.item.update(values, status="promoting", version=version + 1)
        return True

    def record_immutable_version(
        self, upload_id: str, owner_id: str, version: int, **values: Any
    ) -> bool:
        self.recorded = dict(values)
        self.item.update(values, status="validated", version=version + 1)
        return True

    def clear_staging_coordinates(self, *args: Any) -> bool:
        self.cleared = True
        return True

    def mark_invalid(self, *args: Any) -> bool:
        return True


class _PromotionProvider:
    def __init__(self, data: bytes, *, returned_checksum: str | None = None) -> None:
        self.data = data
        self.returned_checksum = returned_checksum or _provider_checksum(data)
        self.put_request: dict[str, Any] | None = None
        self.head_requests: list[dict[str, Any]] = []
        self.delete_requests: list[dict[str, Any]] = []

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"Body": BytesIO(self.data)}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_request = dict(kwargs)
        return {
            "VersionId": "immutable-version-1",
            "ETag": '"immutable-etag"',
            "ChecksumSHA256": self.returned_checksum,
        }

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.head_requests.append(dict(kwargs))
        if kwargs["Key"].startswith("objects/"):
            assert self.put_request is not None
            return {
                "VersionId": "immutable-version-1",
                "ETag": '"immutable-etag"',
                "ContentLength": len(self.data),
                "ChecksumSHA256": _provider_checksum(self.data),
                "Metadata": dict(self.put_request["Metadata"]),
            }
        raise AssertionError("staging absence must be represented explicitly")

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.delete_requests.append(dict(kwargs))
        return {}


def test_immutable_promotion_is_create_only_and_verifies_returned_and_readback_checksum() -> None:
    repository = _PromotionRepository()
    provider = _PromotionProvider(b"abc")

    result = _validate_and_promote_completed(
        repository.item,
        _actor(),
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        now=datetime(2026, 7, 17, tzinfo=timezone.utc),
        repository=repository,
    )

    assert result["status"] == "validated"
    assert provider.put_request is not None
    assert provider.put_request["IfNoneMatch"] == "*"
    assert provider.head_requests
    assert repository.recorded is not None


def test_immutable_promotion_wrong_returned_checksum_never_records_success() -> None:
    repository = _PromotionRepository()
    provider = _PromotionProvider(b"abc", returned_checksum=_provider_checksum(b"different"))

    with pytest.raises(AttachmentDecisionError) as captured:
        _validate_and_promote_completed(
            repository.item,
            _actor(),
            s3=provider,
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            now=datetime(2026, 7, 17, tzinfo=timezone.utc),
            repository=repository,
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert repository.recorded is None


def test_immutable_promotion_conditional_conflict_retains_exact_recovery_fence() -> None:
    repository = _PromotionRepository()

    class ConflictProvider(_PromotionProvider):
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["IfNoneMatch"] == "*"
            self.put_request = dict(kwargs)
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "private"}},
                "PutObject",
            )

    with pytest.raises(AttachmentDecisionError) as captured:
        _validate_and_promote_completed(
            repository.item,
            _actor(),
            s3=ConflictProvider(b"abc"),
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            now=datetime(2026, 7, 17, tzinfo=timezone.utc),
            repository=repository,
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert repository.item["status"] == "promoting"
    assert repository.item["operation_fence"]
    assert repository.item["immutable_object_key"]
    assert repository.recorded is None
    assert "private" not in str(captured.value)


def test_immutable_promotion_retains_staging_coordinates_until_exact_absence_is_proved() -> None:
    repository = _PromotionRepository()
    provider = _PromotionProvider(b"abc")

    _validate_and_promote_completed(
        repository.item,
        _actor(),
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        now=datetime(2026, 7, 17, tzinfo=timezone.utc),
        repository=repository,
    )

    assert provider.delete_requests
    assert repository.cleared is False
