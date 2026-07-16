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
from stoa.models.attachment import AttachmentReference, AttachmentStatus, AttachmentSummary, UploadIntentRequest
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.services.file_validation_service import MIME_BY_EXTENSION
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file
from stoa.services.document_extraction_service import (
    MAX_EXTRACTED_CHARACTERS,
    DocumentExtractionFailure,
    extract_attachment_text,
)


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
            if item.get("status") != "validated" or item.get("expected_kind") != "conversation_attachment":
                raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
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


def ensure_message_attachment_capacity(
    prepared: list[tuple[str, dict[str, Any]]],
    owner_id: str,
    effective_plan: str,
    *,
    repository: Any = attachment_repo,
) -> None:
    fresh_bytes = sum(
        int(item["content_length"]) for kind, item in prepared if kind == "upload"
    )
    if (
        repository.get_storage_usage(owner_id) + fresh_bytes
        > storage_limit_for_entitlement(effective_plan)
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
                "object_key": item["object_key"],
                "original_filename": item["original_filename"],
                "detected_type": item["detected_type"],
                "content_length": int(item["content_length"]),
                "status": "active",
                "created_at": now.isoformat(),
                "source_upload_id": item["upload_id"],
                "etag": item.get("etag"),
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
    ensure_message_attachment_capacity(prepared, actor.user_id, effective_plan, repository=repository)
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
        length = int(item["content_length"])
        try:
            response = s3.get_object(Bucket=settings.s3_images_bucket, Key=item["object_key"])
            data = response["Body"].read(length + 1)
            if len(data) != length:
                raise DocumentExtractionFailure("immutable_bytes_changed")
            value = extract_attachment_text(data, str(item["detected_type"])).strip()
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
        item["attachment_id"]: item
        for item in items
        if item.get("entity_type") == "attachment"
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
        s3.delete_object(Bucket=settings.s3_images_bucket, Key=attachment["object_key"])
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
