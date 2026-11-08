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

from stoa.config import Settings
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import moderation_repo
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
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.services import help_requests, learning_session, notification_service
from stoa.services.moderation_errors import ModerationErrorCode as _M, ModerationViolation
from stoa.services.account_errors import AccountErrorCode, AccountViolation


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
    request_id: str,
    body: ModerationReportRequest,
    user: dict[str, Any],
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Open a case on what was said in a help request (#185).

    ``request`` is the help request record as stored, which the report route
    has resolved and authorized; ``request_id`` is its id, which the case keeps
    as its `question_id`.
    """
    _require_report_access(request, user)
    _validate_surface(body.surface.value)
    reported = _reported_message(request, body.surface.value, body.message_id)

    student_id = request.get("student_id")
    privacy_generation = stored_int(request.get("account_fence_generation"))
    if (
        not isinstance(student_id, str)
        or not student_id
        or privacy_generation is None
        or privacy_generation <= 0
    ):
        raise ModerationViolation(_M.QUESTION_NOT_WRITABLE)

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
        "question_id": request_id,
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
        "question_context": _question_context(request, reported),
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
        raise ModerationViolation(_M.CASE_IMAGE_NOT_FOUND)
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
        raise ModerationViolation(_M.CASE_IMAGE_UNAVAILABLE) from None
    if len(data) != size or hashlib.sha256(data).hexdigest() != item.get("image_sha256"):
        logger.error("moderation_case_image_mismatch case_id=%s", case_id)
        raise ModerationViolation(_M.CASE_IMAGE_UNAVAILABLE)
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


@dataclass(frozen=True, slots=True)
class ModerationCasePage:
    items: list[dict[str, Any]]
    # Every case the filters admit, on this page and all the others.
    total: int
    next_cursor: str | None = None


def list_cases(
    *,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    reason: str | None = None,
    reporter_role: str | None = None,
    assignee: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> ModerationCasePage:
    """One page of the queue, newest first (#110).

    The repository reads every page of the table, past whatever rows that are
    not cases fill it, so the order and the total are the whole queue's. The
    cursor is the position of the last case handed out, not an offset: a case
    reported while the admin pages does not push one already seen onto the next
    page.
    """
    after = _case_cursor_position(cursor) if cursor else None
    matching = sorted(
        (
            item for item in moderation_repo.list_cases(limit=None)
            if _matches(item, "status", status)
            and _matches(item, "severity", severity)
            and _matches(item, "reason", reason)
            and _matches(item, "reporter_role", reporter_role)
            and _matches(item, "assigned_admin_id", assignee)
            and _within_dates(item, date_from, date_to)
        ),
        key=_case_position,
        reverse=True,
    )
    remaining = [item for item in matching if after is None or _case_position(item) < after]
    page = remaining[:limit]
    next_cursor = (
        _case_cursor(_case_position(page[-1])) if len(remaining) > limit else None
    )
    return ModerationCasePage(items=page, total=len(matching), next_cursor=next_cursor)


def _case_position(item: Mapping[str, Any]) -> tuple[str, str]:
    # The case id breaks ties between cases reported in the same instant.
    return (str(item.get("created_at") or ""), str(item.get("case_id") or ""))


CASE_CURSOR_SCOPE = "moderation_cases"


def _case_cursor(position: tuple[str, str]) -> str:
    created_at, case_id = position
    return db_table.page_token(CASE_CURSOR_SCOPE, {"created_at": created_at, "case_id": case_id})


def _case_cursor_position(cursor: str) -> tuple[str, str]:
    try:
        decoded = db_table.read_page_token(cursor, CASE_CURSOR_SCOPE)
    except db_table.PageTokenInvalid as exc:
        raise AccountViolation(AccountErrorCode.CURSOR_INVALID) from exc
    created_at, case_id = decoded.get("created_at"), decoded.get("case_id")
    if set(decoded) != {"created_at", "case_id"} or not (
        isinstance(created_at, str) and isinstance(case_id, str)
    ):
        raise AccountViolation(AccountErrorCode.CURSOR_INVALID)
    return (created_at, case_id)


def get_case(case_id: str, *, include_events: bool = True) -> dict[str, Any]:
    item = moderation_repo.get_case(case_id)
    if not item:
        raise ModerationViolation(_M.MODERATION_CASE_NOT_FOUND)
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


def _require_report_access(request: Mapping[str, Any], user: dict[str, Any]) -> None:
    role = user.get("role")
    if role == "student" and request.get("student_id") != user.get("sub"):
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    if role == "teacher" and not _teacher_holds(request, str(user.get("sub") or "")):
        # The teacher policy also admits a teacher assigned to the student, who
        # may read the request but not act on it (#73). Reporting is acting on
        # it, so they are refused as a teacher who cannot see it is (#186).
        raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
    if role not in {"student", "teacher", "admin"}:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)


def _validate_surface(surface: str) -> None:
    # A help request's answers are messages in its conversation (#185);
    # `_reported_message` finds the one reported.
    if surface == ModerationSurface.IMAGE_UPLOAD.value:
        raise ModerationViolation(_M.IMAGE_CASE_NOT_REPORTABLE)


def _teacher_holds(request: Mapping[str, Any], teacher_id: str) -> bool:
    """Whether the request is this teacher's: they took it, or it is offered to them now."""
    if not teacher_id:
        return False
    holder = request.get("teacher_id")
    if holder:
        return holder == teacher_id
    deadline = _aware(request.get("dispatch_deadline_at"))
    return (
        request.get("dispatched_teacher_id") == teacher_id
        and deadline is not None
        and deadline > datetime.now(timezone.utc)
    )


# Who wrote what each surface reports, in a help request's conversation.
_SURFACE_ROLES = {
    ModerationSurface.QUESTION.value: "student",
    ModerationSurface.AI_ANSWER.value: "assistant",
    ModerationSurface.TEACHER_REPLY.value: "teacher",
}


def _reported_message(
    request: Mapping[str, Any], surface: str, message_id: str | None
) -> learning_session.Message | None:
    """The conversation message a help request's report is about (#185).

    The message named, which must be one of the surface's author in this
    conversation; without a name, an AI answer or teacher reply report is about
    the latest one, and a report of the student's words is about the request.
    """
    role = _SURFACE_ROLES[surface]
    if not message_id and role == "student":
        return None
    said = [
        message
        for message in learning_session.history(str(request["conversation_id"]))
        if message.role == role
        and message.student_id == request.get("student_id")
        and message.content.strip()
    ]
    if message_id:
        named = [message for message in said if message.id == message_id]
        if not named:
            raise ModerationViolation(_M.REPORTED_MESSAGE_NOT_FOUND)
        return named[0]
    if not said:
        raise ModerationViolation(
            _M.NO_AI_ANSWER_TO_REPORT if role == "assistant" else _M.NO_TEACHER_REPLY_TO_REPORT
        )
    # Message ids are random, so the keys do not run in the order of sending.
    return max(said, key=lambda message: message.created_at)


def _question_context(
    request: Mapping[str, Any], reported: learning_session.Message | None = None
) -> dict[str, Any]:
    """What the admin queue shows of the request, in the case's question fields.

    The student's note is the request's words. Its answers are messages in the
    conversation, not on the record, and it keeps no image (#185).
    """
    context = {
        "question_id": str(request.get("escalation_request_id") or request.get("conversation_id")),
        "student_id": request.get("student_id"),
        "subject": request.get("subject"),
        "status": help_requests.stored_status(request),
        "content_preview": _preview(request.get("escalation_message") or ""),
        "ai_answer_preview": None,
        "teacher_response_preview": None,
        "has_image": False,
    }
    if reported is not None:
        # The reported message's words go where the admin queue shows that
        # surface's text.
        field = {
            "student": "content_preview",
            "assistant": "ai_answer_preview",
            "teacher": "teacher_response_preview",
        }[reported.role]
        context[field] = _preview(reported.content)
        context["reported_message_id"] = reported.id
    return context


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
