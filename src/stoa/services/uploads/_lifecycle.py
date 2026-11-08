"""An upload's life: issuance, signed parts, completion, validation and promotion, cleanup.

The S3 answers are read through `attachment_service`'s strict parsers
(`_gateway_call`, `_provider_mapping` and the coordinate checks), which the
phase-473 boundary inventory registers there.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import logging
from tempfile import SpooledTemporaryFile
from typing import Any
from uuid import uuid4

from stoa.config import (
    DOCUMENT_MAX_BYTES,
    IMAGE_MAX_BYTES,
    UPLOAD_INTENT_TTL_SECONDS,
    Settings,
)
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.models.attachment import UploadIntentRequest, UploadPartUrlRequest, UploadPurpose
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.db.dynamodb import stored_int
from stoa.services import learning_session, moderation_service
from stoa.services.attachment_service import (
    CLEANUP_RECONCILIATION_MAX_ITEMS,
    CLEANUP_RECONCILIATION_MAX_PAGES,
    UPLOAD_SPOOL_MEMORY_BYTES,
    _canonical_sha256,
    _cleanup_cursor_pair,
    _close_provider_body,
    _exact_version_absence,
    _gateway_call,
    _positive_provider_integer,
    _provider_mapping,
    _provider_sha256,
    _provider_truncation,
    _required_provider_coordinate,
    _safe_gateway_detail,
    safe_attachment_filename,
)
from stoa.services.file_validation_service import MIME_BY_EXTENSION
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file
from stoa.services.image_moderation_service import (
    MODERATED_TYPES,
    ImageContentBlocked,
    ImageModerationUnavailable,
    require_image_passes_moderation,
)
from stoa.services.uploads import _store

logger = logging.getLogger(__name__)


def _require_active_account_fence(
    repository: Any, owner_id: str, generation: int | None = None
) -> dict[str, Any]:
    """The owner's active account fence, read from the account deletion rows."""
    del repository
    return account_deletion_repo.require_active_account_fence(owner_id, generation)


UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024



UPLOAD_OPERATION_LEASE_SECONDS = 120


PROVIDER_RECONCILIATION_MAX_PAGES = 10


PROVIDER_RECONCILIATION_MAX_ITEMS = 10_000


PROVIDER_VERSION_MAX_PAGES = 10


PROVIDER_VERSION_MAX_ITEMS = 10_000




# Who may open an upload, and for what: a teacher only for a reply (#145).
_UPLOAD_PURPOSES_BY_ROLE = {
    CanonicalRole.STUDENT: frozenset(
        {UploadPurpose.QUESTION_IMAGE, UploadPurpose.CONVERSATION_ATTACHMENT}
    ),
    CanonicalRole.TEACHER: frozenset({UploadPurpose.HELP_REPLY_IMAGE}),
}


_IMAGE_ONLY_PURPOSES = frozenset(
    {UploadPurpose.QUESTION_IMAGE, UploadPurpose.HELP_REPLY_IMAGE}
)


def cleanup_upload_intent(
    candidate: dict[str, Any],
    *,
    s3: Any,
    settings: Settings,
    now: datetime,
    reference_scan_limit: int,
    repository: Any = _store,
) -> str:
    """Safely advance one terminal/expired upload toward idempotent deletion."""
    status = str(candidate.get("status") or "")
    now_epoch = int(now.timestamp())
    if status not in {"invalid", "expired", "cleanup_pending"} and (
        _store.usable_until(candidate) > now_epoch
    ):
        # The short operation lease authorizes takeover/reconciliation only;
        # it never shortens the owner-visible 30-minute intent lifetime. Past
        # that lifetime a live lease still defers the claim (`claim_upload_cleanup`).
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
            repository.block_upload_cleanup(
                str(current["upload_id"]), version, now_epoch=now_epoch
            )
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
            repository.block_upload_cleanup(
                str(current["upload_id"]), version, now_epoch=now_epoch
            )
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

        if not current.get("cleanup_parts_absent"):
            scrubbed = repository.scrub_upload_parts(
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
            str(current["upload_id"]), version, now.isoformat(), now_epoch=now_epoch
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
    repository: Any = _store,
    upload_id: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Open an upload; `conversation_id` binds it to that one conversation (#146)."""
    if request.purpose not in _UPLOAD_PURPOSES_BY_ROLE.get(actor.role, frozenset()):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    try:
        account_fence = _require_active_account_fence(repository, actor.user_id)
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    account_fence_generation = int(account_fence["generation"])
    if request.conversation_id is not None and not _gateway_call(
        lambda: learning_session.owned_by(request.conversation_id, actor.user_id)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    extension = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    allowed = MIME_BY_EXTENSION.get(extension)
    if allowed is None:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    if request.content_type not in allowed:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
    if request.purpose in _IMAGE_ONLY_PURPOSES and extension not in {"jpg", "jpeg", "png"}:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED)
    max_bytes = IMAGE_MAX_BYTES if extension in {"jpg", "jpeg", "png"} else DOCUMENT_MAX_BYTES
    if request.size_bytes > max_bytes:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)
    upload_id = upload_id or str(uuid4())
    staging_object_key = f"staging/{uuid4().hex}/{upload_id}.{extension}"
    operation_fence = uuid4().hex
    usable_epoch = int(now.timestamp()) + UPLOAD_INTENT_TTL_SECONDS
    part_count = (request.size_bytes + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES
    item = {
        "upload_id": upload_id,
        "owner_id": actor.user_id,
        "student_id": actor.user_id,
        "entity_type": "upload_intent",
        "schema_version": "upload-intent.v1",
        "original_filename": safe_attachment_filename(request.filename),
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
        "account_fence_generation": account_fence_generation,
        "created_at": now.isoformat(),
        # Not `expires_at`: that is the table's TTL, set only once the row has
        # ended (#250), or the table would delete it under the cleanup.
        "usable_until": usable_epoch,
    }
    if request.conversation_id is not None:
        item["conversation_id"] = request.conversation_id
    if conversation_id is not None:
        # A phone upload (#146): `bound_conversation_id` is enforced when it is
        # sent; `conversation_id` is where the moderation queue (#139) records it.
        item["bound_conversation_id"] = conversation_id
        item["conversation_id"] = conversation_id
    multipart_upload_id: str | None = None
    try:
        repository.prepare_staging_issuance(item)
        _require_active_account_fence(
            repository, actor.user_id, account_fence_generation
        )
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
        recorded = repository.record_staging_multipart(
            upload_id,
            actor.user_id,
            1,
            operation_fence=operation_fence,
            multipart_upload_id=multipart_upload_id,
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
            repository.mark_upload_issuance_failed(upload_id, actor.user_id, 1)
        except Exception:
            pass
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    return {
        "uploadId": upload_id,
        "expiresAt": datetime.fromtimestamp(usable_epoch, UTC),
        "maxBytes": max_bytes,
        "chunkBytes": UPLOAD_CHUNK_BYTES,
        "acceptedTypes": list(allowed),
        "status": "pending_upload",
    }


def sign_upload_part(
    upload_id: str,
    part_number: int,
    request: UploadPartUrlRequest,
    actor: Actor,
    *,
    signer: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = _store,
) -> dict[str, Any]:
    """A URL on which the browser puts exactly this part's bytes on S3 (ADR-004).

    A part of `UPLOAD_CHUNK_BYTES` sent through the API arrives at Lambda as base64,
    over its 6 MB request limit (#136). The URL is signed for the part's length and
    SHA-256, so S3 refuses any other body; completion then checks what S3 holds.
    """
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
    if request.size_bytes > expected_length:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_TOO_LARGE)
    if request.size_bytes != expected_length:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    try:
        repository.pin_upload_part(
            upload_id,
            part_number,
            request.checksum_sha256,
            request.size_bytes,
            int(now.timestamp()),
        )
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "chunk_conflict":
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT) from None
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    except AttachmentDecisionError:
        raise
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    provider_checksum = base64.b64encode(bytes.fromhex(request.checksum_sha256)).decode("ascii")
    expires_in = settings.s3_presign_expiry_seconds
    try:
        url = signer.generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": settings.s3_images_bucket,
                "Key": item["staging_object_key"],
                "UploadId": item["multipart_upload_id"],
                "PartNumber": part_number,
                "ContentLength": request.size_bytes,
                "ChecksumSHA256": provider_checksum,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    if not isinstance(url, str) or not url:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return {
        "uploadId": upload_id,
        "partNumber": part_number,
        "url": url,
        "method": "PUT",
        "headers": {"x-amz-checksum-sha256": provider_checksum},
        "expiresAt": datetime.fromtimestamp(int(now.timestamp()) + expires_in, UTC),
    }


def _adopt_presigned_parts(
    item: dict[str, Any],
    parts: list[dict[str, Any]],
    *,
    s3: Any,
    settings: Settings,
    repository: Any,
) -> list[dict[str, Any]]:
    """Record the parts the browser wrote on S3, or refuse completion without them.

    Each part was pinned to a length and SHA-256 when its URL was signed. S3
    checked the body against that checksum, and the listing must show the same
    size and checksum before the ledger takes the part's ETag.
    """
    pending = [part for part in parts if part.get("status") == "uploading"]
    if not pending:
        return parts
    held = _provider_parts(item, s3=s3, settings=settings)
    for part in pending:
        number = int(part["part_number"])
        fact = held.get(number)
        if fact is None:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
        provider_size, provider_etag, encoded = fact
        checksum = str(part["checksum_sha256"])
        length = int(part["content_length"])
        _provider_sha256(encoded, expected_hex=checksum)
        if provider_size != length:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
        if _gateway_call(
            lambda: repository.complete_upload_part(
                item["upload_id"],
                number,
                str(part["lease_owner"]),
                provider_etag=provider_etag,
                provider_checksum=encoded,
                expected_checksum_sha256=checksum,
                content_length=length,
            )
        ):
            continue
        # A concurrent completion recorded this part first; the same acknowledgement
        # from S3 is as good as ours.
        current = _gateway_call(
            lambda: repository.get_upload_part(item["upload_id"], number)
        )
        if not (
            isinstance(current, dict)
            and current.get("status") == "completed"
            and current.get("provider_etag") == provider_etag
            and current.get("provider_checksum") == encoded
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    refreshed = _gateway_call(lambda: repository.list_upload_parts(item["upload_id"]))
    if not isinstance(refreshed, list) or any(not isinstance(part, dict) for part in refreshed):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return refreshed


def _provider_parts(
    item: dict[str, Any], *, s3: Any, settings: Settings
) -> dict[int, tuple[int, str, str]]:
    """Every part S3 holds for the upload: number -> (size, ETag, base64 SHA-256)."""
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
    return seen


def complete_upload(
    upload_id: str,
    part_count: int,
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = _store,
    moderation: Any = None,
) -> dict[str, Any]:
    """Assemble only server-ledger ETags; validation/promotion follows this transition.

    `moderation` is the Rekognition client every image must pass before promotion
    (#138); without one, no image completes.
    """
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
            moderation=moderation,
        )
    if item.get("status") != "pending_upload" or part_count != int(item["part_count"]):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    parts = _gateway_call(lambda: repository.list_upload_parts(upload_id))
    if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if [int(part.get("part_number", 0)) for part in parts] != list(range(1, part_count + 1)):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    parts = _adopt_presigned_parts(
        item, parts, s3=s3, settings=settings, repository=repository
    )
    if any(part.get("status") != "completed" for part in parts):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    version = int(item["version"])
    operation_fence = uuid4().hex
    ledger_digest = _part_ledger_digest(parts)
    claimed = _gateway_call(
        lambda: repository.claim_staging_assembly(
            upload_id,
            actor.user_id,
            version,
            int(now.timestamp()),
            operation_fence=operation_fence,
            multipart_upload_id=str(item["multipart_upload_id"]),
            ordered_part_count=part_count,
            part_ledger_digest=ledger_digest,
        )
    )
    if not claimed:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    try:
        # The multipart upload is created with ChecksumAlgorithm SHA256, so S3
        # rejects a completion whose parts omit the checksum it acknowledged.
        result = _provider_mapping(lambda: s3.complete_multipart_upload(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            UploadId=item["multipart_upload_id"],
            MultipartUpload={
                "Parts": [
                    {
                        "PartNumber": int(part["part_number"]),
                        "ETag": part["provider_etag"],
                        "ChecksumSHA256": part["provider_checksum"],
                    }
                    for part in parts
                ]
            },
        ))
        staging_version_id = _required_provider_coordinate(result, "VersionId")
        staging_etag = _required_provider_coordinate(result, "ETag")
        persisted = _gateway_call(
            lambda: repository.recover_staging_completion(
                upload_id,
                actor.user_id,
                version + 1,
                operation_fence=operation_fence,
                staging_version_id=staging_version_id,
                staging_etag=staging_etag,
            )
        )
        if not persisted:
            # Provider completion succeeded, so a false persistence result is an
            # unknown split outcome that callers must retry through recovery.
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    except AttachmentDecisionError:
        raise
    except Exception as exc:
        # The assembling row retains the exact key, multipart ID, fence and lease.
        # A restart reconciles the exact completed version or aborts it during cleanup.
        logger.error(
            "upload_completion_failed upload_id=%s error_class=%s detail=%s",
            upload_id,
            type(exc).__name__,
            _safe_gateway_detail(exc),
        )
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
        moderation=moderation,
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
            expected_length=_positive_provider_integer(stored_int(item.get("expected_size"))),
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
        expected_length = _positive_provider_integer(stored_int(item.get("content_length")))
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
            if not _gateway_call(
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
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
            # One transition since the recovery claim (the uninterrupted promotion
            # makes two), and it left the staging copy owed, as there (#267).
            _reconcile_staging_cleanup_debt(
                {
                    **item,
                    "status": "validated",
                    "version": int(item["version"]) + 1,
                    "staging_cleanup_status": "pending",
                },
                s3=s3,
                settings=settings,
                repository=repository,
            )
            return {"uploadId": item["upload_id"], "status": "validated", "attachment": None}
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
    recovered = _gateway_call(
        lambda: repository.claim_stale_upload_operation(
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
    moderation: Any = None,
) -> dict[str, Any]:
    staging_version = str(item.get("staging_version_id") or "")
    if not staging_version or not item.get("staging_object_key"):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    immutable_key = f"objects/{uuid4().hex}"
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
                if detected.media_type in MODERATED_TYPES:
                    spool.seek(0)
                    _require_moderated_image(
                        spool.read(),
                        detected,
                        item,
                        actor,
                        moderation=moderation,
                        s3=s3,
                        settings=settings,
                        now=now,
                    )
                spool.seek(0)
                operation_fence = uuid4().hex
                if not _gateway_call(
                    lambda: repository.begin_immutable_promotion(
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
                promotion_started = True
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
                persisted = _gateway_call(
                    lambda: repository.record_immutable_version(
                        item["upload_id"],
                        actor.user_id,
                        validating_version + 1,
                        operation_fence=operation_fence,
                        immutable_version_id=immutable_version,
                        immutable_etag=immutable_etag,
                        validated_at=now.isoformat(),
                    )
                )
                if not persisted:
                    raise AttachmentDecisionError(
                        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                    )
        finally:
            _close_provider_body(body)
        validated_version = validating_version + 2
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
        if isinstance(exc, ImageContentBlocked):
            # Its case and a kept copy are already in the admin review queue
            # (#139, `_require_moderated_image`), so the staging copy can go.
            logger.warning(
                "image_moderation_blocked upload_id=%s labels=%s",
                item["upload_id"],
                ",".join(
                    f"{hit.category}/{hit.label}:{hit.confidence:.1f}" for hit in exc.hits
                ),
            )
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
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None


def _require_moderated_image(
    data: bytes,
    detected: Any,
    item: dict[str, Any],
    actor: Actor,
    *,
    moderation: Any,
    s3: Any,
    settings: Settings,
    now: datetime,
) -> None:
    """Let an image be promoted only on a moderation answer that found nothing.

    A refusal is a `ValidationFailure` and ends the upload, once the image and its
    case are in the admin review queue (#139). No answer, or no case, leaves the
    upload validating, so the next completion asks again; it is never a pass.
    """
    try:
        require_image_passes_moderation(
            data,
            width=int(detected.width),
            height=int(detected.height),
            client=moderation,
            settings=settings,
        )
    except ImageContentBlocked as blocked:
        try:
            moderation_service.open_image_case(
                item,
                uploader_role=actor.role.value,
                data=data,
                media_type=detected.media_type,
                hits=blocked.hits,
                s3=s3,
                settings=settings,
                now=now,
            )
        except Exception as exc:
            logger.error(
                "image_moderation_case_failed upload_id=%s error_class=%s",
                item["upload_id"],
                type(exc).__name__,
            )
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        raise
    except ImageModerationUnavailable as exc:
        logger.error(
            "image_moderation_unavailable upload_id=%s cause=%s",
            item["upload_id"],
            exc.cause,
        )
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None


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
    upload_id: str, actor: Actor, *, now: datetime | None = None, repository: Any = _store
) -> dict[str, Any]:
    item = _gateway_call(lambda: repository.get_upload_intent(upload_id))
    if item is not None and not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    if not item or item.get("owner_id") != actor.user_id:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now_epoch = int((now or datetime.now(UTC)).timestamp())
    if _store.usable_until(item) <= now_epoch:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_EXPIRED)
    return item
