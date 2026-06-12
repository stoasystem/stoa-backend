"""Internal curriculum authoring workflow service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import curriculum_ops_repo
from stoa.services import curriculum_analytics_service


AUTHOR_ROLES = {"admin", "tutor", "teacher"}
PUBLISHER_ROLES = {"admin"}
REVIEWABLE_STATES = {"draft", "changes_requested"}
PUBLISHABLE_STATES = {"approved"}
ROLLBACK_STATES = {"approved", "published", "superseded", "archived"}


def list_worklist(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    items = [_version_response(item) for item in curriculum_ops_repo.list_worklist(status, limit)]
    return {"items": items, "count": len(items)}


def preview_lesson(public_id: str, version_id: str) -> dict[str, Any]:
    version = _existing_version(public_id, version_id)
    return _version_response(version, include_content=True)


def create_lesson_draft(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _require_role(user, AUTHOR_ROLES)
    public_id = _clean_id(payload.get("public_lesson_id") or payload.get("publicLessonId"))
    lesson = _lesson_payload(public_id, payload)
    exercises = _exercise_payloads(public_id, payload.get("exercises") or [])
    _validate_publish_ready(lesson, exercises, level="draft")

    now = _now()
    version_id = f"lessonv_{uuid4().hex}"
    version = {
        "public_id": public_id,
        "version_id": version_id,
        "content_type": "lesson_bundle",
        "state": "draft",
        "review_state": None,
        "lesson": lesson,
        "exercises": exercises,
        "created_by": _actor_id(user),
        "updated_by": _actor_id(user),
        "created_at": now,
        "updated_at": now,
    }
    curriculum_ops_repo.put_version(version)
    curriculum_ops_repo.put_pointer(
        {
            "public_id": public_id,
            "draft_version_id": version_id,
            "updated_by": _actor_id(user),
            "updated_at": now,
        }
    )
    _audit(public_id, user, "create_draft", None, "draft", version_id, None)
    return _version_response(version, include_content=True)


def submit_review(public_id: str, version_id: str, user: dict[str, Any]) -> dict[str, Any]:
    _require_role(user, AUTHOR_ROLES)
    version = _existing_version(public_id, version_id)
    _require_state(version, REVIEWABLE_STATES, "not_reviewable")
    _validate_publish_ready(version["lesson"], version.get("exercises") or [], level="review")
    updated = _with_state(version, "in_review", user, review_state="pending")
    curriculum_ops_repo.put_version(updated)
    _audit(public_id, user, "submit_review", version["state"], "in_review", version_id, None)
    return _version_response(updated, include_content=True)


def approve(public_id: str, version_id: str, user: dict[str, Any]) -> dict[str, Any]:
    _require_role(user, AUTHOR_ROLES)
    version = _existing_version(public_id, version_id)
    _require_state(version, {"in_review"}, "not_in_review")
    _validate_publish_ready(version["lesson"], version.get("exercises") or [], level="publish")
    updated = _with_state(version, "approved", user, review_state="approved")
    curriculum_ops_repo.put_version(updated)
    _audit(public_id, user, "approve", version["state"], "approved", version_id, None)
    return _version_response(updated, include_content=True)


def request_changes(
    public_id: str,
    version_id: str,
    user: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    _require_role(user, AUTHOR_ROLES)
    version = _existing_version(public_id, version_id)
    _require_state(version, {"in_review"}, "not_in_review")
    updated = _with_state(version, "changes_requested", user, review_state="changes_requested")
    updated["review_note"] = reason
    curriculum_ops_repo.put_version(updated)
    _audit(public_id, user, "request_changes", version["state"], "changes_requested", version_id, reason)
    return _version_response(updated, include_content=True)


def publish(
    public_id: str,
    version_id: str,
    user: dict[str, Any],
    *,
    expected_published_version_id: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    _require_role(user, PUBLISHER_ROLES)
    version = _existing_version(public_id, version_id)
    _require_state(version, PUBLISHABLE_STATES, "not_approved")
    _validate_publish_ready(version["lesson"], version.get("exercises") or [], level="publish")
    pointer = curriculum_ops_repo.get_pointer(public_id) or {}
    if pointer.get("published_version_id") == version_id:
        return {
            "status": "published",
            "idempotent": True,
            "manifest": {"manifestId": pointer.get("manifest_id")},
            "version": _version_response(version),
        }

    now = _now()
    manifest = _manifest(public_id, version, pointer, user, now, reason)
    curriculum_ops_repo.put_manifest(manifest)
    try:
        pointer = curriculum_ops_repo.set_published_pointer(
            public_id=public_id,
            version_id=version_id,
            manifest_id=manifest["manifest_id"],
            expected_published_version_id=expected_published_version_id,
            actor_id=_actor_id(user),
            updated_at=now,
        )
    except curriculum_ops_repo.StalePointerError as exc:
        _audit(public_id, user, "publish_refused", version["state"], version["state"], version_id, "stale_pointer")
        raise HTTPException(status_code=409, detail="stale_pointer") from exc

    curriculum_ops_repo.put_published_projection(version, manifest)
    updated = _with_state(version, "published", user)
    updated["published_at"] = now
    curriculum_ops_repo.put_version(updated)
    curriculum_analytics_service.record_publish_event(updated, operation="publish")
    _audit(public_id, user, "publish", version["state"], "published", version_id, reason)
    return {
        "status": "published",
        "idempotent": False,
        "manifest": _manifest_response(manifest),
        "pointer": _pointer_response(pointer),
        "version": _version_response(updated),
    }


def rollback(
    public_id: str,
    version_id: str,
    user: dict[str, Any],
    *,
    expected_published_version_id: str | None,
    reason: str,
) -> dict[str, Any]:
    _require_role(user, PUBLISHER_ROLES)
    version = _existing_version(public_id, version_id)
    _require_state(version, ROLLBACK_STATES, "rollback_target_not_publishable")
    pointer = curriculum_ops_repo.get_pointer(public_id) or {}
    now = _now()
    manifest = _manifest(public_id, version, pointer, user, now, reason, operation="rollback")
    curriculum_ops_repo.put_manifest(manifest)
    try:
        pointer = curriculum_ops_repo.set_published_pointer(
            public_id=public_id,
            version_id=version_id,
            manifest_id=manifest["manifest_id"],
            expected_published_version_id=expected_published_version_id,
            actor_id=_actor_id(user),
            updated_at=now,
        )
    except curriculum_ops_repo.StalePointerError as exc:
        raise HTTPException(status_code=409, detail="stale_pointer") from exc
    curriculum_ops_repo.put_published_projection(version, manifest)
    curriculum_analytics_service.record_publish_event(version, operation="publish")
    _audit(public_id, user, "rollback", pointer.get("published_version_id"), version_id, version_id, reason)
    return {
        "status": "rolled_back",
        "manifest": _manifest_response(manifest),
        "pointer": _pointer_response(pointer),
    }


def archive(public_id: str, version_id: str, user: dict[str, Any], *, reason: str) -> dict[str, Any]:
    _require_role(user, PUBLISHER_ROLES)
    version = _existing_version(public_id, version_id)
    refs = curriculum_ops_repo.list_active_assignment_refs(public_id)
    if refs:
        _audit(
            public_id,
            user,
            "archive_refused",
            version.get("state"),
            version.get("state"),
            version_id,
            "active_assignments_block_archive",
        )
        raise HTTPException(status_code=409, detail="active_assignments_block_archive")
    updated = _with_state(version, "archived", user)
    updated["archive_reason"] = reason
    curriculum_ops_repo.put_version(updated)
    curriculum_analytics_service.record_publish_event(updated, operation="archive")
    _audit(public_id, user, "archive", version.get("state"), "archived", version_id, reason)
    return _version_response(updated)


def _existing_version(public_id: str, version_id: str) -> dict[str, Any]:
    version = curriculum_ops_repo.get_version(public_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="curriculum_version_not_found")
    return version


def _lesson_payload(public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "lesson_id": public_id,
        "title": str(payload.get("title") or "").strip(),
        "objective": str(payload.get("objective") or payload.get("description") or "").strip(),
        "description": str(payload.get("description") or payload.get("objective") or "").strip(),
        "subject_id": _clean_id(payload.get("subject_id") or payload.get("subjectId")),
        "topic_id": _clean_id(payload.get("topic_id") or payload.get("topicId")),
        "unit_id": str(payload.get("unit_id") or payload.get("unitId") or "").strip(),
        "grade_level": str(payload.get("grade_level") or payload.get("gradeLevel") or "").strip(),
        "difficulty": str(payload.get("difficulty") or "practice").strip(),
        "estimated_minutes": int(payload.get("estimated_minutes") or payload.get("estimatedMinutes") or 10),
        "language": str(payload.get("language") or payload.get("locale") or "neutral").strip(),
    }


def _exercise_payloads(public_id: str, exercises: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, exercise in enumerate(exercises, start=1):
        exercise_id = _clean_id(
            exercise.get("exercise_id")
            or exercise.get("exerciseId")
            or exercise.get("challenge_id")
            or exercise.get("challengeId")
            or f"{public_id}-exercise-{index}"
        )
        answer_key = exercise.get("answer_key") or exercise.get("answerKey") or exercise.get("correct_answer")
        normalized.append(
            {
                "exercise_id": exercise_id,
                "challenge_id": exercise_id,
                "lesson_id": public_id,
                "prompt": str(exercise.get("prompt") or "").strip(),
                "type": str(exercise.get("type") or "text_input").strip(),
                "difficulty": str(exercise.get("difficulty") or "practice").strip(),
                "order": int(exercise.get("order") or index),
                "answer_key": str(answer_key or "").strip(),
                "explanation": str(exercise.get("explanation") or "").strip(),
                "skills": exercise.get("skills") or [],
            }
        )
    return normalized


def _validate_publish_ready(
    lesson: dict[str, Any],
    exercises: list[dict[str, Any]],
    *,
    level: str,
) -> None:
    missing = [
        key
        for key in ["lesson_id", "title", "objective", "subject_id", "topic_id", "grade_level"]
        if not lesson.get(key)
    ]
    if level in {"review", "publish"} and not exercises:
        missing.append("exercises")
    if level == "publish":
        for index, exercise in enumerate(exercises, start=1):
            for key in ["exercise_id", "prompt", "difficulty", "answer_key", "explanation"]:
                if not exercise.get(key):
                    missing.append(f"exercise[{index}].{key}")
    if missing:
        raise HTTPException(status_code=422, detail={"code": "validation_failed", "fields": missing})


def _with_state(
    version: dict[str, Any],
    state: str,
    user: dict[str, Any],
    *,
    review_state: str | None = None,
) -> dict[str, Any]:
    updated = dict(version)
    updated["state"] = state
    if review_state is not None:
        updated["review_state"] = review_state
    updated["updated_by"] = _actor_id(user)
    updated["updated_at"] = _now()
    return updated


def _require_state(version: dict[str, Any], allowed: set[str], detail: str) -> None:
    if version.get("state") not in allowed:
        raise HTTPException(status_code=409, detail=detail)


def _require_role(user: dict[str, Any], allowed: set[str]) -> None:
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="curriculum_authoring_forbidden")


def _manifest(
    public_id: str,
    version: dict[str, Any],
    pointer: dict[str, Any],
    user: dict[str, Any],
    now: str,
    reason: str | None,
    *,
    operation: str = "publish",
) -> dict[str, Any]:
    return {
        "manifest_id": f"manifest_{uuid4().hex}",
        "public_id": public_id,
        "operation": operation,
        "lesson_version_id": version["version_id"],
        "exercise_version_ids": [
            {
                "exercise_id": item["exercise_id"],
                "version_id": version["version_id"],
                "order": item["order"],
            }
            for item in version.get("exercises") or []
        ],
        "previous_published_version_id": pointer.get("published_version_id"),
        "created_by": _actor_id(user),
        "created_at": now,
        "reason": reason,
    }


def _audit(
    public_id: str,
    user: dict[str, Any],
    operation: str,
    from_state: str | None,
    to_state: str | None,
    version_id: str | None,
    reason: str | None,
) -> None:
    curriculum_ops_repo.append_audit_event(
        public_id,
        {
            "event_id": f"event_{uuid4().hex}",
            "public_id": public_id,
            "version_id": version_id,
            "operation": operation,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "actor_id": _actor_id(user),
            "actor_role": user.get("role"),
            "created_at": _now(),
        },
    )


def _version_response(version: dict[str, Any], *, include_content: bool = False) -> dict[str, Any]:
    response = {
        "publicLessonId": version.get("public_id"),
        "versionId": version.get("version_id"),
        "state": version.get("state"),
        "reviewState": version.get("review_state"),
        "updatedAt": version.get("updated_at"),
        "updatedBy": version.get("updated_by"),
    }
    if include_content:
        response["lesson"] = version.get("lesson") or {}
        response["exercises"] = version.get("exercises") or []
    return response


def _pointer_response(pointer: dict[str, Any]) -> dict[str, Any]:
    return {
        "publicLessonId": pointer.get("public_id"),
        "publishedVersionId": pointer.get("published_version_id"),
        "manifestId": pointer.get("manifest_id"),
        "updatedAt": pointer.get("updated_at"),
    }


def _manifest_response(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifestId": manifest.get("manifest_id"),
        "lessonVersionId": manifest.get("lesson_version_id"),
        "previousPublishedVersionId": manifest.get("previous_published_version_id"),
        "operation": manifest.get("operation"),
    }


def _actor_id(user: dict[str, Any]) -> str:
    return str(user.get("sub") or user.get("username") or "unknown")


def _clean_id(value: Any) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail={"code": "validation_failed", "fields": ["id"]})
    return cleaned


def _now() -> str:
    return datetime.now(UTC).isoformat()
