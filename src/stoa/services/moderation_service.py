"""Content moderation case helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import moderation_repo, question_repo
from stoa.models.moderation import (
    ModerationCaseNoteRequest,
    ModerationCaseUpdateRequest,
    ModerationReportRequest,
    ModerationStatus,
    ModerationSurface,
)
from stoa.services import notification_service


TERMINAL_STATUSES = {
    ModerationStatus.ACTIONED.value,
    ModerationStatus.DISMISSED.value,
    ModerationStatus.CLOSED.value,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_case(question_id: str, body: ModerationReportRequest, user: dict[str, Any]) -> dict[str, Any]:
    question = question_repo.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    _require_report_access(question, user)
    _validate_surface(question, body.surface.value)

    created_at = now_iso()
    case_id = f"mod-{uuid4().hex}"
    item = {
        "entity_type": "moderation_case",
        "case_id": case_id,
        "status": ModerationStatus.OPEN.value,
        "reason": body.reason.value,
        "severity": body.severity.value,
        "surface": body.surface.value,
        "question_id": question_id,
        "student_id": question.get("student_id"),
        "reporter_id": str(user.get("sub") or user.get("username") or "unknown"),
        "reporter_role": str(user.get("role") or "unknown"),
        "assigned_admin_id": None,
        "report_note": _clean_note(body.note),
        "resolution_note": None,
        "created_at": created_at,
        "updated_at": created_at,
        "closed_at": None,
        "question_context": _question_context(question),
    }
    event = _event(
        case_id,
        "reported",
        actor_id=item["reporter_id"],
        actor_role=item["reporter_role"],
        at=created_at,
        changes={
            "surface": item["surface"],
            "reason": item["reason"],
            "severity": item["severity"],
        },
        note=item["report_note"],
    )
    item["history"] = [event]
    moderation_repo.put_case(item)
    moderation_repo.put_event(case_id, event)
    notification_service.emit_moderation_created(
        case_item=item,
        actor_id=item["reporter_id"],
        actor_role=item["reporter_role"],
    )
    return item


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
        if body.status.value in TERMINAL_STATUSES:
            updates["closed_at"] = existing.get("closed_at") or now
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
    )
    updated = moderation_repo.update_case(case_id, updates) or {**existing, **updates}
    moderation_repo.put_event(case_id, event)
    updated = dict(updated)
    updated["history"] = moderation_repo.list_case_events(case_id) or [event]
    notification_service.emit_moderation_update(
        case_item=updated,
        actor_id=actor_id,
        actor_role=str(user.get("role") or "admin"),
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
    )
    return updated


def _require_report_access(question: dict[str, Any], user: dict[str, Any]) -> None:
    role = user.get("role")
    if role == "student" and question.get("student_id") != user.get("sub"):
        raise HTTPException(status_code=403, detail="Not your question")
    if role in {"teacher", "tutor"} and not _teacher_visible(question, str(user.get("sub") or "")):
        raise HTTPException(status_code=403, detail="Question is not visible to this teacher workflow")
    if role not in {"student", "teacher", "tutor", "admin"}:
        raise HTTPException(status_code=403, detail="Role is not permitted to report content")


def _validate_surface(question: dict[str, Any], surface: str) -> None:
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
