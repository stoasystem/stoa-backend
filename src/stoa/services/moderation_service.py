"""Content moderation case helpers."""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from io import BytesIO
import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.config import Settings
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import moderation_repo, question_repo
from stoa.models.moderation import (
    ModerationCaseNoteRequest,
    ModerationCaseUpdateRequest,
    ModerationImageStatus,
    ModerationReason,
    ModerationReportRequest,
    ModerationSeverity,
    ModerationStatus,
    ModerationSurface,
)
from stoa.services import notification_service


logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    ModerationStatus.ACTIONED.value,
    ModerationStatus.DISMISSED.value,
    ModerationStatus.CLOSED.value,
}

# A refused image is kept in the images bucket (eu-central-2, ADR-010) under its
# own prefix, readable only through the admin case route. It is deleted 90 days
# after its case is handled (#139, Q18), and in any case 365 days after it was
# uploaded, the longest any child's image is kept: whichever comes first.
CASE_IMAGE_PREFIX = "moderation/"
CASE_IMAGE_RETENTION = timedelta(days=90)
CASE_IMAGE_MAXIMUM_AGE = timedelta(days=365)
IMAGE_MODERATION_ACTOR = "system:image_moderation"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_case(
    question_id: str,
    body: ModerationReportRequest,
    user: dict[str, Any],
    *,
    question: dict[str, Any] | None = None,
) -> dict[str, Any]:
    question = question if question is not None else question_repo.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    _require_report_access(question, user)
    _validate_surface(question, body.surface.value)

    student_id = question.get("student_id")
    privacy_generation = stored_int(question.get("account_fence_generation"))
    if (
        not isinstance(student_id, str)
        or not student_id
        or privacy_generation is None
        or privacy_generation <= 0
    ):
        raise HTTPException(status_code=409, detail="Question is not writable")

    created_at = now_iso()
    case_id = f"mod-{uuid4().hex}"
    reporter_id = str(user.get("sub") or user.get("username") or "unknown")
    reporter_role = str(user.get("role") or "unknown")
    report_note = _clean_note(body.note)
    item: dict[str, object] = {
        "entity_type": "moderation_case",
        "case_id": case_id,
        "status": ModerationStatus.OPEN.value,
        "reason": body.reason.value,
        "severity": body.severity.value,
        "surface": body.surface.value,
        "question_id": question_id,
        "student_id": student_id,
        "privacy_generation": privacy_generation,
        "reporter_id": reporter_id,
        "reporter_role": reporter_role,
        "assigned_admin_id": None,
        "report_note": report_note,
        "resolution_note": None,
        "created_at": created_at,
        "updated_at": created_at,
        "closed_at": None,
        "question_context": _question_context(question),
    }
    event = _event(
        case_id,
        "reported",
        actor_id=reporter_id,
        actor_role=reporter_role,
        at=created_at,
        changes={
            "surface": item["surface"],
            "reason": item["reason"],
            "severity": item["severity"],
        },
        note=report_note,
        student_id=student_id,
        privacy_generation=privacy_generation,
    )
    item["history"] = [event]
    moderation_repo.put_case(item, event)
    notification_service.emit_moderation_created(
        case_item=item,
        actor_id=reporter_id,
        actor_role=reporter_role,
        owner_id=student_id,
        privacy_generation=privacy_generation,
    )
    return item


def open_image_case(
    upload: Mapping[str, Any],
    *,
    uploader_role: str,
    data: bytes,
    media_type: str,
    hits: Iterable[Any],
    s3: Any,
    settings: Settings,
    now: datetime,
) -> dict[str, Any]:
    """Keep an image moderation refused and open its case for the admin queue.

    One case per upload: a completion retried after a failure here finds the case
    already open. Raises when either the image or the case could not be stored,
    so the caller keeps the upload retryable rather than lose the evidence.
    """
    upload_id = str(upload["upload_id"])
    case_id = f"mod-upload-{upload_id}"
    existing = moderation_repo.get_case(case_id)
    if existing:
        return existing
    owner_id = upload.get("owner_id")
    privacy_generation = stored_int(upload.get("account_fence_generation"))
    if (
        not isinstance(owner_id, str)
        or not owner_id
        or privacy_generation is None
        or privacy_generation <= 0
    ):
        raise ValueError("upload has no authoritative owner")
    image_key = f"{CASE_IMAGE_PREFIX}{uuid4().hex}"
    checksum = hashlib.sha256(data).hexdigest()
    stored = s3.put_object(
        Bucket=settings.s3_images_bucket,
        Key=image_key,
        ContentType=media_type,
        ServerSideEncryption="AES256",
        Body=BytesIO(data),
        ContentLength=len(data),
        ChecksumSHA256=base64.b64encode(bytes.fromhex(checksum)).decode("ascii"),
        Metadata={"case-id": case_id, "content-sha256": checksum},
        IfNoneMatch="*",
    )
    image_version = stored.get("VersionId") if isinstance(stored, Mapping) else None
    if not isinstance(image_version, str) or not image_version:
        raise ValueError("stored case image has no version")
    created_at = now.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    item: dict[str, Any] = {
        "entity_type": "moderation_case",
        "case_id": case_id,
        "status": ModerationStatus.OPEN.value,
        "reason": ModerationReason.UNSAFE_CONTENT.value,
        "severity": ModerationSeverity.HIGH.value,
        "surface": ModerationSurface.IMAGE_UPLOAD.value,
        "question_id": None,
        "student_id": owner_id,
        "privacy_generation": privacy_generation,
        "reporter_id": IMAGE_MODERATION_ACTOR,
        "reporter_role": "system",
        "assigned_admin_id": None,
        "report_note": None,
        "resolution_note": None,
        "created_at": created_at,
        "updated_at": created_at,
        "closed_at": None,
        "image_context": {
            "upload_id": upload_id,
            "conversation_id": upload.get("conversation_id"),
            "uploaded_at": str(upload.get("created_at") or created_at),
            "uploader_id": owner_id,
            "uploader_role": uploader_role,
            "media_type": media_type,
            "size_bytes": len(data),
            # DynamoDB takes no floats.
            "hits": [
                {
                    "label": hit.label,
                    "category": hit.category,
                    "confidence": Decimal(str(hit.confidence)),
                }
                for hit in hits
            ],
            "image_status": ModerationImageStatus.STORED.value,
            "image_deleted_at": None,
        },
        "image_object_key": image_key,
        "image_version_id": image_version,
        "image_sha256": checksum,
    }
    event = _event(
        case_id,
        "image_blocked",
        actor_id=IMAGE_MODERATION_ACTOR,
        actor_role="system",
        at=created_at,
        changes={
            "surface": item["surface"],
            "reason": item["reason"],
            "severity": item["severity"],
        },
        note=None,
        student_id=owner_id,
        privacy_generation=privacy_generation,
    )
    item["history"] = [event]
    try:
        moderation_repo.put_case(item, event)
    except Exception:
        # Nothing refers to the image without its case. A write that landed
        # but answered with an error did make the case, so ask before deleting.
        try:
            written = moderation_repo.get_case(case_id)
        except Exception:
            written = None
            orphaned = False
        else:
            orphaned = not written or written.get("image_version_id") != image_version
        if orphaned:
            _delete_image_version(s3, settings, image_key, image_version, quiet=True)
        raise
    notification_service.emit_moderation_created(
        case_item=item,
        actor_id=IMAGE_MODERATION_ACTOR,
        actor_role="system",
        owner_id=owner_id,
        privacy_generation=privacy_generation,
    )
    return item


def read_case_image(case_id: str, *, s3: Any, settings: Settings) -> tuple[bytes, str]:
    """The refused image of an `image_upload` case, exactly as it was stored."""
    item = moderation_repo.get_case(case_id)
    if not item or not _holds_image(item):
        raise HTTPException(status_code=404, detail="Moderation case image not found")
    context = item["image_context"]
    size = int(context["size_bytes"])
    try:
        response = s3.get_object(
            Bucket=settings.s3_images_bucket,
            Key=str(item["image_object_key"]),
            VersionId=str(item["image_version_id"]),
        )
        body = response["Body"]
        try:
            data = body.read(size + 1)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        logger.error(
            "moderation_case_image_unavailable case_id=%s error_class=%s",
            case_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503, detail="Moderation case image is unavailable"
        ) from None
    if len(data) != size or hashlib.sha256(data).hexdigest() != item.get("image_sha256"):
        logger.error("moderation_case_image_mismatch case_id=%s", case_id)
        raise HTTPException(status_code=503, detail="Moderation case image is unavailable")
    return data, str(context["media_type"])


@dataclass(frozen=True, slots=True)
class CaseImageRetentionSummary:
    scanned: int = 0
    deleted: int = 0
    retryable: int = 0


def delete_due_case_images(
    *, s3: Any, settings: Settings, now: datetime, limit: int = 100
) -> CaseImageRetentionSummary:
    """Delete each refused image that is due: 90 days after its case was handled,
    or 365 days after it was uploaded, whichever comes first.

    A case that is open again waits for the 365 days. The case itself stays,
    with its hits, and records that the image is gone.
    """
    now = now.astimezone(timezone.utc)
    scanned = deleted = retryable = 0
    for item in moderation_repo.list_cases(limit=None):
        if deleted + retryable >= limit:
            break
        scanned += 1
        if not _holds_image(item) or not _image_due(item, now):
            continue
        case_id = str(item["case_id"])
        try:
            delete_case_image(item, s3=s3, settings=settings)
            at = now.replace(microsecond=0).isoformat()
            moderation_repo.update_case(
                case_id,
                {
                    "image_context": {
                        **item["image_context"],
                        "image_status": ModerationImageStatus.DELETED.value,
                        "image_deleted_at": at,
                    },
                    "updated_at": at,
                },
            )
            moderation_repo.put_event(
                case_id,
                _event(
                    case_id,
                    "image_deleted",
                    actor_id=IMAGE_MODERATION_ACTOR,
                    actor_role="system",
                    at=at,
                    changes={"image_status": ModerationImageStatus.DELETED.value},
                    note=None,
                    student_id=str(item["student_id"]),
                    privacy_generation=int(item["privacy_generation"]),
                ),
            )
            deleted += 1
        except Exception as exc:
            # Left for the next run; a deleted account's case is the account
            # deletion's to finish.
            logger.warning(
                "moderation_case_image_retention_failed case_id=%s error_class=%s",
                case_id,
                type(exc).__name__,
            )
            retryable += 1
    return CaseImageRetentionSummary(scanned=scanned, deleted=deleted, retryable=retryable)


def _image_due(item: Mapping[str, Any], now: datetime) -> bool:
    context = item["image_context"]
    uploaded_at = _aware(context.get("uploaded_at") or item.get("created_at"))
    if uploaded_at is not None and uploaded_at <= now - CASE_IMAGE_MAXIMUM_AGE:
        return True
    closed_at = _aware(item.get("closed_at"))
    return (
        item.get("status") in TERMINAL_STATUSES
        and closed_at is not None
        and closed_at <= now - CASE_IMAGE_RETENTION
    )


def _aware(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def delete_case_image(item: Mapping[str, Any], *, s3: Any, settings: Settings) -> None:
    """Permanently delete a case's stored image version; raises if S3 refuses."""
    if not _holds_image(item):
        return
    _delete_image_version(
        s3, settings, str(item["image_object_key"]), str(item["image_version_id"])
    )


def _holds_image(item: Mapping[str, Any]) -> bool:
    context = item.get("image_context")
    return (
        item.get("surface") == ModerationSurface.IMAGE_UPLOAD.value
        and isinstance(context, Mapping)
        and context.get("image_status") == ModerationImageStatus.STORED.value
        and bool(item.get("image_object_key"))
        and bool(item.get("image_version_id"))
    )


def _delete_image_version(
    s3: Any, settings: Settings, key: str, version_id: str, *, quiet: bool = False
) -> None:
    try:
        s3.delete_object(Bucket=settings.s3_images_bucket, Key=key, VersionId=version_id)
    except Exception:
        if not quiet:
            raise


def list_cases(
    *,
    limit: int = 50,
    status: str | None = None,
    severity: str | None = None,
    reason: str | None = None,
    reporter_role: str | None = None,
    assignee: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    items = moderation_repo.list_cases(limit=max(limit, 100))
    filtered = [
        item for item in items
        if _matches(item, "status", status)
        and _matches(item, "severity", severity)
        and _matches(item, "reason", reason)
        and _matches(item, "reporter_role", reporter_role)
        and _matches(item, "assigned_admin_id", assignee)
        and _within_dates(item, date_from, date_to)
    ]
    return sorted(filtered, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]


def get_case(case_id: str, *, include_events: bool = True) -> dict[str, Any]:
    item = moderation_repo.get_case(case_id)
    if not item:
        raise HTTPException(status_code=404, detail="Moderation case not found")
    if include_events:
        events = moderation_repo.list_case_events(case_id)
        item = dict(item)
        item["history"] = events or item.get("history") or []
    return item


def update_case(case_id: str, body: ModerationCaseUpdateRequest, user: dict[str, Any]) -> dict[str, Any]:
    existing = get_case(case_id, include_events=False)
    updates: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    now = now_iso()

    if body.status is not None and body.status.value != existing.get("status"):
        updates["status"] = body.status.value
        changes["status"] = body.status.value
        # Handled is when it was last closed: a refused image is deleted 90 days
        # after that (#139), so a reopened case starts over when closed again.
        # While open, its old `closed_at` stays and counts for nothing.
        if (
            body.status.value in TERMINAL_STATUSES
            and existing.get("status") not in TERMINAL_STATUSES
        ):
            updates["closed_at"] = now
    if body.assigned_admin_id is not None and body.assigned_admin_id != existing.get("assigned_admin_id"):
        updates["assigned_admin_id"] = body.assigned_admin_id
        changes["assigned_admin_id"] = body.assigned_admin_id
    if body.resolution_note is not None:
        updates["resolution_note"] = _clean_note(body.resolution_note)
        changes["resolution_note"] = updates["resolution_note"]

    if not updates:
        return get_case(case_id)

    updates["updated_at"] = now
    actor_id = str(user.get("sub") or user.get("username") or "admin")
    event = _event(
        case_id,
        "updated",
        actor_id=actor_id,
        actor_role=str(user.get("role") or "admin"),
        at=now,
        changes=changes,
        note=updates.get("resolution_note"),
        student_id=str(existing["student_id"]),
        privacy_generation=int(existing["privacy_generation"]),
    )
    updated = moderation_repo.update_case(case_id, updates) or {**existing, **updates}
    moderation_repo.put_event(case_id, event)
    updated = dict(updated)
    updated["history"] = moderation_repo.list_case_events(case_id) or [event]
    notification_service.emit_moderation_update(
        case_item=updated,
        actor_id=actor_id,
        actor_role=str(user.get("role") or "admin"),
        owner_id=str(existing["student_id"]),
        privacy_generation=int(existing["privacy_generation"]),
    )
    return updated


def add_note(case_id: str, body: ModerationCaseNoteRequest, user: dict[str, Any]) -> dict[str, Any]:
    existing = get_case(case_id, include_events=False)
    now = now_iso()
    actor_id = str(user.get("sub") or user.get("username") or "admin")
    event = _event(
        case_id,
        "note_added",
        actor_id=actor_id,
        actor_role=str(user.get("role") or "admin"),
        at=now,
        changes={},
        note=_clean_note(body.note),
        student_id=str(existing["student_id"]),
        privacy_generation=int(existing["privacy_generation"]),
    )
    moderation_repo.update_case(case_id, {"updated_at": now})
    moderation_repo.put_event(case_id, event)
    updated = dict(existing)
    updated["updated_at"] = now
    updated["history"] = moderation_repo.list_case_events(case_id) or [event]
    notification_service.emit_moderation_update(
        case_item=updated,
        actor_id=actor_id,
        actor_role=str(user.get("role") or "admin"),
        owner_id=str(existing["student_id"]),
        privacy_generation=int(existing["privacy_generation"]),
    )
    return updated


def _require_report_access(question: dict[str, Any], user: dict[str, Any]) -> None:
    role = user.get("role")
    if role == "student" and question.get("student_id") != user.get("sub"):
        raise HTTPException(status_code=403, detail="Not your question")
    if role == "teacher" and not _teacher_visible(question, str(user.get("sub") or "")):
        raise HTTPException(status_code=403, detail="Question is not visible to this teacher workflow")
    if role not in {"student", "teacher", "admin"}:
        raise HTTPException(status_code=403, detail="Role is not permitted to report content")


def _validate_surface(question: dict[str, Any], surface: str) -> None:
    if surface == ModerationSurface.IMAGE_UPLOAD.value:
        raise HTTPException(status_code=400, detail="Image cases are opened by moderation only")
    if surface == ModerationSurface.AI_ANSWER.value and not question.get("ai_response"):
        raise HTTPException(status_code=400, detail="Question has no AI answer to report")
    if surface == ModerationSurface.TEACHER_REPLY.value and not question.get("teacher_response"):
        raise HTTPException(status_code=400, detail="Question has no teacher reply to report")


def _teacher_visible(question: dict[str, Any], teacher_id: str) -> bool:
    if teacher_id and question.get("teacher_id") == teacher_id:
        return True
    return question.get("status") in {"escalated", "teacher_active", "resolved"}


def _question_context(question: dict[str, Any]) -> dict[str, Any]:
    ai_response = question.get("ai_response") or {}
    return {
        "question_id": question.get("question_id"),
        "student_id": question.get("student_id"),
        "subject": question.get("subject"),
        "status": question.get("status"),
        "content_preview": _preview(question.get("content")),
        "ai_answer_preview": _preview(ai_response.get("answer") if isinstance(ai_response, dict) else None),
        "teacher_response_preview": _preview(question.get("teacher_response")),
        "has_image": bool(question.get("image_s3_key") or question.get("has_image")),
    }


def _event(
    case_id: str,
    event_type: str,
    *,
    actor_id: str,
    actor_role: str,
    at: str,
    changes: dict[str, Any],
    note: str | None,
    student_id: str,
    privacy_generation: int,
) -> dict[str, Any]:
    return {
        "event_id": f"{at}#{uuid4().hex}",
        "case_id": case_id,
        "event_type": event_type,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "created_at": at,
        "changes": changes,
        "note": note,
        "student_id": student_id,
        "privacy_generation": privacy_generation,
    }


def _matches(item: dict[str, Any], key: str, expected: str | None) -> bool:
    return expected is None or item.get(key) == expected


def _within_dates(item: dict[str, Any], date_from: str | None, date_to: str | None) -> bool:
    created = str(item.get("created_at") or "")
    if date_from and created < date_from:
        return False
    if date_to and created > date_to:
        return False
    return True


def _clean_note(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _preview(value: object, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]
