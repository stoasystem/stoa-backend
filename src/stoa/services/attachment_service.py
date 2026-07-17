"""Owner-bound upload lifecycle orchestration."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
from pathlib import PurePath
from tempfile import SpooledTemporaryFile
from typing import Any
from uuid import uuid4

from stoa.config import (
    DOCUMENT_MAX_BYTES,
    FREE_STORAGE_BYTES,
    IMAGE_MAX_BYTES,
    PAID_STORAGE_BYTES,
    UPLOAD_INTENT_TTL_SECONDS,
    Settings,
)
from stoa.db.repositories import attachment_repo
from stoa.models.attachment import (
    AttachmentReference,
    AttachmentStatus,
    AttachmentSummary,
    UploadIntentRequest,
)
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.services.file_validation_service import MIME_BY_EXTENSION
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file
from stoa.services.document_extraction_service import (
    MAX_EXTRACTED_CHARACTERS,
    DocumentExtractionFailure,
)
from stoa.services.document_parser_worker import parse_document_isolated


UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024
UPLOAD_SPOOL_MEMORY_BYTES = 1024 * 1024
UPLOAD_OPERATION_LEASE_SECONDS = 120
PROVIDER_RECONCILIATION_MAX_PAGES = 10
PROVIDER_RECONCILIATION_MAX_ITEMS = 10_000
PROVIDER_VERSION_MAX_PAGES = 10
PROVIDER_VERSION_MAX_ITEMS = 10_000
CLEANUP_RECONCILIATION_MAX_PAGES = 10
CLEANUP_RECONCILIATION_MAX_ITEMS = 10_000


class RetentionDisposition(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE_RETRYABLE = "incomplete_retryable"
    CONFLICT = "conflict"
    CONCEALED_MISSING = "concealed_missing"


class RetentionStage(StrEnum):
    FENCED = "fenced"
    REFERENCES_RELEASING = "references_releasing"
    OBJECT_DELETION_PENDING = "object_deletion_pending"
    OBJECT_ABSENCE_PROVEN = "object_absence_proven"
    QUOTA_FINALIZE_PENDING = "quota_finalize_pending"
    COMPLETE = "complete"
    RETRYABLE = "retryable"
    CONFLICT = "conflict"


class RetentionResult(dict[str, int]):
    """Typed retention outcome with legacy informational count mapping."""

    disposition: RetentionDisposition
    stage: RetentionStage

    def __init__(
        self,
        disposition: RetentionDisposition,
        stage: RetentionStage,
        *,
        released: int = 0,
        deleted: int = 0,
    ) -> None:
        super().__init__(released=released, deleted=deleted)
        self.disposition = disposition
        self.stage = stage


def _list_owner_retention_items(
    repository: Any, owner_id: str, fence: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if fence is None:
        return repository.list_owner_attachment_items(owner_id)
    try:
        return repository.list_owner_attachment_items(owner_id, fence=fence)
    except TypeError:
        # Narrow compatibility for in-memory repositories used by inherited tests.
        return repository.list_owner_attachment_items(owner_id)


def _gateway_call(
    operation, *, conflict_code=AttachmentErrorCode.UPLOAD_NOT_FOUND
):
    """Keep repository/provider diagnostics behind one closed upload boundary."""
    try:
        return operation()
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "dependency_failure":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        if exc.category == "chunk_conflict":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT
            ) from None
        raise AttachmentDecisionError(conflict_code) from None
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None


def _provider_mapping(operation) -> dict[str, Any]:
    response = _gateway_call(operation)
    if not isinstance(response, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return response


def _required_provider_coordinate(response: dict[str, Any], field: str) -> str:
    """Accept only an exact non-blank provider coordinate without coercion."""
    value = response.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _positive_provider_integer(value: Any) -> int:
    """Parse an exact positive integer without accepting bools or string coercion."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _canonical_sha256(value: Any) -> str:
    """Accept only a canonical lowercase SHA-256 hex digest."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _provider_sha256(value: Any, *, expected_hex: str | None = None) -> str:
    """Validate one canonical provider base64 SHA-256 acknowledgement."""
    if not isinstance(value, str) or not value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None
    if len(decoded) != hashlib.sha256().digest_size:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if base64.b64encode(decoded).decode("ascii") != value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if expected_hex is not None and decoded.hex() != _canonical_sha256(expected_hex):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _provider_truncation(value: Any) -> bool:
    if not isinstance(value, bool):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _close_provider_body(body: Any) -> bool:
    """Release one provider response body without replacing the primary outcome."""
    try:
        close = getattr(body, "close", None)
    except Exception:
        return False
    if not callable(close):
        return False
    try:
        close()
    except Exception:
        # Provider cleanup is best-effort and must not replace the stable decision.
        return False
    return True


def storage_limit_for_entitlement(effective_plan: str) -> int:
    return PAID_STORAGE_BYTES if effective_plan in {"standard", "premium"} else FREE_STORAGE_BYTES


def cleanup_upload_intent(
    candidate: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    reference_scan_limit: int,
    repository: Any = attachment_repo,
) -> str:
    """Safely advance one terminal/expired upload toward idempotent deletion."""
    status = str(candidate.get("status") or "")
    now_epoch = int(now.timestamp())
    if status not in {"invalid", "expired", "cleanup_pending"} and int(
        candidate.get("expires_at", 0)
    ) > now_epoch:
        # The short operation lease authorizes takeover/reconciliation only;
        # it never shortens the owner-visible 30-minute intent lifetime.
        return "skipped"
    reason = (
        "invalid"
        if status == "invalid"
        else "expired"
        if status in {"expired", "validated", "validating"}
        else "abandoned"
    )
    try:
        claimed = repository.claim_upload_cleanup(
            str(candidate.get("upload_id") or ""),
            int(candidate.get("version", 0)),
            now_epoch,
            str(candidate.get("cleanup_reason") or reason),
        )
        if not claimed:
            return "skipped"
        current = repository.get_upload_intent(str(claimed["upload_id"]))
        if (
            not current
            or current.get("status") != "cleanup_pending"
            or int(current.get("version", -1)) != int(claimed.get("version", -2))
        ):
            return "skipped"
        version = int(current["version"])
        if current.get("durable_attachment_id"):
            repository.block_upload_cleanup(str(current["upload_id"]), version)
            return "protected"
        immutable_key = str(current.get("immutable_object_key") or "")
        immutable_version = str(current.get("immutable_version_id") or "")
        found, next_cursor = repository.scan_durable_upload_references(
            str(current["upload_id"]),
            immutable_key,
            immutable_version,
            limit=reference_scan_limit,
            exclusive_start_key=current.get("cleanup_reference_cursor"),
        )
        if found:
            repository.block_upload_cleanup(str(current["upload_id"]), version)
            return "protected"
        if next_cursor:
            if repository.advance_upload_cleanup_reference_scan(
                str(current["upload_id"]), version, next_cursor
            ):
                return "deferred"
            return "skipped"
        staging_key = str(current.get("staging_object_key") or "")
        staging_version = str(current.get("staging_version_id") or "")
        multipart_id = str(current.get("multipart_upload_id") or "")
        operation_kind = str(current.get("operation_kind") or "")

        if not current.get("cleanup_multipart_aborted"):
            if multipart_id and staging_key and not staging_version:
                try:
                    _abort_multipart_exact(s3, settings, staging_key, multipart_id)
                except Exception:
                    # Abort may have committed before its response was lost. Only
                    # the following exact listing decides whether progress is safe.
                    pass
                absent, cursor, pages = _exact_multipart_absence(
                    s3,
                    settings,
                    staging_key,
                    multipart_id,
                    cursor=current.get("cleanup_multipart_cursor"),
                )
                if cursor:
                    if not repository.defer_cleanup_reconciliation(
                        str(current["upload_id"]),
                        version,
                        "multipart",
                        cursor,
                        mutation_attempted=True,
                        pages=pages,
                    ):
                        return "retryable"
                    return "deferred"
                if not absent:
                    return "retryable"
            elif staging_key and operation_kind == "staging_issuance":
                if not _abort_all_exact_key_multiparts(s3, settings, staging_key):
                    return "retryable"
            if not repository.mark_cleanup_multipart_aborted(str(current["upload_id"]), version):
                return "retryable"
            version += 1
            current["cleanup_multipart_aborted"] = True

        if not staging_version and staging_key and operation_kind == "staging_assembly":
            recovered = _matching_exact_version(
                s3,
                settings,
                staging_key,
                expected_length=int(current.get("expected_size", -1)),
                metadata_name="upload-id",
                metadata_value=str(current["upload_id"]),
            )
            if recovered:
                staging_version, staging_etag = recovered
                if not repository.record_cleanup_staging_version(
                    str(current["upload_id"]), version, staging_version, staging_etag
                ):
                    return "retryable"
                version += 1
                current["staging_version_id"] = staging_version

        if not current.get("cleanup_staging_deleted"):
            if staging_key and staging_version:
                try:
                    s3.delete_object(
                        Bucket=settings.s3_images_bucket,
                        Key=staging_key,
                        VersionId=staging_version,
                    )
                except Exception:
                    # A lost delete response is reconciled by exact listing.
                    pass
                absent, cursor, pages = _exact_version_absence(
                    s3,
                    settings,
                    staging_key,
                    staging_version,
                    cursor=current.get("cleanup_staging_cursor"),
                )
                if cursor:
                    if not repository.defer_cleanup_reconciliation(
                        str(current["upload_id"]),
                        version,
                        "staging",
                        cursor,
                        mutation_attempted=True,
                        pages=pages,
                    ):
                        return "retryable"
                    return "deferred"
                if not absent:
                    return "retryable"
            if not repository.mark_cleanup_staging_deleted(str(current["upload_id"]), version):
                return "retryable"
            version += 1
            current["cleanup_staging_deleted"] = True

        if not immutable_version and immutable_key and operation_kind == "immutable_promotion":
            recovered = _matching_exact_version(
                s3,
                settings,
                immutable_key,
                expected_length=int(current.get("content_length", -1)),
                metadata_name="content-sha256",
                metadata_value=str(current.get("content_sha256") or ""),
            )
            if recovered:
                immutable_version, immutable_etag = recovered
                if not repository.record_cleanup_immutable_version(
                    str(current["upload_id"]), version, immutable_version, immutable_etag
                ):
                    return "retryable"
                version += 1
                current["immutable_version_id"] = immutable_version

        if not current.get("cleanup_immutable_deleted"):
            if immutable_key and immutable_version:
                try:
                    s3.delete_object(
                        Bucket=settings.s3_images_bucket,
                        Key=immutable_key,
                        VersionId=immutable_version,
                    )
                except Exception:
                    pass
                absent, cursor, pages = _exact_version_absence(
                    s3,
                    settings,
                    immutable_key,
                    immutable_version,
                    cursor=current.get("cleanup_immutable_cursor"),
                )
                if cursor:
                    if not repository.defer_cleanup_reconciliation(
                        str(current["upload_id"]),
                        version,
                        "immutable",
                        cursor,
                        mutation_attempted=True,
                        pages=pages,
                    ):
                        return "retryable"
                    return "deferred"
                if not absent:
                    return "retryable"
            if not repository.mark_cleanup_immutable_deleted(str(current["upload_id"]), version):
                return "retryable"
            version += 1
            current["cleanup_immutable_deleted"] = True

        scrub_parts = getattr(repository, "scrub_upload_parts", None)
        if callable(scrub_parts) and not current.get("cleanup_parts_absent"):
            scrubbed = scrub_parts(
                str(current["upload_id"]),
                version,
                limit=24,
                exclusive_start_key=current.get("cleanup_part_cursor"),
            )
            if not isinstance(scrubbed, tuple) or len(scrubbed) != 2:
                return "retryable"
            removed, part_cursor = scrubbed
            if isinstance(removed, bool) or not isinstance(removed, int) or removed < 0:
                return "retryable"
            if removed:
                if not repository.advance_cleanup_part_scrub(
                    str(current["upload_id"]), version, part_cursor
                ):
                    return "retryable"
                return "deferred"
            if not repository.mark_cleanup_parts_absent(
                str(current["upload_id"]), version
            ):
                return "retryable"
            version += 1
            current["cleanup_parts_absent"] = True

        if not repository.complete_upload_cleanup(
            str(current["upload_id"]), version, now.isoformat()
        ):
            return "retryable"
    except (
        AttachmentDecisionError,
        attachment_repo.AttachmentRepositoryConflict,
    ):
        return "retryable"
    return "deleted"


def _provider_target_absent(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    code = str((response.get("Error") or {}).get("Code") or "")
    return code in {"404", "NoSuchKey", "NoSuchUpload", "NoSuchVersion", "NotFound"}


def _abort_multipart_exact(
    s3: Any, settings: Settings, key: str, multipart_upload_id: str
) -> None:
    s3.abort_multipart_upload(
        Bucket=settings.s3_images_bucket, Key=key, UploadId=multipart_upload_id
    )


def _abort_all_exact_key_multiparts(s3: Any, settings: Settings, key: str) -> bool:
    exact = _exact_key_multipart_ids(s3, settings, key)
    for multipart_upload_id in exact:
        try:
            _abort_multipart_exact(s3, settings, key, multipart_upload_id)
        except Exception:
            pass
    return not _exact_key_multipart_ids(s3, settings, key)


def _cleanup_cursor_pair(
    cursor: Any, first: str, second: str
) -> tuple[str, str] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, dict) or set(cursor) != {first, second}:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return (
        _required_provider_coordinate(cursor, first),
        _required_provider_coordinate(cursor, second),
    )


def _exact_multipart_absence(
    s3: Any,
    settings: Settings,
    key: str,
    multipart_upload_id: str,
    *,
    cursor: Any = None,
) -> tuple[bool, dict[str, str] | None, int]:
    """Return absence only after every validated listing page was visited."""
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Prefix": key,
        "MaxUploads": 1000,
    }
    previous = _cleanup_cursor_pair(cursor, "KeyMarker", "UploadIdMarker")
    if previous:
        request["KeyMarker"], request["UploadIdMarker"] = previous
    item_count = 0
    for page in range(1, CLEANUP_RECONCILIATION_MAX_PAGES + 1):
        response = _provider_mapping(lambda: s3.list_multipart_uploads(**request))
        uploads = response.get("Uploads", [])
        if not isinstance(uploads, list) or any(
            not isinstance(upload, dict) for upload in uploads
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        for upload in uploads:
            item_count += 1
            if item_count > CLEANUP_RECONCILIATION_MAX_ITEMS:
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
            listed_key = _required_provider_coordinate(upload, "Key")
            listed_upload_id = _required_provider_coordinate(upload, "UploadId")
            if listed_key == key and listed_upload_id == multipart_upload_id:
                return False, None, page
        if not _provider_truncation(response.get("IsTruncated", False)):
            return True, None, page
        markers = (
            _required_provider_coordinate(response, "NextKeyMarker"),
            _required_provider_coordinate(response, "NextUploadIdMarker"),
        )
        if markers == previous:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous = markers
        request["KeyMarker"], request["UploadIdMarker"] = markers
    assert previous is not None
    return False, {"KeyMarker": previous[0], "UploadIdMarker": previous[1]}, page


def _exact_key_multipart_ids(s3: Any, settings: Settings, key: str) -> list[str]:
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Prefix": key,
        "MaxUploads": 1000,
    }
    exact: list[str] = []
    previous: tuple[str, str] | None = None
    item_count = 0
    for _ in range(CLEANUP_RECONCILIATION_MAX_PAGES):
        response = _provider_mapping(lambda: s3.list_multipart_uploads(**request))
        uploads = response.get("Uploads", [])
        if not isinstance(uploads, list) or any(
            not isinstance(upload, dict) for upload in uploads
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        for upload in uploads:
            item_count += 1
            if item_count > CLEANUP_RECONCILIATION_MAX_ITEMS:
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
            listed_key = _required_provider_coordinate(upload, "Key")
            listed_upload_id = _required_provider_coordinate(upload, "UploadId")
            if listed_key == key:
                exact.append(listed_upload_id)
        if not _provider_truncation(response.get("IsTruncated", False)):
            return exact
        markers = (
            _required_provider_coordinate(response, "NextKeyMarker"),
            _required_provider_coordinate(response, "NextUploadIdMarker"),
        )
        if markers == previous:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous = markers
        request["KeyMarker"], request["UploadIdMarker"] = markers
    raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)


def _exact_version_absence(
    s3: Any,
    settings: Settings,
    key: str,
    version_id: str,
    *,
    cursor: Any = None,
) -> tuple[bool, dict[str, str] | None, int]:
    """Prove one exact version absent across versions and delete markers."""
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Prefix": key,
        "MaxKeys": 1000,
    }
    previous = _cleanup_cursor_pair(cursor, "KeyMarker", "VersionIdMarker")
    if previous:
        request["KeyMarker"], request["VersionIdMarker"] = previous
    item_count = 0
    for page in range(1, CLEANUP_RECONCILIATION_MAX_PAGES + 1):
        response = _provider_mapping(lambda: s3.list_object_versions(**request))
        versions = response.get("Versions", [])
        delete_markers = response.get("DeleteMarkers", [])
        if (
            not isinstance(versions, list)
            or any(not isinstance(value, dict) for value in versions)
            or not isinstance(delete_markers, list)
            or any(not isinstance(value, dict) for value in delete_markers)
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        for value in [*versions, *delete_markers]:
            item_count += 1
            if item_count > CLEANUP_RECONCILIATION_MAX_ITEMS:
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
            listed_key = _required_provider_coordinate(value, "Key")
            listed_version = _required_provider_coordinate(value, "VersionId")
            if listed_key == key and listed_version == version_id:
                return False, None, page
        for value in versions:
            _required_provider_coordinate(value, "ETag")
        if not _provider_truncation(response.get("IsTruncated", False)):
            return True, None, page
        markers = (
            _required_provider_coordinate(response, "NextKeyMarker"),
            _required_provider_coordinate(response, "NextVersionIdMarker"),
        )
        if markers == previous:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous = markers
        request["KeyMarker"], request["VersionIdMarker"] = markers
    assert previous is not None
    return False, {"KeyMarker": previous[0], "VersionIdMarker": previous[1]}, page


def _matching_exact_version(
    s3: Any,
    settings: Settings,
    key: str,
    *,
    expected_length: int,
    metadata_name: str,
    metadata_value: str,
) -> tuple[str, str] | None:
    versions = _exact_object_versions(s3, settings, key)
    matches: list[tuple[str, str]] = []
    for version in versions:
        version_id = _required_provider_coordinate(version, "VersionId")
        head = _provider_mapping(
            lambda: s3.head_object(
                Bucket=settings.s3_images_bucket, Key=key, VersionId=version_id
            )
        )
        metadata = head.get("Metadata")
        if not isinstance(metadata, dict):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        content_length = head.get("ContentLength")
        if isinstance(content_length, bool) or not isinstance(content_length, int):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        if content_length == expected_length and metadata.get(metadata_name) == metadata_value:
            etag_source = head if head.get("ETag") is not None else version
            matches.append(
                (version_id, _required_provider_coordinate(etag_source, "ETag"))
            )
    if len(matches) == 1:
        return matches[0]
    if versions or len(matches) > 1:
        # A never-reused exact key with an unverified version is not proof of
        # absence, and multiple exact candidates are ambiguous. Retain the
        # recovery fence for a later safe reconciliation.
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return None


def create_upload_intent(
    request: UploadIntentRequest,
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, Any]:
    if actor.role != CanonicalRole.STUDENT:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    extension = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    allowed = MIME_BY_EXTENSION.get(extension)
    if allowed is None:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    if request.content_type not in allowed:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
    if request.purpose.value == "question_image" and extension not in {"jpg", "jpeg", "png"}:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    max_bytes = IMAGE_MAX_BYTES if extension in {"jpg", "jpeg", "png"} else DOCUMENT_MAX_BYTES
    if request.size_bytes > max_bytes:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)
    upload_id = str(uuid4())
    staging_object_key = f"staging/{uuid4().hex}/{upload_id}.{extension}"
    operation_fence = uuid4().hex
    expires_epoch = int(now.timestamp()) + UPLOAD_INTENT_TTL_SECONDS
    part_count = (request.size_bytes + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES
    item = {
        "upload_id": upload_id,
        "owner_id": actor.user_id,
        "student_id": actor.user_id,
        "entity_type": "upload_intent",
        "schema_version": "upload-intent.v1",
        "original_filename": PurePath(request.filename).name,
        "declared_type": request.content_type,
        "expected_kind": request.purpose.value,
        "expected_size": request.size_bytes,
        "max_bytes": max_bytes,
        "part_count": part_count,
        "staging_object_key": staging_object_key,
        "status": "issuing",
        "version": 1,
        "operation_kind": "staging_issuance",
        "operation_fence": operation_fence,
        "operation_lease_expires_at": int(now.timestamp()) + UPLOAD_OPERATION_LEASE_SECONDS,
        "operation_takeover_count": 0,
        "created_at": now.isoformat(),
        "expires_at": expires_epoch,
    }
    multipart_upload_id: str | None = None
    try:
        prepare = getattr(repository, "prepare_staging_issuance", repository.create_upload_intent)
        prepare(item)
        created = _provider_mapping(
            lambda: s3.create_multipart_upload(
                Bucket=settings.s3_images_bucket,
                Key=staging_object_key,
                ContentType=request.content_type,
                ServerSideEncryption="AES256",
                Metadata={"upload-id": upload_id},
                ChecksumAlgorithm="SHA256",
            )
        )
        multipart_upload_id = _required_provider_coordinate(created, "UploadId")
        record = getattr(repository, "record_staging_multipart", None)
        recorded = (
            record(
                upload_id,
                actor.user_id,
                1,
                operation_fence=operation_fence,
                multipart_upload_id=multipart_upload_id,
            )
            if record
            else repository.mark_upload_issued(
                upload_id,
                actor.user_id,
                1,
                staging_object_key=staging_object_key,
                multipart_upload_id=multipart_upload_id,
            )
        )
        if not recorded:
            raise RuntimeError("issuance transition failed")
    except Exception:
        if multipart_upload_id:
            try:
                s3.abort_multipart_upload(
                    Bucket=settings.s3_images_bucket,
                    Key=staging_object_key,
                    UploadId=multipart_upload_id,
                )
            except Exception:
                pass
        try:
            repository.mark_upload_issuance_failed(
                upload_id,
                actor.user_id,
                1,
                cleanup_pending=True,
            )
        except Exception:
            pass
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    return {
        "uploadId": upload_id,
        "expiresAt": datetime.fromtimestamp(expires_epoch, UTC),
        "maxBytes": max_bytes,
        "chunkBytes": UPLOAD_CHUNK_BYTES,
        "acceptedTypes": list(allowed),
        "status": "pending_upload",
    }


async def put_upload_chunk(
    upload_id: str,
    part_number: int,
    chunks: Any,
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, Any]:
    """Buffer one bounded part, claim its digest, then perform the provider mutation."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    item = resolve_owned_upload(upload_id, actor, now=now, repository=repository)
    if item.get("status") != "pending_upload":
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    expected_parts = int(item["part_count"])
    if not 1 <= part_number <= expected_parts:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    expected_length = (
        UPLOAD_CHUNK_BYTES
        if part_number < expected_parts
        else int(item["expected_size"]) - UPLOAD_CHUNK_BYTES * (expected_parts - 1)
    )
    digest = hashlib.sha256()
    length = 0
    with SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b") as spool:
        async for value in chunks:
            if not value:
                continue
            remaining = expected_length + 1 - length
            if remaining <= 0:
                break
            bounded = value[:remaining]
            spool.write(bounded)
            digest.update(bounded)
            length += len(bounded)
            if len(value) > remaining:
                length += 1
                break
        if length > expected_length:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)
        if length != expected_length:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
        checksum = digest.hexdigest()
        lease_owner = uuid4().hex
        try:
            claim = repository.claim_upload_part(
                upload_id,
                part_number,
                checksum,
                length,
                lease_owner,
                int(now.timestamp()),
            )
        except attachment_repo.AttachmentRepositoryConflict as exc:
            if exc.category == "chunk_conflict":
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT) from None
            if exc.category in {"lease_exhausted"}:
                _terminal_abort(item, actor, s3=s3, settings=settings, repository=repository)
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
        except AttachmentDecisionError:
            raise
        except Exception:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
        if not isinstance(claim, dict):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        if claim.get("status") == "completed":
            return _safe_part_receipt(upload_id, part_number, length, checksum)
        if claim.get("lease_owner") != lease_owner:
            for _ in range(20):
                await asyncio.sleep(0.05)
                current = _gateway_call(
                    lambda: repository.get_upload_part(upload_id, part_number)
                )
                if current is not None and not isinstance(current, dict):
                    raise AttachmentDecisionError(
                        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                    )
                if current and current.get("status") == "completed":
                    return _safe_part_receipt(upload_id, part_number, length, checksum)
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

        if int(claim.get("attempt", 1)) > 1:
            adopted = _reconcile_provider_part(
                item,
                part_number,
                length,
                checksum,
                lease_owner,
                s3=s3,
                settings=settings,
                repository=repository,
            )
            if adopted:
                return _safe_part_receipt(upload_id, part_number, length, checksum)
        spool.seek(0)
        provider_checksum = base64.b64encode(bytes.fromhex(checksum)).decode("ascii")
        result = _provider_mapping(
            lambda: s3.upload_part(
                Bucket=settings.s3_images_bucket,
                Key=item["staging_object_key"],
                UploadId=item["multipart_upload_id"],
                PartNumber=part_number,
                Body=spool,
                ContentLength=length,
                ChecksumSHA256=provider_checksum,
            )
        )
        provider_etag = _required_provider_coordinate(result, "ETag")
        acknowledged_checksum = _provider_sha256(
            result.get("ChecksumSHA256"), expected_hex=checksum
        )
        if not _gateway_call(
            lambda: repository.complete_upload_part(
                upload_id,
                part_number,
                lease_owner,
                provider_etag=provider_etag,
                provider_checksum=acknowledged_checksum,
                expected_checksum_sha256=checksum,
                content_length=length,
            )
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return _safe_part_receipt(upload_id, part_number, length, checksum)


def _safe_part_receipt(
    upload_id: str, part_number: int, length: int, checksum: str
) -> dict[str, Any]:
    return {
        "uploadId": upload_id,
        "partNumber": part_number,
        "sizeBytes": length,
        "checksumSha256": checksum,
        "status": "accepted",
    }


def _reconcile_provider_part(
    item: dict[str, Any],
    part_number: int,
    length: int,
    checksum: str,
    lease_owner: str,
    *,
    s3: Any,
    settings: Settings,
    repository: Any,
) -> bool:
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Key": item["staging_object_key"],
        "UploadId": item["multipart_upload_id"],
    }
    seen: dict[int, tuple[int, str, str]] = {}
    item_count = 0
    previous_marker = 0
    for _ in range(PROVIDER_RECONCILIATION_MAX_PAGES):
        response = _provider_mapping(lambda: s3.list_parts(**request))
        provider_parts = response.get("Parts", [])
        if not isinstance(provider_parts, list):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        for provider_part in provider_parts:
            if not isinstance(provider_part, dict):
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            item_count += 1
            if item_count > PROVIDER_RECONCILIATION_MAX_ITEMS:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            provider_number = _positive_provider_integer(
                provider_part.get("PartNumber")
            )
            provider_size = _positive_provider_integer(provider_part.get("Size"))
            provider_etag = _required_provider_coordinate(provider_part, "ETag")
            encoded = _provider_sha256(provider_part.get("ChecksumSHA256"))
            fact = (provider_size, provider_etag, encoded)
            if provider_number in seen:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            seen[provider_number] = fact

        truncated = _provider_truncation(response.get("IsTruncated", False))
        if not truncated:
            break
        marker = _positive_provider_integer(response.get("NextPartNumberMarker"))
        if marker <= previous_marker:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous_marker = marker
        request["PartNumberMarker"] = marker
    else:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    match = seen.get(part_number)
    if match is None:
        return False
    provider_size, provider_etag, encoded = match
    _provider_sha256(encoded, expected_hex=checksum)
    if provider_size != length:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if not _gateway_call(
        lambda: repository.complete_upload_part(
            item["upload_id"],
            part_number,
            lease_owner,
            provider_etag=provider_etag,
            provider_checksum=encoded,
            expected_checksum_sha256=checksum,
            content_length=length,
        )
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return True


def _terminal_abort(
    item: dict[str, Any],
    actor: Actor | None,
    *,
    s3: Any,
    settings: Settings,
    repository: Any,
) -> None:
    try:
        transitioned = repository.mark_upload_terminal(
            item["upload_id"],
            item["owner_id"] if actor is None else actor.user_id,
            int(item["version"]),
            "multipart_reconciliation_failed",
        )
    except Exception:
        return
    if transitioned is not True:
        return
    try:
        s3.abort_multipart_upload(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            UploadId=item["multipart_upload_id"],
        )
    except Exception:
        pass


def complete_upload(
    upload_id: str,
    part_count: int,
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, Any]:
    """Assemble only server-ledger ETags; validation/promotion follows this transition."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    item = resolve_owned_upload(upload_id, actor, now=now, repository=repository)
    if item.get("status") == "validated":
        _reconcile_staging_cleanup_debt(
            item, s3=s3, settings=settings, repository=repository
        )
        return {"uploadId": upload_id, "status": "validated", "attachment": None}
    if item.get("status") == "assembling":
        item = _recover_staging_assembly(
            item, actor, s3=s3, settings=settings, now=now, repository=repository
        )
    if item.get("status") == "promoting":
        return _recover_immutable_promotion(
            item, actor, s3=s3, settings=settings, now=now, repository=repository
        )
    if item.get("status") == "validating":
        return _validate_and_promote_completed(
            item,
            actor,
            s3=s3,
            settings=settings,
            now=now,
            repository=repository,
        )
    if item.get("status") != "pending_upload" or part_count != int(item["part_count"]):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    parts = _gateway_call(lambda: repository.list_upload_parts(upload_id))
    if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if [int(part.get("part_number", 0)) for part in parts] != list(range(1, part_count + 1)):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    if any(part.get("status") != "completed" for part in parts):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    version = int(item["version"])
    operation_fence = uuid4().hex
    ledger_digest = _part_ledger_digest(parts)
    claim = getattr(repository, "claim_staging_assembly", None)
    claimed = _gateway_call(
        lambda: (
            claim(
                upload_id,
                actor.user_id,
                version,
                int(now.timestamp()),
                operation_fence=operation_fence,
                multipart_upload_id=str(item["multipart_upload_id"]),
                ordered_part_count=part_count,
                part_ledger_digest=ledger_digest,
            )
            if claim
            else repository.begin_upload_assembly(
                upload_id, actor.user_id, version, int(now.timestamp())
            )
        )
    )
    if not claimed:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    try:
        result = _provider_mapping(lambda: s3.complete_multipart_upload(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            UploadId=item["multipart_upload_id"],
            MultipartUpload={
                "Parts": [
                    {"PartNumber": int(part["part_number"]), "ETag": part["provider_etag"]}
                    for part in parts
                ]
            },
        ))
        staging_version_id = _required_provider_coordinate(result, "VersionId")
        staging_etag = _required_provider_coordinate(result, "ETag")
        recover = getattr(repository, "recover_staging_completion", None)
        persisted = _gateway_call(lambda: (
            recover(
                upload_id,
                actor.user_id,
                version + 1,
                operation_fence=operation_fence,
                staging_version_id=staging_version_id,
                staging_etag=staging_etag,
            )
            if recover
            else repository.mark_staging_completed(
                upload_id,
                actor.user_id,
                version + 1,
                staging_version_id=staging_version_id,
                staging_etag=staging_etag,
            )
        ))
        if not persisted:
            # Provider completion succeeded, so a false persistence result is an
            # unknown split outcome that callers must retry through recovery.
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    except AttachmentDecisionError:
        raise
    except Exception:
        # The assembling row retains the exact key, multipart ID, fence and lease.
        # A restart reconciles the exact completed version or aborts it during cleanup.
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    completed = {
        **item,
        "status": "validating",
        "version": version + 2,
        "staging_version_id": staging_version_id,
        "staging_etag": staging_etag,
    }
    return _validate_and_promote_completed(
        completed,
        actor,
        s3=s3,
        settings=settings,
        now=now,
        repository=repository,
    )


def _part_ledger_digest(parts: list[dict[str, Any]]) -> str:
    canonical = "\n".join(
        ":".join(
            (
                str(int(part["part_number"])),
                str(part.get("provider_etag") or ""),
                str(part.get("provider_checksum") or ""),
                str(int(part.get("content_length", 0))),
            )
        )
        for part in parts
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exact_object_versions(s3: Any, settings: Settings, key: str) -> list[dict[str, Any]]:
    request: dict[str, Any] = {
        "Bucket": settings.s3_images_bucket,
        "Prefix": key,
        "MaxKeys": 1000,
    }
    exact: list[dict[str, Any]] = []
    item_count = 0
    previous_markers: tuple[str, str] | None = None
    for _ in range(PROVIDER_VERSION_MAX_PAGES):
        response = _provider_mapping(lambda: s3.list_object_versions(**request))
        versions = response.get("Versions", [])
        delete_markers = response.get("DeleteMarkers", [])
        if (
            not isinstance(versions, list)
            or any(not isinstance(value, dict) for value in versions)
            or not isinstance(delete_markers, list)
            or any(not isinstance(value, dict) for value in delete_markers)
        ):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        for value in [*versions, *delete_markers]:
            item_count += 1
            if item_count > PROVIDER_VERSION_MAX_ITEMS:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            _required_provider_coordinate(value, "Key")
            _required_provider_coordinate(value, "VersionId")
        for value in versions:
            _required_provider_coordinate(value, "ETag")
            if value["Key"] == key:
                exact.append(value)
        truncated = _provider_truncation(response.get("IsTruncated", False))
        if not truncated:
            return exact
        markers = (
            _required_provider_coordinate(response, "NextKeyMarker"),
            _required_provider_coordinate(response, "NextVersionIdMarker"),
        )
        if markers == previous_markers:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        previous_markers = markers
        request["KeyMarker"], request["VersionIdMarker"] = markers
    raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)


def _exact_object_digest(
    s3: Any,
    settings: Settings,
    key: str,
    version_id: str,
    *,
    maximum: int,
) -> tuple[int, str]:
    """Read one exact version through a bounded stream and return its byte proof."""
    response = _provider_mapping(
        lambda: s3.get_object(
            Bucket=settings.s3_images_bucket, Key=key, VersionId=version_id
        )
    )
    body = response.get("Body")
    if body is None:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    length = 0
    digest = hashlib.sha256()
    try:
        read = getattr(body, "read", None)
        if not callable(read):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        while True:
            chunk = read(min(UPLOAD_SPOOL_MEMORY_BYTES, maximum + 1 - length))
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            length += len(chunk)
            if length > maximum:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            digest.update(chunk)
    finally:
        _close_provider_body(body)
    return length, digest.hexdigest()


def _exact_version_absent(
    s3: Any, settings: Settings, key: str, version_id: str
) -> bool:
    try:
        s3.head_object(
            Bucket=settings.s3_images_bucket, Key=key, VersionId=version_id
        )
    except Exception as exc:
        return _provider_target_absent(exc)
    return False


def _recover_staging_assembly(
    item: dict[str, Any],
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    repository: Any,
) -> dict[str, Any]:
    if int(item.get("operation_lease_expires_at", 0)) > int(now.timestamp()):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    key = str(item.get("staging_object_key") or "")
    fence = str(item.get("operation_fence") or "")
    if not key or not fence:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    item = _claim_recovery_fence(
        item, actor, now=now, repository=repository, operation_kind="staging_assembly"
    )
    fence = str(item["operation_fence"])
    try:
        matched = _matching_exact_version(
            s3,
            settings,
            key,
            expected_length=_positive_provider_integer(item.get("expected_size")),
            metadata_name="upload-id",
            metadata_value=_required_provider_coordinate(item, "upload_id"),
        )
        if matched is not None:
            version_id, etag = matched
            if _gateway_call(
                lambda: repository.recover_staging_completion(
                    item["upload_id"],
                    actor.user_id,
                    int(item["version"]),
                    operation_fence=fence,
                    staging_version_id=version_id,
                    staging_etag=etag,
                )
            ):
                return {
                    **item,
                    "status": "validating",
                    "version": int(item["version"]) + 1,
                    "staging_version_id": version_id,
                    "staging_etag": etag,
                }
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    except AttachmentDecisionError:
        raise
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)


def _recover_immutable_promotion(
    item: dict[str, Any],
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    repository: Any,
) -> dict[str, Any]:
    if int(item.get("operation_lease_expires_at", 0)) > int(now.timestamp()):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    key = str(item.get("immutable_object_key") or "")
    fence = str(item.get("operation_fence") or "")
    expected_checksum = str(item.get("content_sha256") or "")
    item = _claim_recovery_fence(
        item, actor, now=now, repository=repository, operation_kind="immutable_promotion"
    )
    fence = str(item["operation_fence"])
    try:
        expected_length = _positive_provider_integer(item.get("content_length"))
        expected_checksum = _canonical_sha256(expected_checksum)
        matched = _matching_exact_version(
            s3,
            settings,
            key,
            expected_length=expected_length,
            metadata_name="content-sha256",
            metadata_value=expected_checksum,
        )
        if matched is not None:
            version_id, etag = matched
            actual_length, actual_checksum = _exact_object_digest(
                s3, settings, key, version_id, maximum=expected_length
            )
            if actual_length != expected_length or actual_checksum != expected_checksum:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            if _gateway_call(
                lambda: repository.record_immutable_version(
                    item["upload_id"],
                    actor.user_id,
                    int(item["version"]),
                    operation_fence=fence,
                    immutable_version_id=version_id,
                    immutable_etag=etag,
                    validated_at=now.isoformat(),
                )
            ):
                return {"uploadId": item["upload_id"], "status": "validated", "attachment": None}
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    except AttachmentDecisionError:
        raise
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)


def _claim_recovery_fence(
    item: dict[str, Any],
    actor: Actor,
    *,
    now: datetime,
    repository: Any,
    operation_kind: str,
) -> dict[str, Any]:
    claim = getattr(repository, "claim_stale_upload_operation", None)
    if not claim:
        return item
    recovered = _gateway_call(
        lambda: claim(
            str(item["upload_id"]),
            actor.user_id,
            int(item["version"]),
            operation_kind,
            str(item.get("operation_fence") or ""),
            uuid4().hex,
            int(now.timestamp()),
        )
    )
    if not recovered:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return recovered


def _validate_and_promote_completed(
    item: dict[str, Any],
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    repository: Any,
) -> dict[str, Any]:
    staging_version = str(item.get("staging_version_id") or "")
    if not staging_version or not item.get("staging_object_key"):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    immutable_key = f"objects/{uuid4().hex}"
    immutable_version: str | None = None
    digest = hashlib.sha256()
    length = 0
    validating_version = int(item["version"])
    promotion_started = False
    try:
        response = _provider_mapping(
            lambda: s3.get_object(
                Bucket=settings.s3_images_bucket,
                Key=item["staging_object_key"],
                VersionId=staging_version,
            )
        )
        body = response.get("Body")
        if body is None:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        try:
            read = getattr(body, "read", None)
            if not callable(read):
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            with SpooledTemporaryFile(
                max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b"
            ) as spool:
                maximum = int(item["max_bytes"])
                while True:
                    chunk = read(
                        min(UPLOAD_SPOOL_MEMORY_BYTES, maximum + 1 - length)
                    )
                    if not chunk:
                        break
                    spool.write(chunk)
                    digest.update(chunk)
                    length += len(chunk)
                    if length > maximum:
                        raise ValidationFailure(AttachmentErrorCode.UPLOAD_TOO_LARGE)
                if length != int(item["expected_size"]):
                    raise ValidationFailure(AttachmentErrorCode.UPLOAD_INVALID)
                checksum = digest.hexdigest()
                spool.seek(0)
                detected = validate_uploaded_file(
                    spool, item["original_filename"], item["declared_type"]
                )
                spool.seek(0)
                operation_fence = uuid4().hex
                begin = getattr(repository, "begin_immutable_promotion", None)
                if begin and not _gateway_call(
                    lambda: begin(
                        item["upload_id"],
                        actor.user_id,
                        validating_version,
                        int(now.timestamp()),
                        operation_fence=operation_fence,
                        immutable_object_key=immutable_key,
                        content_sha256=checksum,
                        content_length=detected.size_bytes,
                        detected_type=detected.media_type,
                        image_width=detected.width,
                        image_height=detected.height,
                    )
                ):
                    raise AttachmentDecisionError(
                        AttachmentErrorCode.UPLOAD_NOT_FOUND
                    )
                promotion_started = bool(begin)
                provider_checksum = base64.b64encode(
                    bytes.fromhex(checksum)
                ).decode("ascii")
                immutable_metadata = {
                    "content-sha256": checksum,
                    "upload-id": str(item["upload_id"]),
                    "operation-generation": str(validating_version + 1),
                    "content-length": str(detected.size_bytes),
                    "detected-type": detected.media_type,
                    "purpose": str(item.get("expected_kind") or ""),
                }
                promoted = _provider_mapping(
                    lambda: s3.put_object(
                        Bucket=settings.s3_images_bucket,
                        Key=immutable_key,
                        ContentType=detected.media_type,
                        ServerSideEncryption="AES256",
                        Body=spool,
                        ContentLength=detected.size_bytes,
                        ChecksumSHA256=provider_checksum,
                        Metadata=immutable_metadata,
                        IfNoneMatch="*",
                    )
                )
                immutable_version = _required_provider_coordinate(
                    promoted, "VersionId"
                )
                immutable_etag = _required_provider_coordinate(promoted, "ETag")
                returned_checksum = promoted.get("ChecksumSHA256")
                if returned_checksum is not None:
                    _provider_sha256(returned_checksum, expected_hex=checksum)
                if promotion_started:
                    head = _provider_mapping(
                        lambda: s3.head_object(
                            Bucket=settings.s3_images_bucket,
                            Key=immutable_key,
                            VersionId=immutable_version,
                        )
                    )
                    head_version = head.get("VersionId")
                    if head_version is not None and head_version != immutable_version:
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                        )
                    if _required_provider_coordinate(head, "ETag") != immutable_etag:
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                        )
                    head_length = head.get("ContentLength")
                    if (
                        isinstance(head_length, bool)
                        or not isinstance(head_length, int)
                        or head_length != detected.size_bytes
                    ):
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                        )
                    head_checksum = head.get("ChecksumSHA256")
                    if head_checksum is not None:
                        _provider_sha256(head_checksum, expected_hex=checksum)
                    if head.get("Metadata") != immutable_metadata:
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                        )
                    verified_length, verified_checksum = _exact_object_digest(
                        s3,
                        settings,
                        immutable_key,
                        immutable_version,
                        maximum=detected.size_bytes,
                    )
                    if (
                        verified_length != detected.size_bytes
                        or verified_checksum != checksum
                    ):
                        raise AttachmentDecisionError(
                            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                        )
                record = getattr(repository, "record_immutable_version", None)
                persisted = _gateway_call(
                    lambda: (
                        record(
                            item["upload_id"],
                            actor.user_id,
                            validating_version + 1,
                            operation_fence=operation_fence,
                            immutable_version_id=immutable_version,
                            immutable_etag=immutable_etag,
                            validated_at=now.isoformat(),
                        )
                        if record
                        else repository.mark_validated(
                            item["upload_id"],
                            actor.user_id,
                            validating_version,
                            {
                                "detected_type": detected.media_type,
                                "content_length": detected.size_bytes,
                                "content_sha256": checksum,
                                "immutable_object_key": immutable_key,
                                "immutable_version_id": immutable_version,
                                "immutable_etag": immutable_etag,
                                "image_width": detected.width,
                                "image_height": detected.height,
                                "validated_at": now.isoformat(),
                            },
                        )
                    )
                )
                if not persisted:
                    raise AttachmentDecisionError(
                        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                    )
        finally:
            _close_provider_body(body)
        validated_version = validating_version + (2 if promotion_started else 1)
        _reconcile_staging_cleanup_debt(
            {
                **item,
                "status": "validated",
                "version": validated_version,
                "staging_cleanup_status": "pending",
            },
            s3=s3,
            settings=settings,
            repository=repository,
        )
        return {"uploadId": item["upload_id"], "status": "validated", "attachment": None}
    except ValidationFailure as exc:
        failure_code = exc.code
        if not promotion_started:
            _gateway_call(
                lambda: repository.mark_invalid(
                    item["upload_id"],
                    actor.user_id,
                    validating_version,
                    failure_code.value,
                )
            )
        _delete_exact_if_present(
            s3,
            settings,
            item.get("staging_object_key"),
            staging_version,
        )
        raise AttachmentDecisionError(failure_code) from None
    except AttachmentDecisionError:
        raise
    except Exception:
        # Once promotion starts, its exact key/checksum/length/fence remain durable.
        # Never erase a possibly successful provider write before restart recovery.
        if immutable_version and not promotion_started:
            _delete_exact_if_present(s3, settings, immutable_key, immutable_version)
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None


def _delete_exact_if_present(
    s3: Any,
    settings: Settings,
    key: Any,
    version_id: Any,
) -> None:
    if not key or not version_id:
        return
    try:
        s3.delete_object(
            Bucket=settings.s3_images_bucket,
            Key=str(key),
            VersionId=str(version_id),
        )
    except Exception:
        pass


def _reconcile_staging_cleanup_debt(
    item: dict[str, Any], *, s3: Any, settings: Settings, repository: Any
) -> bool:
    """Clear a durable staging coordinate only after exact listed absence."""
    if item.get("staging_cleanup_status") != "pending":
        return True
    key = item.get("staging_object_key")
    version_id = item.get("staging_version_id")
    if not isinstance(key, str) or not key or not isinstance(version_id, str) or not version_id:
        return False
    try:
        s3.delete_object(
            Bucket=settings.s3_images_bucket,
            Key=key,
            VersionId=version_id,
        )
    except Exception:
        pass
    try:
        absent, cursor, _pages = _exact_version_absence(
            s3, settings, key, version_id
        )
        if not absent or cursor is not None:
            return False
        return bool(
            repository.clear_staging_coordinates(
                item["upload_id"], item["owner_id"], int(item["version"])
            )
        )
    except Exception:
        return False


def resolve_owned_upload(
    upload_id: str, actor: Actor, *, now: datetime | None = None, repository: Any = attachment_repo
) -> dict[str, Any]:
    item = _gateway_call(lambda: repository.get_upload_intent(upload_id))
    if item is not None and not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if not item or item.get("owner_id") != actor.user_id:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now_epoch = int((now or datetime.now(UTC)).timestamp())
    if int(item.get("expires_at", 0)) <= now_epoch:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_EXPIRED)
    return item


def resolve_owned_attachment(
    attachment_id: str, actor: Actor, *, repository: Any = attachment_repo
) -> dict[str, Any]:
    item = _gateway_call(lambda: repository.get_attachment(attachment_id))
    if item is not None and not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if not item or item.get("owner_id") != actor.user_id or item.get("status") != "active":
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    _require_immutable_record(item)
    return item


def _require_immutable_record(item: dict[str, Any]) -> None:
    if (
        not all(
            item.get(field)
            for field in (
                "immutable_object_key",
                "immutable_version_id",
                "immutable_etag",
                "content_sha256",
                "original_filename",
                "detected_type",
            )
        )
        or int(item.get("content_length", 0)) <= 0
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)


def prepare_message_attachments(
    references: list[AttachmentReference],
    actor: Actor,
    *,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve the complete owner list before any message, quota, or AI effect."""
    now = now or datetime.now(UTC)
    prepared: list[tuple[str, dict[str, Any]]] = []
    for reference in references:
        if reference.upload_id is not None:
            item = resolve_owned_upload(reference.upload_id, actor, now=now, repository=repository)
            if (
                item.get("status") != "validated"
                or item.get("expected_kind") != "conversation_attachment"
            ):
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
            _require_immutable_record(item)
            prepared.append(("upload", item))
        else:
            prepared.append(
                (
                    "attachment",
                    resolve_owned_attachment(
                        str(reference.attachment_id), actor, repository=repository
                    ),
                )
            )
    return prepared


def reserve_question_attachment(
    reference: AttachmentReference,
    actor: Actor,
    *,
    effective_plan: str,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, Any]:
    """Resolve an owner image and exclusively reserve fresh uploads before OCR."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if reference.upload_id is not None:
        upload = resolve_owned_upload(reference.upload_id, actor, now=now, repository=repository)
        if (
            upload.get("status") != "validated"
            or upload.get("expected_kind") != "question_image"
            or upload.get("detected_type") not in {"image/jpeg", "image/png"}
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        _require_immutable_record(upload)
        if repository.get_storage_usage(actor.user_id) + int(
            upload["content_length"]
        ) > storage_limit_for_entitlement(effective_plan):
            raise AttachmentDecisionError(AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED)
        version = int(upload.get("version", 0))
        if not repository.reserve_upload_for_question(
            str(reference.upload_id), actor.user_id, version, int(now.timestamp())
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        attachment_id = str(uuid4())
        attachment = {
            "attachment_id": attachment_id,
            "owner_id": actor.user_id,
            "student_id": actor.user_id,
            "entity_type": "attachment",
            "schema_version": "attachment.v1",
            "immutable_object_key": upload["immutable_object_key"],
            "immutable_version_id": upload["immutable_version_id"],
            "immutable_etag": upload["immutable_etag"],
            "content_sha256": upload["content_sha256"],
            "original_filename": upload["original_filename"],
            "detected_type": upload["detected_type"],
            "content_length": int(upload["content_length"]),
            "status": "active",
            "created_at": now.isoformat(),
            "source_upload_id": upload["upload_id"],
            "ref_count": 1,
        }
        return {
            "kind": "upload",
            "identity": reference.identity,
            "record": {
                **upload,
                "status": "consuming",
                "version": version + 1,
                "consume_epoch": int(now.timestamp()),
            },
            "attachment": attachment,
        }

    attachment = resolve_owned_attachment(
        str(reference.attachment_id), actor, repository=repository
    )
    if attachment.get("detected_type") not in {"image/jpeg", "image/png"}:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return {
        "kind": "attachment",
        "identity": reference.identity,
        "record": attachment,
        "attachment": attachment,
    }


def release_question_attachment_reservation(
    prepared: dict[str, Any],
    actor: Actor,
    *,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> None:
    if prepared["kind"] != "upload":
        return
    now = (now or datetime.now(UTC)).astimezone(UTC)
    upload = prepared["record"]
    repository.release_question_upload_reservation(
        upload["upload_id"],
        actor.user_id,
        int(upload["version"]),
        int(now.timestamp()),
    )


def invalidate_question_attachment(
    prepared: dict[str, Any],
    actor: Actor,
    *,
    repository: Any = attachment_repo,
) -> None:
    if prepared["kind"] == "upload":
        upload = prepared["record"]
        repository.invalidate_question_upload_reservation(
            upload["upload_id"],
            actor.user_id,
            int(upload["version"]),
            AttachmentErrorCode.UPLOAD_INVALID.value,
        )
        return
    repository.invalidate_attachment(prepared["attachment"]["attachment_id"], actor.user_id)


def commit_question_with_attachment(
    *,
    question: dict[str, Any],
    prepared: dict[str, Any],
    actor: Actor,
    effective_plan: str,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> AttachmentSummary:
    """Atomically commit question, association, consumption and first-byte charge."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    attachment = prepared["attachment"]
    association = {
        **repository.question_association_key(attachment["attachment_id"], question["question_id"]),
        "attachment_id": attachment["attachment_id"],
        "owner_id": actor.user_id,
        "student_id": actor.user_id,
        "entity_type": "attachment_association",
        "resource_type": "question",
        "resource_id": question["question_id"],
        "created_at": now.isoformat(),
    }
    try:
        repository.transact(
            repository.build_question_attachment_transaction(
                question=question,
                prepared=prepared,
                attachment=attachment,
                association=association,
                owner_id=actor.user_id,
                limit_bytes=storage_limit_for_entitlement(effective_plan),
                now_iso=now.isoformat(),
            )
        )
    except attachment_repo.AttachmentTransactionError as exc:
        raise AttachmentDecisionError(_transaction_error_code(exc.outcome)) from None
    return _attachment_summary(attachment)


def ensure_message_attachment_capacity(
    prepared: list[tuple[str, dict[str, Any]]],
    owner_id: str,
    effective_plan: str,
    *,
    repository: Any = attachment_repo,
) -> None:
    fresh_bytes = sum(int(item["content_length"]) for kind, item in prepared if kind == "upload")
    used_bytes = _gateway_call(lambda: repository.get_storage_usage(owner_id))
    if used_bytes + fresh_bytes > storage_limit_for_entitlement(
        effective_plan
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED)


def bind_message_attachments(
    *,
    message: dict[str, Any],
    conversation_id: str,
    actor: Actor,
    prepared: list[tuple[str, dict[str, Any]]],
    effective_plan: str,
    now: datetime | None = None,
    repository: Any = attachment_repo,
    command: dict[str, Any] | None = None,
    deterministic_attachment_ids: list[str] | None = None,
) -> list[AttachmentSummary]:
    """Atomically persist a message and every fresh/reused attachment reference."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fresh_count = sum(kind == "upload" for kind, _ in prepared)
    if deterministic_attachment_ids is not None:
        if len(deterministic_attachment_ids) != fresh_count or any(
            not isinstance(value, str) or not value.strip()
            for value in deterministic_attachment_ids
        ):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    fresh: list[tuple[dict[str, Any], dict[str, Any]]] = []
    reused: list[dict[str, Any]] = []
    summaries: list[AttachmentSummary] = []
    associations: list[dict[str, Any]] = []
    bound_attachment_ids: list[str] = []
    deterministic_ids = iter(deterministic_attachment_ids or [])
    for kind, item in prepared:
        if kind == "upload":
            attachment_id = (
                next(deterministic_ids)
                if deterministic_attachment_ids is not None
                else str(uuid4())
            )
            attachment = {
                "attachment_id": attachment_id,
                "owner_id": actor.user_id,
                "student_id": actor.user_id,
                "entity_type": "attachment",
                "schema_version": "attachment.v1",
                "immutable_object_key": item["immutable_object_key"],
                "immutable_version_id": item["immutable_version_id"],
                "immutable_etag": item["immutable_etag"],
                "content_sha256": item["content_sha256"],
                "original_filename": item["original_filename"],
                "detected_type": item["detected_type"],
                "content_length": int(item["content_length"]),
                "status": "active",
                "created_at": now.isoformat(),
                "source_upload_id": item["upload_id"],
                "ref_count": 1,
            }
            item = {**item, "consume_epoch": int(now.timestamp())}
            fresh.append((item, attachment))
        else:
            attachment = item
            attachment_id = str(item["attachment_id"])
            reused.append(item)
        bound_attachment_ids.append(attachment_id)
        associations.append(
            {
                **repository.association_key(
                    attachment_id, "conversation", conversation_id, message["message_id"]
                ),
                "attachment_id": attachment_id,
                "owner_id": actor.user_id,
                "student_id": actor.user_id,
                "entity_type": "attachment_association",
                "resource_type": "conversation",
                "resource_id": conversation_id,
                "message_id": message["message_id"],
                "created_at": now.isoformat(),
            }
        )
        summaries.append(_attachment_summary(attachment))
    message["attachment_ids"] = bound_attachment_ids
    limit = storage_limit_for_entitlement(effective_plan)
    ensure_message_attachment_capacity(
        prepared, actor.user_id, effective_plan, repository=repository
    )
    try:
        repository.transact(
            repository.build_message_attachment_transaction(
                message=message,
                fresh=fresh,
                reused=reused,
                associations=associations,
                owner_id=actor.user_id,
                limit_bytes=limit,
                now_iso=now.isoformat(),
                command=command,
            )
        )
    except attachment_repo.AttachmentTransactionError as exc:
        raise AttachmentDecisionError(_transaction_error_code(exc.outcome)) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None
    return summaries


def _transaction_error_code(
    outcome: attachment_repo.AttachmentTransactionOutcome,
) -> AttachmentErrorCode:
    return {
        attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED: (
            AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
        ),
        attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY: (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ),
        attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT: (
            AttachmentErrorCode.UPLOAD_NOT_FOUND
        ),
    }[outcome]


class AttachmentContextDisposition(StrEnum):
    READY = "ready"
    RETRYABLE = "retryable"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class AttachmentContextResult:
    disposition: AttachmentContextDisposition
    context: str = ""
    error_code: AttachmentErrorCode | None = None


def extract_message_attachment_context(
    prepared: list[tuple[str, dict[str, Any]]],
    *,
    s3: Any,
    settings: Settings,
) -> AttachmentContextResult:
    """Return one all-or-nothing typed context from exact immutable private bytes."""
    parts: list[str] = []
    total = 0
    for _, item in prepared:
        try:
            _require_immutable_record(item)
        except AttachmentDecisionError:
            return AttachmentContextResult(
                AttachmentContextDisposition.INVALID,
                error_code=AttachmentErrorCode.UPLOAD_NOT_FOUND,
            )
        length = int(item["content_length"])
        body = None
        primary_error: DocumentExtractionFailure | None = None
        value = ""
        try:
            response = _provider_mapping(
                lambda: s3.get_object(
                    Bucket=settings.s3_images_bucket,
                    Key=item["immutable_object_key"],
                    VersionId=item["immutable_version_id"],
                )
            )
            body = response.get("Body")
            if body is None:
                raise DocumentExtractionFailure("service_unavailable")
            response_etag = response.get("ETag")
            response_length = response.get("ContentLength")
            if (
                not isinstance(response_etag, str)
                or response_etag != item["immutable_etag"]
                or type(response_length) is not int
                or response_length != length
            ):
                raise DocumentExtractionFailure("immutable_bytes_changed")
            digest = hashlib.sha256()
            measured = 0
            read = getattr(body, "read", None)
            if not callable(read):
                raise DocumentExtractionFailure("service_unavailable")
            with SpooledTemporaryFile(
                max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b"
            ) as spool:
                while True:
                    chunk = read(
                        min(UPLOAD_SPOOL_MEMORY_BYTES, length + 1 - measured)
                    )
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise DocumentExtractionFailure("service_unavailable")
                    spool.write(chunk)
                    digest.update(chunk)
                    measured += len(chunk)
                    if measured > length:
                        break
                if measured != length or digest.hexdigest() != item["content_sha256"]:
                    raise DocumentExtractionFailure("immutable_bytes_changed")
                spool.seek(0)
                try:
                    detected = validate_uploaded_file(
                        spool,
                        item["original_filename"],
                        item["detected_type"],
                    )
                except ValidationFailure:
                    raise DocumentExtractionFailure("invalid_document") from None
                if detected.media_type != item["detected_type"]:
                    raise DocumentExtractionFailure("immutable_bytes_changed")
                spool.seek(0)
                parsed = parse_document_isolated(spool, item["detected_type"])
                if parsed.category is not None:
                    raise DocumentExtractionFailure(parsed.category)
                value = (parsed.text or "").strip()
        except DocumentExtractionFailure as error:
            primary_error = error
        except Exception:
            primary_error = DocumentExtractionFailure("service_unavailable")
        finally:
            close_ok = body is None or _close_provider_body(body)
        if primary_error is None and not close_ok:
            primary_error = DocumentExtractionFailure("service_unavailable")
        if primary_error is not None:
            if primary_error.category == "no_extractable_text":
                continue
            if primary_error.category in {
                "invalid_document",
                "active_content",
                "encrypted_document",
                "unsupported_document",
                "document_limit_exceeded",
            }:
                return AttachmentContextResult(
                    AttachmentContextDisposition.INVALID,
                    error_code=AttachmentErrorCode.UPLOAD_INVALID,
                )
            return AttachmentContextResult(
                AttachmentContextDisposition.RETRYABLE,
                error_code=AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
            )
        if not value:
            continue
        remaining = MAX_EXTRACTED_CHARACTERS - total
        if remaining <= 0:
            break
        value = value[:remaining]
        parts.append(value)
        total += len(value)
    return AttachmentContextResult(
        AttachmentContextDisposition.READY,
        context="\n\n".join(parts),
    )


def release_resource_attachments(
    owner_id: str,
    resource_type: str,
    resource_id: str,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> RetentionResult:
    """Release references and retain a retryable tombstone for last-byte deletion."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fence: dict[str, Any] | None = None
    activate_fence = getattr(repository, "activate_retention_fence", None)
    if callable(activate_fence):
        try:
            fence = activate_fence(
                owner_id,
                resource_type=resource_type,
                resource_id=resource_id,
                now_iso=now.isoformat(),
            )
        except attachment_repo.AttachmentRepositoryConflict as exc:
            disposition = (
                RetentionDisposition.INCOMPLETE_RETRYABLE
                if exc.category == "dependency_failure"
                else RetentionDisposition.CONFLICT
            )
            return RetentionResult(disposition, RetentionStage.FENCED)
    try:
        items = _list_owner_retention_items(repository, owner_id, fence)
    except attachment_repo.AttachmentRepositoryConflict as exc:
        disposition = (
            RetentionDisposition.INCOMPLETE_RETRYABLE
            if exc.category == "dependency_failure"
            else RetentionDisposition.CONFLICT
        )
        return RetentionResult(disposition, RetentionStage.RETRYABLE)
    attachments = {
        item["attachment_id"]: item for item in items if item.get("entity_type") == "attachment"
    }
    associations = [
        item
        for item in items
        if item.get("entity_type") == "attachment_association"
        and item.get("resource_type") == resource_type
        and item.get("resource_id") == resource_id
    ]
    released = deleted = 0
    disposition = RetentionDisposition.COMPLETE
    for association in associations:
        attachment = attachments.get(association.get("attachment_id"))
        if not attachment or attachment.get("status") != "active":
            disposition = RetentionDisposition.CONCEALED_MISSING
            continue
        last = int(attachment.get("ref_count", 1)) == 1
        try:
            repository.transact(
                repository.build_release_reference_transaction(
                    attachment=attachment,
                    association=association,
                    last_reference=last,
                )
            )
        except attachment_repo.AttachmentRepositoryConflict:
            disposition = RetentionDisposition.CONFLICT
            continue
        released += 1
        if last:
            pending = {
                **attachment,
                "status": "deletion_pending",
                "deletion_stage": RetentionStage.OBJECT_DELETION_PENDING.value,
                "deletion_resource_type": resource_type,
                "deletion_resource_id": resource_id,
            }
            if _finish_pending_deletion(
                pending, s3=s3, settings=settings, now=now, repository=repository
            ):
                deleted += 1
        else:
            attachment["ref_count"] = int(attachment.get("ref_count", 1)) - 1
    for attachment in attachments.values():
        if (
            attachment.get("status") == "deletion_pending"
            and attachment.get("deletion_resource_type") == resource_type
            and attachment.get("deletion_resource_id") == resource_id
            and _finish_pending_deletion(
                attachment, s3=s3, settings=settings, now=now, repository=repository
            )
        ):
            deleted += 1
    try:
        quiescent_items = _list_owner_retention_items(repository, owner_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    remaining = [
        item
        for item in quiescent_items
        if (
            item.get("entity_type") == "attachment_association"
            and item.get("resource_type") == resource_type
            and item.get("resource_id") == resource_id
        )
        or (
            item.get("entity_type") == "attachment"
            and item.get("status") == "deletion_pending"
            and item.get("deletion_resource_type") == resource_type
            and item.get("deletion_resource_id") == resource_id
        )
    ]
    if remaining:
        if disposition is RetentionDisposition.COMPLETE:
            disposition = RetentionDisposition.INCOMPLETE_RETRYABLE
        return RetentionResult(
            disposition,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    if disposition is not RetentionDisposition.COMPLETE:
        return RetentionResult(
            disposition,
            RetentionStage.CONFLICT,
            released=released,
            deleted=deleted,
        )
    complete_fence = getattr(repository, "complete_retention_fence", None)
    if fence is not None and callable(complete_fence):
        try:
            if not complete_fence(fence, now_iso=now.isoformat()):
                return RetentionResult(
                    RetentionDisposition.CONFLICT,
                    RetentionStage.CONFLICT,
                    released=released,
                    deleted=deleted,
                )
        except attachment_repo.AttachmentRepositoryConflict:
            return RetentionResult(
                RetentionDisposition.INCOMPLETE_RETRYABLE,
                RetentionStage.RETRYABLE,
                released=released,
                deleted=deleted,
            )
    return RetentionResult(
        RetentionDisposition.COMPLETE,
        RetentionStage.COMPLETE,
        released=released,
        deleted=deleted,
    )


def purge_student_attachments(
    student_id: str,
    *,
    s3: Any,
    settings: Settings,
    repository: Any = attachment_repo,
) -> RetentionResult:
    """Account-closure hook: idempotently release every remaining owner association."""
    now = datetime.now(UTC)
    fence: dict[str, Any] | None = None
    activate_fence = getattr(repository, "activate_retention_fence", None)
    if callable(activate_fence):
        try:
            fence = activate_fence(student_id, now_iso=now.isoformat())
        except attachment_repo.AttachmentRepositoryConflict as exc:
            disposition = (
                RetentionDisposition.INCOMPLETE_RETRYABLE
                if exc.category == "dependency_failure"
                else RetentionDisposition.CONFLICT
            )
            return RetentionResult(disposition, RetentionStage.FENCED)
    try:
        items = _list_owner_retention_items(repository, student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE, RetentionStage.RETRYABLE
        )
    resources = {
        (str(item["resource_type"]), str(item["resource_id"]))
        for item in items
        if item.get("entity_type") == "attachment_association"
    }
    released = deleted = 0
    for resource_type, resource_id in sorted(resources):
        result = release_resource_attachments(
            student_id,
            resource_type,
            resource_id,
            s3=s3,
            settings=settings,
            repository=repository,
        )
        released += result["released"]
        deleted += result["deleted"]
        if result.disposition is not RetentionDisposition.COMPLETE:
            return RetentionResult(
                result.disposition,
                result.stage,
                released=released,
                deleted=deleted,
            )
    try:
        pending_items = _list_owner_retention_items(repository, student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    for attachment in pending_items:
        if (
            attachment.get("entity_type") == "attachment"
            and attachment.get("status") == "deletion_pending"
            and _finish_pending_deletion(
                attachment,
                s3=s3,
                settings=settings,
                now=now,
                repository=repository,
            )
        ):
            deleted += 1
    list_cleanup_debts = getattr(repository, "list_owner_staging_cleanup_debts", None)
    if callable(list_cleanup_debts):
        try:
            cleanup_debts = list_cleanup_debts(student_id)
        except attachment_repo.AttachmentRepositoryConflict:
            return RetentionResult(
                RetentionDisposition.INCOMPLETE_RETRYABLE,
                RetentionStage.RETRYABLE,
                released=released,
                deleted=deleted,
            )
        if any(
            not _reconcile_staging_cleanup_debt(
                debt, s3=s3, settings=settings, repository=repository
            )
            for debt in cleanup_debts
        ):
            return RetentionResult(
                RetentionDisposition.INCOMPLETE_RETRYABLE,
                RetentionStage.RETRYABLE,
                released=released,
                deleted=deleted,
            )
    try:
        quiescent_items = _list_owner_retention_items(repository, student_id, fence)
    except attachment_repo.AttachmentRepositoryConflict:
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    if any(
        item.get("entity_type") in {"attachment", "attachment_association"}
        for item in quiescent_items
    ):
        return RetentionResult(
            RetentionDisposition.INCOMPLETE_RETRYABLE,
            RetentionStage.RETRYABLE,
            released=released,
            deleted=deleted,
        )
    complete_fence = getattr(repository, "complete_retention_fence", None)
    if fence is not None and callable(complete_fence):
        try:
            if not complete_fence(fence, now_iso=now.isoformat()):
                return RetentionResult(
                    RetentionDisposition.CONFLICT,
                    RetentionStage.CONFLICT,
                    released=released,
                    deleted=deleted,
                )
        except attachment_repo.AttachmentRepositoryConflict:
            return RetentionResult(
                RetentionDisposition.INCOMPLETE_RETRYABLE,
                RetentionStage.RETRYABLE,
                released=released,
                deleted=deleted,
            )
    return RetentionResult(
        RetentionDisposition.COMPLETE,
        RetentionStage.COMPLETE,
        released=released,
        deleted=deleted,
    )


def release_conversation_attachments(
    owner_id: str,
    conversation_id: str,
    *,
    s3: Any,
    settings: Settings,
    repository: Any = attachment_repo,
) -> RetentionResult:
    """Conversation-deletion integration hook."""
    return release_resource_attachments(
        owner_id,
        "conversation",
        conversation_id,
        s3=s3,
        settings=settings,
        repository=repository,
    )


def _finish_pending_deletion(
    attachment: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    repository: Any,
) -> bool:
    try:
        _require_immutable_record(attachment)
    except Exception:
        return False
    try:
        s3.delete_object(
            Bucket=settings.s3_images_bucket,
            Key=attachment["immutable_object_key"],
            VersionId=attachment["immutable_version_id"],
        )
    except Exception:
        # A provider error may be a lost response; exact listing decides progress.
        pass
    try:
        absent, cursor, _pages = _exact_version_absence(
            s3,
            settings,
            str(attachment["immutable_object_key"]),
            str(attachment["immutable_version_id"]),
        )
        if not absent or cursor is not None:
            return False
        mark_absent = getattr(repository, "mark_deletion_absence_proven", None)
        if callable(mark_absent) and not mark_absent(attachment):
            current = repository.get_attachment(attachment["attachment_id"])
            if not current or current.get("deletion_stage") != RetentionStage.OBJECT_ABSENCE_PROVEN:
                return False
        attachment = {
            **attachment,
            "deletion_stage": RetentionStage.OBJECT_ABSENCE_PROVEN.value,
        }
        repository.transact(
            repository.build_finalize_deletion_transaction(attachment, now.isoformat())
        )
    except attachment_repo.AttachmentRepositoryConflict:
        get_attachment = getattr(repository, "get_attachment", None)
        if callable(get_attachment):
            try:
                return get_attachment(attachment["attachment_id"]) is None
            except Exception:
                return False
        return False
    except Exception:
        get_attachment = getattr(repository, "get_attachment", None)
        if callable(get_attachment):
            try:
                return get_attachment(attachment["attachment_id"]) is None
            except Exception:
                return False
        return False
    return True


def list_attachment_summaries(
    attachment_ids: list[str], *, repository: Any = attachment_repo
) -> dict[str, AttachmentSummary]:
    records = repository.get_attachments(list(dict.fromkeys(attachment_ids)))
    return {
        attachment_id: _attachment_summary(item)
        for attachment_id, item in records.items()
        if item.get("status") == "active"
    }


def attachment_summaries_for_records(
    attachment_ids: list[str], records: dict[str, dict[str, Any]]
) -> list[AttachmentSummary]:
    """Project already-authorized active records without another repository read."""
    return [
        _attachment_summary(records[value])
        for value in attachment_ids
        if value in records and records[value].get("status") == "active"
    ]


def _attachment_summary(item: dict[str, Any]) -> AttachmentSummary:
    return AttachmentSummary(
        attachmentId=item["attachment_id"],
        filename=item["original_filename"],
        mediaType=item["detected_type"],
        sizeBytes=int(item["content_length"]),
        status=AttachmentStatus.ACTIVE,
        createdAt=item["created_at"],
    )
