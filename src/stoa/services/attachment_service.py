"""Owner-bound upload lifecycle orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePath
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
from stoa.models.attachment import UploadIntentRequest
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.services.file_validation_service import MIME_BY_EXTENSION
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file


def storage_limit_for_entitlement(effective_plan: str) -> int:
    return PAID_STORAGE_BYTES if effective_plan in {"standard", "premium"} else FREE_STORAGE_BYTES


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
    object_key = f"uploads/{uuid4().hex}/{upload_id}.{extension}"
    expires_epoch = int(now.timestamp()) + UPLOAD_INTENT_TTL_SECONDS
    item = {
        "upload_id": upload_id,
        "owner_id": actor.user_id,
        "object_key": object_key,
        "original_filename": PurePath(request.filename).name,
        "declared_type": request.content_type,
        "expected_kind": request.purpose.value,
        "expected_size": request.size_bytes,
        "max_bytes": max_bytes,
        "status": "pending_upload",
        "version": 1,
        "created_at": now.isoformat(),
        "expires_at": expires_epoch,
    }
    repository.create_upload_intent(item)
    post = s3.generate_presigned_post(
        Bucket=settings.s3_images_bucket,
        Key=object_key,
        Fields={"Content-Type": request.content_type},
        Conditions=[
            {"key": object_key},
            {"Content-Type": request.content_type},
            ["content-length-range", 1, max_bytes],
        ],
        ExpiresIn=UPLOAD_INTENT_TTL_SECONDS,
    )
    return {
        "uploadId": upload_id,
        "url": post["url"],
        "fields": post["fields"],
        "expiresAt": datetime.fromtimestamp(expires_epoch, UTC),
        "maxBytes": max_bytes,
        "acceptedTypes": list(allowed),
        "status": "pending_upload",
    }


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
    return item


def finalize_upload(
    upload_id: str,
    actor: Actor,
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    repository: Any = attachment_repo,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    item = resolve_owned_upload(upload_id, actor, now=now, repository=repository)
    version = int(item.get("version", 0))
    if item.get("status") == "validated":
        return {"uploadId": upload_id, "status": "validated", "attachment": None}
    if item.get("status") != "pending_upload" or not repository.begin_validation(
        upload_id, actor.user_id, version, int(now.timestamp())
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    validating_version = version + 1
    try:
        head = s3.head_object(Bucket=settings.s3_images_bucket, Key=item["object_key"])
        length = int(head.get("ContentLength", -1))
        content_type = str(head.get("ContentType") or "")
        if length < 0 or length > int(item["max_bytes"]):
            raise ValidationFailure(AttachmentErrorCode.UPLOAD_TOO_LARGE)
        if content_type != item["declared_type"]:
            raise ValidationFailure(AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH)
        response = s3.get_object(Bucket=settings.s3_images_bucket, Key=item["object_key"])
        body = response["Body"].read(int(item["max_bytes"]) + 1)
        if len(body) != length:
            raise ValidationFailure(
                AttachmentErrorCode.UPLOAD_TOO_LARGE
                if len(body) > int(item["max_bytes"])
                else AttachmentErrorCode.UPLOAD_INVALID
            )
        detected = validate_uploaded_file(body, item["original_filename"], content_type)
        etag = str(head.get("ETag") or "")
        response_etag = str(response.get("ETag") or etag)
        if etag and response_etag != etag:
            raise ValidationFailure(AttachmentErrorCode.UPLOAD_INVALID)
        attributes = {
            "detected_type": detected.media_type,
            "content_length": detected.size_bytes,
            "etag": etag,
            "image_width": detected.width,
            "image_height": detected.height,
            "validated_at": now.isoformat(),
        }
        if not repository.mark_validated(upload_id, actor.user_id, validating_version, attributes):
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        return {"uploadId": upload_id, "status": "validated", "attachment": None}
    except ValidationFailure as exc:
        repository.mark_invalid(upload_id, actor.user_id, validating_version, exc.code.value)
        raise AttachmentDecisionError(exc.code) from None
    except AttachmentDecisionError:
        raise
    except Exception:
        repository.release_validation(
            upload_id, actor.user_id, validating_version, int(now.timestamp())
        )
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE) from None
