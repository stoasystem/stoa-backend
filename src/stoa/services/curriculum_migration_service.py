"""Manifest-driven curriculum content migration service."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import curriculum_ops_repo
from stoa.services import curriculum_analytics_service, curriculum_ops_service


def dry_run(manifest: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    _require_migration_access(user)
    normalized = _normalize_manifest(manifest)
    rows = [_analyze_row(row) for row in normalized["lessons"]]
    summary = _summary(rows)
    return {
        "migrationId": _migration_id(normalized),
        "confirmationToken": _confirmation_token(normalized),
        "source": normalized["source"],
        "operatorNote": normalized.get("operator_note"),
        "summary": summary,
        "rows": rows,
        "publishReady": summary["errors"] == 0 and summary["conflicts"] == 0,
    }


def apply_migration(
    migration_id: str,
    manifest: dict[str, Any],
    confirmation_token: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    _require_migration_access(user)
    normalized = _normalize_manifest(manifest)
    expected_id = _migration_id(normalized)
    expected_token = _confirmation_token(normalized)
    if migration_id != expected_id or confirmation_token != expected_token:
        raise HTTPException(status_code=409, detail="migration_confirmation_mismatch")

    existing = curriculum_ops_repo.get_migration_evidence(migration_id)
    manifest_hash = _manifest_hash(normalized)
    if existing and existing.get("manifest_hash") == manifest_hash and existing.get("status") == "applied":
        response = _evidence_response(existing)
        response["idempotent"] = True
        return response

    preview = dry_run(manifest, user)
    if not preview["publishReady"]:
        raise HTTPException(status_code=409, detail={"code": "migration_not_ready", "summary": preview["summary"]})

    now = _now()
    applied_rows = [_apply_row(row, user, now, migration_id) for row in preview["rows"]]
    evidence = {
        "migration_id": migration_id,
        "manifest_hash": manifest_hash,
        "status": "applied",
        "source": normalized["source"],
        "operator_note": normalized.get("operator_note"),
        "summary": _summary(applied_rows),
        "rows": applied_rows,
        "applied_by": _actor_id(user),
        "applied_at": now,
    }
    curriculum_ops_repo.put_migration_evidence(evidence)
    response = _evidence_response(evidence)
    response["idempotent"] = False
    return response


def get_migration(migration_id: str, user: dict[str, Any]) -> dict[str, Any]:
    _require_migration_access(user)
    evidence = curriculum_ops_repo.get_migration_evidence(migration_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="migration_not_found")
    return _evidence_response(evidence)


def _require_migration_access(user: dict[str, Any]) -> None:
    curriculum_ops_service._require_capability(  # noqa: SLF001
        user,
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY,
        curriculum_ops_service.PUBLISHER_CAPABILITY,
    )


def _normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    lessons = manifest.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise HTTPException(status_code=422, detail={"code": "invalid_manifest", "fields": ["lessons"]})

    source = manifest.get("source") or {}
    normalized = {
        "source": {
            "sourceId": str(source.get("sourceId") or source.get("source_id") or "manual").strip(),
            "sourceVersion": str(source.get("sourceVersion") or source.get("source_version") or "").strip(),
            "sourceType": str(source.get("sourceType") or source.get("source_type") or "manifest").strip(),
        },
        "operator_note": manifest.get("operatorNote") or manifest.get("operator_note"),
        "lessons": [_normalize_row(row, index) for index, row in enumerate(lessons, start=1)],
    }
    return normalized


def _normalize_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    public_id = _clean_id(row.get("publicLessonId") or row.get("public_lesson_id"))
    lesson_input = row.get("lesson") if isinstance(row.get("lesson"), dict) else row
    lesson = curriculum_ops_service._patch_lesson(public_id, {}, lesson_input)  # noqa: SLF001
    lesson.setdefault("subject_id", row.get("subjectId") or row.get("subject_id"))
    lesson.setdefault("topic_id", row.get("topicId") or row.get("topic_id"))
    lesson.setdefault("grade_level", row.get("gradeLevel") or row.get("grade_level"))
    lesson.setdefault("title", row.get("title"))
    lesson.setdefault("objective", row.get("objective") or row.get("description"))
    lesson.setdefault("description", row.get("description") or row.get("objective"))
    lesson["lesson_id"] = public_id

    exercises = curriculum_ops_service._exercise_payloads(  # noqa: SLF001
        public_id,
        row.get("exercises") or [],
    )
    publish_intent = bool(row.get("publish") or row.get("publishIntent") or row.get("publish_intent"))
    return {
        "rowIndex": index,
        "publicLessonId": public_id,
        "expectedPublishedVersionId": row.get("expectedPublishedVersionId")
        or row.get("expected_published_version_id"),
        "targetVersionId": row.get("targetVersionId") or row.get("target_version_id"),
        "publishIntent": publish_intent,
        "rollbackHint": row.get("rollbackHint") or row.get("rollback_hint"),
        "lesson": lesson,
        "exercises": exercises,
    }


def _analyze_row(row: dict[str, Any]) -> dict[str, Any]:
    pointer = curriculum_ops_repo.get_pointer(row["publicLessonId"]) or {}
    published_version_id = pointer.get("published_version_id")
    current_version = (
        curriculum_ops_repo.get_version(row["publicLessonId"], published_version_id)
        if published_version_id
        else None
    )
    target_version = (
        curriculum_ops_repo.get_version(row["publicLessonId"], row["targetVersionId"])
        if row.get("targetVersionId")
        else None
    )
    validation_issues = curriculum_ops_service._validation_issues(  # noqa: SLF001
        row["lesson"],
        row["exercises"],
        level="publish" if row["publishIntent"] else "review",
    )
    conflicts = []
    expected = row.get("expectedPublishedVersionId")
    if expected is not None and expected != published_version_id:
        conflicts.append(
            {
                "code": "published_pointer_mismatch",
                "expectedPublishedVersionId": expected,
                "actualPublishedVersionId": published_version_id,
            }
        )

    action = "create" if current_version is None else "update"
    if target_version and _content_equal(target_version, row):
        action = "skip"
    if validation_issues:
        action = "error"
    if conflicts:
        action = "conflict"

    return {
        "rowIndex": row["rowIndex"],
        "publicLessonId": row["publicLessonId"],
        "action": action,
        "publishIntent": row["publishIntent"],
        "expectedPublishedVersionId": expected,
        "currentPublishedVersionId": published_version_id,
        "targetVersionId": row.get("targetVersionId"),
        "validationIssues": validation_issues,
        "conflicts": conflicts,
        "rollbackHint": row.get("rollbackHint"),
        "lesson": row["lesson"],
        "exercises": row["exercises"],
    }


def _apply_row(row: dict[str, Any], user: dict[str, Any], now: str, migration_id: str) -> dict[str, Any]:
    if row["action"] == "skip":
        return {**_public_row(row), "status": "skipped"}

    version_id = _version_id(row, migration_id)
    version = {
        "public_id": row["publicLessonId"],
        "version_id": version_id,
        "content_type": "lesson_bundle",
        "state": "approved" if row["publishIntent"] else "draft",
        "review_state": "approved" if row["publishIntent"] else None,
        "lesson": row["lesson"],
        "exercises": row["exercises"],
        "created_by": _actor_id(user),
        "updated_by": _actor_id(user),
        "created_at": now,
        "updated_at": now,
        "migration_id": migration_id,
    }
    curriculum_ops_repo.put_version(version)
    _append_audit(row["publicLessonId"], user, "migration_apply", None, version["state"], version_id, migration_id)

    pointer = None
    manifest = None
    if row["publishIntent"]:
        manifest = _publish_manifest(row, version, user, now, migration_id)
        curriculum_ops_repo.put_manifest(manifest)
        try:
            pointer = curriculum_ops_repo.set_published_pointer(
                public_id=row["publicLessonId"],
                version_id=version_id,
                manifest_id=manifest["manifest_id"],
                expected_published_version_id=row.get("expectedPublishedVersionId"),
                actor_id=_actor_id(user),
                updated_at=now,
            )
        except curriculum_ops_repo.StalePointerError as exc:
            raise HTTPException(status_code=409, detail="stale_pointer") from exc
        published = {**version, "state": "published", "published_at": now}
        curriculum_ops_repo.put_published_projection(published, manifest)
        curriculum_ops_repo.put_version(published)
        curriculum_analytics_service.record_publish_event(published, operation="migration_publish")
        _append_audit(
            row["publicLessonId"],
            user,
            "migration_publish",
            "approved",
            "published",
            version_id,
            migration_id,
        )

    return {
        **_public_row(row),
        "status": "applied",
        "versionId": version_id,
        "pointer": _pointer_response(pointer) if pointer else None,
        "manifest": _manifest_response(manifest) if manifest else None,
        "rollback": {
            "previousPublishedVersionId": row.get("currentPublishedVersionId"),
            "newVersionId": version_id,
            "hint": row.get("rollbackHint"),
        },
    }


def _append_audit(
    public_id: str,
    user: dict[str, Any],
    operation: str,
    from_state: str | None,
    to_state: str | None,
    version_id: str,
    migration_id: str,
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
            "reason": migration_id,
            "actor_id": _actor_id(user),
            "actor_role": user.get("role"),
            "actor_capabilities": sorted(curriculum_ops_service.curriculum_capabilities(user)),
            "created_at": _now(),
        },
    )


def _publish_manifest(
    row: dict[str, Any],
    version: dict[str, Any],
    user: dict[str, Any],
    now: str,
    migration_id: str,
) -> dict[str, Any]:
    return {
        "manifest_id": f"manifest_{uuid4().hex}",
        "public_id": row["publicLessonId"],
        "operation": "migration_publish",
        "lesson_version_id": version["version_id"],
        "exercise_version_ids": [
            {
                "exercise_id": item["exercise_id"],
                "version_id": version["version_id"],
                "order": item["order"],
            }
            for item in version.get("exercises") or []
        ],
        "previous_published_version_id": row.get("currentPublishedVersionId"),
        "created_by": _actor_id(user),
        "created_at": now,
        "reason": migration_id,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(rows), "creates": 0, "updates": 0, "skips": 0, "conflicts": 0, "errors": 0}
    for row in rows:
        action = row.get("action") or row.get("status")
        if action == "create":
            counts["creates"] += 1
        elif action == "update":
            counts["updates"] += 1
        elif action in {"skip", "skipped"}:
            counts["skips"] += 1
        elif action == "conflict":
            counts["conflicts"] += 1
        elif action == "error":
            counts["errors"] += 1
    return counts


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rowIndex": row["rowIndex"],
        "publicLessonId": row["publicLessonId"],
        "action": row.get("action"),
        "publishIntent": row.get("publishIntent", False),
        "validationIssues": row.get("validationIssues") or [],
        "conflicts": row.get("conflicts") or [],
    }


def _evidence_response(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "migrationId": evidence.get("migration_id"),
        "status": evidence.get("status"),
        "source": evidence.get("source") or {},
        "operatorNote": evidence.get("operator_note"),
        "summary": evidence.get("summary") or {},
        "rows": evidence.get("rows") or [],
        "appliedBy": evidence.get("applied_by"),
        "appliedAt": evidence.get("applied_at"),
    }


def _content_equal(version: dict[str, Any], row: dict[str, Any]) -> bool:
    return (version.get("lesson") or {}) == row["lesson"] and (version.get("exercises") or []) == row["exercises"]


def _migration_id(manifest: dict[str, Any]) -> str:
    return f"migration_{_manifest_hash(manifest)[:16]}"


def _confirmation_token(manifest: dict[str, Any]) -> str:
    return f"confirm_{_manifest_hash(manifest)[16:32]}"


def _version_id(row: dict[str, Any], migration_id: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"migrationId": migration_id, "row": row["rowIndex"], "publicLessonId": row["publicLessonId"]},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"lessonv_mig_{digest[:20]}"


def _manifest_hash(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _pointer_response(pointer: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pointer:
        return None
    return {
        "publicLessonId": pointer.get("public_id"),
        "publishedVersionId": pointer.get("published_version_id"),
        "manifestId": pointer.get("manifest_id"),
        "updatedAt": pointer.get("updated_at"),
    }


def _manifest_response(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
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
        raise HTTPException(status_code=422, detail={"code": "invalid_manifest", "fields": ["publicLessonId"]})
    return cleaned


def _now() -> str:
    return datetime.now(UTC).isoformat()
