"""Owner-bound upload lifecycle orchestration."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
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
    extract_attachment_text,
)


UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024
UPLOAD_SPOOL_MEMORY_BYTES = 1024 * 1024


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
        if multipart_id and staging_key and not staging_version:
            try:
                s3.abort_multipart_upload(
                    Bucket=settings.s3_images_bucket,
                    Key=staging_key,
                    UploadId=multipart_id,
                )
            except Exception:
                return "retryable"
        if staging_key and staging_version:
            try:
                s3.delete_object(
                    Bucket=settings.s3_images_bucket,
                    Key=staging_key,
                    VersionId=staging_version,
                )
            except Exception:
                return "retryable"
        if not repository.complete_upload_cleanup(
            str(current["upload_id"]), version, now.isoformat()
        ):
            return "retryable"
    except attachment_repo.AttachmentRepositoryConflict:
        return "retryable"
    return "deleted"


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
    expires_epoch = int(now.timestamp()) + UPLOAD_INTENT_TTL_SECONDS
    part_count = (request.size_bytes + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES
    item = {
        "upload_id": upload_id,
        "owner_id": actor.user_id,
        "original_filename": PurePath(request.filename).name,
        "declared_type": request.content_type,
        "expected_kind": request.purpose.value,
        "expected_size": request.size_bytes,
        "max_bytes": max_bytes,
        "part_count": part_count,
        "status": "issuing",
        "version": 1,
        "created_at": now.isoformat(),
        "expires_at": expires_epoch,
    }
    multipart_upload_id: str | None = None
    try:
        repository.create_upload_intent(item)
        created = s3.create_multipart_upload(
            Bucket=settings.s3_images_bucket,
            Key=staging_object_key,
            ContentType=request.content_type,
            ServerSideEncryption="AES256",
            Metadata={"upload-id": upload_id},
            ChecksumAlgorithm="SHA256",
        )
        multipart_upload_id = str(created["UploadId"])
        if not repository.mark_upload_issued(
            upload_id,
            actor.user_id,
            1,
            staging_object_key=staging_object_key,
            multipart_upload_id=multipart_upload_id,
        ):
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
                cleanup_pending=bool(multipart_upload_id),
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
        if claim.get("status") == "completed":
            return _safe_part_receipt(upload_id, part_number, length, checksum)
        if claim.get("lease_owner") != lease_owner:
            for _ in range(20):
                await asyncio.sleep(0.05)
                current = repository.get_upload_part(upload_id, part_number)
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
        try:
            result = s3.upload_part(
                Bucket=settings.s3_images_bucket,
                Key=item["staging_object_key"],
                UploadId=item["multipart_upload_id"],
                PartNumber=part_number,
                Body=spool,
                ContentLength=length,
                ChecksumSHA256=provider_checksum,
            )
        except Exception:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
        if not repository.complete_upload_part(
            upload_id,
            part_number,
            lease_owner,
            provider_etag=str(result.get("ETag") or ""),
            provider_checksum=str(result.get("ChecksumSHA256") or provider_checksum),
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
    try:
        response = s3.list_parts(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            UploadId=item["multipart_upload_id"],
        )
    except Exception:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    for provider_part in response.get("Parts", []):
        if int(provider_part.get("PartNumber", 0)) != part_number:
            continue
        encoded = str(provider_part.get("ChecksumSHA256") or "")
        try:
            provider_hex = base64.b64decode(encoded).hex()
        except Exception:
            provider_hex = ""
        if int(provider_part.get("Size", -1)) != length or provider_hex != checksum:
            _terminal_abort(item, None, s3=s3, settings=settings, repository=repository)
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        if not repository.complete_upload_part(
            item["upload_id"],
            part_number,
            lease_owner,
            provider_etag=str(provider_part.get("ETag") or ""),
            provider_checksum=encoded,
        ):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        return True
    return False


def _terminal_abort(
    item: dict[str, Any],
    actor: Actor | None,
    *,
    s3: Any,
    settings: Settings,
    repository: Any,
) -> None:
    try:
        repository.mark_upload_terminal(
            item["upload_id"],
            item["owner_id"] if actor is None else actor.user_id,
            int(item["version"]),
            "multipart_reconciliation_failed",
        )
    except Exception:
        pass
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
        return {"uploadId": upload_id, "status": "validated", "attachment": None}
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
    parts = repository.list_upload_parts(upload_id)
    if [int(part.get("part_number", 0)) for part in parts] != list(range(1, part_count + 1)):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    if any(part.get("status") != "completed" for part in parts):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_INVALID)
    version = int(item["version"])
    if not repository.begin_upload_assembly(
        upload_id, actor.user_id, version, int(now.timestamp())
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    try:
        result = s3.complete_multipart_upload(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            UploadId=item["multipart_upload_id"],
            MultipartUpload={
                "Parts": [
                    {"PartNumber": int(part["part_number"]), "ETag": part["provider_etag"]}
                    for part in parts
                ]
            },
        )
        if not repository.mark_staging_completed(
            upload_id,
            actor.user_id,
            version + 1,
            staging_version_id=str(result.get("VersionId") or ""),
            staging_etag=str(result.get("ETag") or ""),
        ):
            raise RuntimeError("staging completion transition failed")
    except Exception:
        _terminal_abort(
            {**item, "version": version + 1},
            actor,
            s3=s3,
            settings=settings,
            repository=repository,
        )
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
    completed = {
        **item,
        "status": "validating",
        "version": version + 2,
        "staging_version_id": str(result.get("VersionId") or ""),
        "staging_etag": str(result.get("ETag") or ""),
    }
    return _validate_and_promote_completed(
        completed,
        actor,
        s3=s3,
        settings=settings,
        now=now,
        repository=repository,
    )


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
    immutable_upload_id: str | None = None
    immutable_version: str | None = None
    immutable_etag: str | None = None
    digest = hashlib.sha256()
    length = 0
    validating_version = int(item["version"])
    try:
        response = s3.get_object(
            Bucket=settings.s3_images_bucket,
            Key=item["staging_object_key"],
            VersionId=staging_version,
        )
        with SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b") as spool:
            body = response["Body"]
            maximum = int(item["max_bytes"])
            while True:
                chunk = body.read(min(UPLOAD_SPOOL_MEMORY_BYTES, maximum + 1 - length))
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
            created = s3.create_multipart_upload(
                Bucket=settings.s3_images_bucket,
                Key=immutable_key,
                ContentType=detected.media_type,
                ServerSideEncryption="AES256",
                Metadata={"content-sha256": checksum},
                ChecksumAlgorithm="SHA256",
            )
            immutable_upload_id = str(created["UploadId"])
            promoted_parts: list[dict[str, Any]] = []
            part_number = 1
            while chunk := spool.read(UPLOAD_CHUNK_BYTES):
                encoded = base64.b64encode(hashlib.sha256(chunk).digest()).decode("ascii")
                uploaded = s3.upload_part(
                    Bucket=settings.s3_images_bucket,
                    Key=immutable_key,
                    UploadId=immutable_upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                    ContentLength=len(chunk),
                    ChecksumSHA256=encoded,
                )
                promoted_parts.append(
                    {"PartNumber": part_number, "ETag": str(uploaded.get("ETag") or "")}
                )
                part_number += 1
            promoted = s3.complete_multipart_upload(
                Bucket=settings.s3_images_bucket,
                Key=immutable_key,
                UploadId=immutable_upload_id,
                MultipartUpload={"Parts": promoted_parts},
            )
            immutable_version = str(promoted.get("VersionId") or "")
            immutable_etag = str(promoted.get("ETag") or "")
            if not immutable_version or not immutable_etag:
                raise RuntimeError("immutable version metadata unavailable")
            attributes = {
                "detected_type": detected.media_type,
                "content_length": detected.size_bytes,
                "content_sha256": checksum,
                "immutable_object_key": immutable_key,
                "immutable_version_id": immutable_version,
                "immutable_etag": immutable_etag,
                "image_width": detected.width,
                "image_height": detected.height,
                "validated_at": now.isoformat(),
            }
            if not repository.mark_validated(
                item["upload_id"], actor.user_id, validating_version, attributes
            ):
                raise RuntimeError("immutable tuple persistence failed")
        validated_version = validating_version + 1
        try:
            s3.delete_object(
                Bucket=settings.s3_images_bucket,
                Key=item["staging_object_key"],
                VersionId=staging_version,
            )
            repository.clear_staging_coordinates(
                item["upload_id"], actor.user_id, validated_version
            )
        except Exception:
            # The exact staging version remains server-only and cleanup-eligible.
            pass
        return {"uploadId": item["upload_id"], "status": "validated", "attachment": None}
    except ValidationFailure as exc:
        repository.mark_invalid(
            item["upload_id"], actor.user_id, validating_version, exc.code.value
        )
        _delete_exact_if_present(
            s3,
            settings,
            item.get("staging_object_key"),
            staging_version,
        )
        raise AttachmentDecisionError(exc.code) from None
    except AttachmentDecisionError:
        raise
    except Exception:
        if immutable_upload_id and not immutable_version:
            try:
                s3.abort_multipart_upload(
                    Bucket=settings.s3_images_bucket,
                    Key=immutable_key,
                    UploadId=immutable_upload_id,
                )
            except Exception:
                pass
        if immutable_version:
            _delete_exact_if_present(
                s3, settings, immutable_key, immutable_version
            )
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


def resolve_owned_upload(
    upload_id: str, actor: Actor, *, now: datetime | None = None, repository: Any = attachment_repo
) -> dict[str, Any]:
    item = repository.get_upload_intent(upload_id)
    if not item or item.get("owner_id") != actor.user_id:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    now_epoch = int((now or datetime.now(UTC)).timestamp())
    if int(item.get("expires_at", 0)) <= now_epoch:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_EXPIRED)
    return item


def resolve_owned_attachment(
    attachment_id: str, actor: Actor, *, repository: Any = attachment_repo
) -> dict[str, Any]:
    item = repository.get_attachment(attachment_id)
    if not item or item.get("owner_id") != actor.user_id or item.get("status") != "active":
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    _require_immutable_record(item)
    return item


def _require_immutable_record(item: dict[str, Any]) -> None:
    if not all(
        item.get(field)
        for field in (
            "immutable_object_key",
            "immutable_version_id",
            "immutable_etag",
            "content_sha256",
        )
    ) or int(item.get("content_length", 0)) <= 0:
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
    except attachment_repo.AttachmentRepositoryConflict as exc:
        code = (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            if exc.category == "dependency_failure"
            else AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
        raise AttachmentDecisionError(code) from None
    return _attachment_summary(attachment)


def ensure_message_attachment_capacity(
    prepared: list[tuple[str, dict[str, Any]]],
    owner_id: str,
    effective_plan: str,
    *,
    repository: Any = attachment_repo,
) -> None:
    fresh_bytes = sum(int(item["content_length"]) for kind, item in prepared if kind == "upload")
    if repository.get_storage_usage(owner_id) + fresh_bytes > storage_limit_for_entitlement(
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
) -> list[AttachmentSummary]:
    """Atomically persist a message and every fresh/reused attachment reference."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    fresh: list[tuple[dict[str, Any], dict[str, Any]]] = []
    reused: list[dict[str, Any]] = []
    summaries: list[AttachmentSummary] = []
    associations: list[dict[str, Any]] = []
    attachment_ids: list[str] = []
    for kind, item in prepared:
        if kind == "upload":
            attachment_id = str(uuid4())
            attachment = {
                "attachment_id": attachment_id,
                "owner_id": actor.user_id,
                "student_id": actor.user_id,
                "entity_type": "attachment",
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
        attachment_ids.append(attachment_id)
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
    message["attachment_ids"] = attachment_ids
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
            )
        )
    except attachment_repo.AttachmentRepositoryConflict as exc:
        code = (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            if exc.category == "dependency_failure"
            else AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
        raise AttachmentDecisionError(code) from None
    return summaries


def extract_message_attachment_context(
    prepared: list[tuple[str, dict[str, Any]]],
    *,
    s3: Any,
    settings: Settings,
) -> str:
    """Read immutable private bytes and return bounded model-only document context."""
    parts: list[str] = []
    total = 0
    for _, item in prepared:
        try:
            _require_immutable_record(item)
        except AttachmentDecisionError:
            parts.append("[attachment:immutable_reference_missing]")
            continue
        length = int(item["content_length"])
        try:
            response = s3.get_object(
                Bucket=settings.s3_images_bucket,
                Key=item["immutable_object_key"],
                VersionId=item["immutable_version_id"],
            )
            digest = hashlib.sha256()
            measured = 0
            with SpooledTemporaryFile(max_size=UPLOAD_SPOOL_MEMORY_BYTES, mode="w+b") as spool:
                while True:
                    chunk = response["Body"].read(
                        min(UPLOAD_SPOOL_MEMORY_BYTES, length + 1 - measured)
                    )
                    if not chunk:
                        break
                    spool.write(chunk)
                    digest.update(chunk)
                    measured += len(chunk)
                    if measured > length:
                        break
                if measured != length or digest.hexdigest() != item["content_sha256"]:
                    raise DocumentExtractionFailure("immutable_bytes_changed")
                spool.seek(0)
                value = extract_attachment_text(spool, str(item["detected_type"])).strip()
        except DocumentExtractionFailure as error:
            value = f"[attachment:{error.category}]"
        except Exception:
            value = "[attachment:service_unavailable]"
        if not value:
            continue
        remaining = MAX_EXTRACTED_CHARACTERS - total
        if remaining <= 0:
            break
        value = value[:remaining]
        parts.append(value)
        total += len(value)
    return "\n\n".join(parts)


def release_resource_attachments(
    owner_id: str,
    resource_type: str,
    resource_id: str,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, int]:
    """Release references and retain a retryable tombstone for last-byte deletion."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    items = repository.list_owner_attachment_items(owner_id)
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
    for association in associations:
        attachment = attachments.get(association.get("attachment_id"))
        if not attachment or attachment.get("status") != "active":
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
            continue
        released += 1
        if last:
            pending = {
                **attachment,
                "status": "deletion_pending",
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
    return {"released": released, "deleted": deleted}


def purge_student_attachments(
    student_id: str,
    *,
    s3: Any,
    settings: Settings,
    repository: Any = attachment_repo,
) -> dict[str, int]:
    """Account-closure hook: idempotently release every remaining owner association."""
    items = repository.list_owner_attachment_items(student_id)
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
    for attachment in repository.list_owner_attachment_items(student_id):
        if (
            attachment.get("entity_type") == "attachment"
            and attachment.get("status") == "deletion_pending"
            and _finish_pending_deletion(
                attachment,
                s3=s3,
                settings=settings,
                now=datetime.now(UTC),
                repository=repository,
            )
        ):
            deleted += 1
    return {"released": released, "deleted": deleted}


def release_conversation_attachments(
    owner_id: str,
    conversation_id: str,
    *,
    s3: Any,
    settings: Settings,
    repository: Any = attachment_repo,
) -> dict[str, int]:
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
        s3.delete_object(
            Bucket=settings.s3_images_bucket,
            Key=attachment["immutable_object_key"],
            VersionId=attachment["immutable_version_id"],
        )
        repository.transact(
            repository.build_finalize_deletion_transaction(attachment, now.isoformat())
        )
    except attachment_repo.AttachmentRepositoryConflict:
        return False
    except Exception:
        # The deletion-pending tombstone preserves retryability and prevents reuse.
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


def _attachment_summary(item: dict[str, Any]) -> AttachmentSummary:
    return AttachmentSummary(
        attachmentId=item["attachment_id"],
        filename=item["original_filename"],
        mediaType=item["detected_type"],
        sizeBytes=int(item["content_length"]),
        status=AttachmentStatus.ACTIVE,
        createdAt=item["created_at"],
    )
