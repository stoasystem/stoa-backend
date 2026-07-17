"""Adversarial provider acknowledgement and recovery state machines for Phase 473."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from typing import Any

import pytest

from stoa.config import DOCUMENT_MAX_BYTES, Settings
from stoa.db.repositories import attachment_repo
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services.attachment_service import (
    _exact_object_versions,
    _matching_exact_version,
    _reconcile_provider_part,
    _terminal_abort,
    _validate_and_promote_completed,
    put_upload_chunk,
)


PRIVATE_CANARIES = (
    "private-bucket-canary",
    "staging/private-coordinate-canary.txt",
    "provider-upload-id-canary",
    "provider-diagnostic-canary",
)


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
        "expires_at": 2_000_000_000,
    }


async def _chunks(value: bytes):
    yield value


def _provider_checksum(value: bytes) -> str:
    return base64.b64encode(hashlib.sha256(value).digest()).decode("ascii")


class _PartRepository:
    def __init__(self, *, attempt: int = 1) -> None:
        self.item = _pending_upload()
        self.part: dict[str, Any] | None = None
        self.attempt = attempt
        self.completions: list[dict[str, Any]] = []

    def get_upload_intent(self, upload_id: str) -> dict[str, Any]:
        return dict(self.item)

    def claim_upload_part(
        self,
        upload_id: str,
        part_number: int,
        checksum: str,
        length: int,
        lease_owner: str,
        now_epoch: int,
    ) -> dict[str, Any]:
        self.part = {
            "status": "uploading",
            "part_number": part_number,
            "checksum_sha256": checksum,
            "content_length": length,
            "lease_owner": lease_owner,
            "lease_expires_at": now_epoch + 120,
            "attempt": self.attempt,
        }
        return dict(self.part)

    def get_upload_part(self, upload_id: str, part_number: int) -> dict[str, Any] | None:
        return dict(self.part) if self.part else None

    def complete_upload_part(
        self, upload_id: str, part_number: int, lease_owner: str, **ack: Any
    ) -> bool:
        self.completions.append(dict(ack))
        assert self.part is not None
        self.part.update(ack, status="completed")
        return True


class _UploadPartProvider:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def upload_part(self, **kwargs: Any) -> dict[str, Any]:
        return dict(self.response)


def test_part_acknowledgement_commit_then_raise_reconciles_without_second_write() -> None:
    data = b"abc"

    class Repository(_PartRepository):
        def __init__(self) -> None:
            super().__init__()
            self.claims = 0

        def claim_upload_part(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            result = super().claim_upload_part(*args, **kwargs)
            self.claims += 1
            result["attempt"] = self.claims
            assert self.part is not None
            self.part["attempt"] = self.claims
            return result

    class Provider:
        def __init__(self) -> None:
            self.uploads = 0
            self.part: dict[str, Any] | None = None

        def upload_part(self, **kwargs: Any) -> dict[str, Any]:
            self.uploads += 1
            self.part = {
                "PartNumber": kwargs["PartNumber"],
                "Size": kwargs["ContentLength"],
                "ETag": '"provider-etag"',
                "ChecksumSHA256": kwargs["ChecksumSHA256"],
            }
            raise RuntimeError("provider-diagnostic-canary")

        def list_parts(self, **kwargs: Any) -> dict[str, Any]:
            return {"Parts": [dict(self.part)], "IsTruncated": False}

    repository, provider = Repository(), Provider()
    with pytest.raises(AttachmentDecisionError) as first:
        asyncio.run(
            put_upload_chunk(
                "upload-1", 1, _chunks(data), _actor(), s3=provider,
                settings=Settings(s3_images_bucket="private-bucket-canary"),
                repository=repository,
            )
        )
    assert first.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert "provider-diagnostic-canary" not in str(first.value)

    replay = asyncio.run(
        put_upload_chunk(
            "upload-1", 1, _chunks(data), _actor(), s3=provider,
            settings=Settings(s3_images_bucket="private-bucket-canary"),
            repository=repository,
        )
    )
    assert replay["status"] == "accepted"
    assert provider.uploads == 1


@pytest.mark.parametrize("etag", [None, "", " \t", False, True, 0, 1, [], {}])
def test_part_acknowledgement_rejects_nonblank_nonstring_etag(etag: Any) -> None:
    data = b"abc"
    repository = _PartRepository()
    response = {"ChecksumSHA256": _provider_checksum(data)}
    if etag is not None:
        response["ETag"] = etag

    with pytest.raises(AttachmentDecisionError) as captured:
        asyncio.run(
            put_upload_chunk(
                "upload-1",
                1,
                _chunks(data),
                _actor(),
                s3=_UploadPartProvider(response),
                settings=Settings(s3_images_bucket="private-bucket-canary"),
                repository=repository,
            )
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert repository.completions == []
    assert all(value not in str(captured.value) for value in PRIVATE_CANARIES)


@pytest.mark.parametrize(
    "checksum",
    [
        None,
        "",
        "not-base64",
        base64.b64encode(b"short").decode("ascii"),
        _provider_checksum(b"different"),
        False,
        1,
        [],
        {},
    ],
)
def test_part_acknowledgement_rejects_missing_malformed_or_unequal_checksum(
    checksum: Any,
) -> None:
    repository = _PartRepository()
    response: dict[str, Any] = {"ETag": '"provider-etag"'}
    if checksum is not None:
        response["ChecksumSHA256"] = checksum

    with pytest.raises(AttachmentDecisionError) as captured:
        asyncio.run(
            put_upload_chunk(
                "upload-1",
                1,
                _chunks(b"abc"),
                _actor(),
                s3=_UploadPartProvider(response),
                settings=Settings(s3_images_bucket="private-bucket-canary"),
                repository=repository,
            )
        )

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert repository.completions == []


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
def test_part_acknowledgement_repository_rejects_invalid_invariants_before_write(
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


def _reconcile(
    provider: _ListPartsProvider,
    *, repository: _PartRepository | None = None,
) -> tuple[bool, _PartRepository]:
    repository = repository or _PartRepository(attempt=2)
    repository.part = {
        "status": "uploading",
        "part_number": 1,
        "checksum_sha256": hashlib.sha256(b"abc").hexdigest(),
        "content_length": 3,
        "lease_owner": "lease-owner",
        "attempt": 2,
    }
    adopted = _reconcile_provider_part(
        repository.item,
        1,
        3,
        hashlib.sha256(b"abc").hexdigest(),
        "lease-owner",
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        repository=repository,
    )
    return adopted, repository


def test_list_parts_paginates_with_strict_progressing_marker() -> None:
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

    adopted, repository = _reconcile(provider)

    assert adopted is True
    assert provider.requests[1]["PartNumberMarker"] == 1
    assert repository.completions


@pytest.mark.parametrize("marker", [None, 0, -1, True, "1", "", [], {}])
def test_list_parts_rejects_invalid_continuation_marker(marker: Any) -> None:
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
def test_list_parts_rejects_malformed_success_scalars(field: str, value: Any) -> None:
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


def test_list_parts_rejects_duplicate_conflicting_part() -> None:
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


def test_terminal_abort_stale_cas_performs_no_provider_mutation() -> None:
    class Repository:
        def mark_upload_terminal(self, *args: Any, **kwargs: Any) -> bool:
            return False

    class Provider:
        aborts = 0

        def abort_multipart_upload(self, **kwargs: Any) -> None:
            self.aborts += 1

    provider = Provider()
    _terminal_abort(
        _pending_upload(),
        _actor(),
        s3=provider,
        settings=Settings(s3_images_bucket="private-bucket-canary"),
        repository=Repository(),
    )
    assert provider.aborts == 0


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
            return {
                "VersionId": "immutable-version-1",
                "ETag": '"immutable-etag"',
                "ContentLength": len(self.data),
                "ChecksumSHA256": _provider_checksum(self.data),
                "Metadata": {
                    "content-sha256": hashlib.sha256(self.data).hexdigest(),
                    "upload-id": "upload-1",
                    "purpose": "conversation_attachment",
                },
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
