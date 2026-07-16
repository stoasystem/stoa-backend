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
