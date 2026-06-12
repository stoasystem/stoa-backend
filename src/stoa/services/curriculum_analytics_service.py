"""Bounded curriculum quality analytics service."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from stoa.db.repositories import curriculum_analytics_repo


QUALITY_SIGNALS = {
    "practice_attempt",
    "wrong_answer",
    "lesson_completed",
    "assignment_completed",
    "assignment_skipped",
    "publish",
    "archive",
    "adaptive_memory_refresh",
}


def record_practice_attempt(
    *,
    student_id: str,
    challenge: dict[str, Any],
    correct: bool,
) -> None:
    metadata = {"correct": correct, "studentHash": _stable_subject_hash(student_id)}
    _safe_record(
        signal_type="practice_attempt",
        public_id=str(challenge.get("challenge_id") or ""),
        content_type="exercise",
        version_id=challenge.get("version_id"),
        subject_id=challenge.get("subject_id"),
        topic_id=challenge.get("topic_id"),
        source_type="catalog_self_practice",
        metadata=metadata,
    )
    if not correct:
        _safe_record(
            signal_type="wrong_answer",
            public_id=str(challenge.get("challenge_id") or ""),
            content_type="exercise",
            version_id=challenge.get("version_id"),
            subject_id=challenge.get("subject_id"),
            topic_id=challenge.get("topic_id"),
            source_type="catalog_self_practice",
            metadata=metadata,
        )


def record_lesson_completed(*, student_id: str, lesson: dict[str, Any]) -> None:
    _safe_record(
        signal_type="lesson_completed",
        public_id=str(lesson.get("lesson_id") or ""),
        content_type="lesson",
        version_id=lesson.get("version_id"),
        subject_id=lesson.get("subject_id"),
        topic_id=lesson.get("topic_id"),
        source_type="lesson_completion",
        metadata={"studentHash": _stable_subject_hash(student_id)},
    )


def record_assignment_outcome(item: dict[str, Any], *, correct: bool | None) -> None:
    signal_type = "assignment_completed"
    source_type = _source_type(item)
    metadata = {"correct": correct, "studentHash": _stable_subject_hash(str(item.get("student_id") or ""))}
    if item.get("exercise_id"):
        _safe_record(
            signal_type=signal_type,
            public_id=str(item.get("exercise_id")),
            content_type="exercise",
            version_id=item.get("version_id"),
            subject_id=item.get("subject"),
            topic_id=_first_topic(item),
            source_type=source_type,
            metadata=metadata,
        )
    if item.get("lesson_id"):
        _safe_record(
            signal_type=signal_type,
            public_id=str(item.get("lesson_id")),
            content_type="lesson",
            version_id=item.get("version_id"),
            subject_id=item.get("subject"),
            topic_id=_first_topic(item),
            source_type=source_type,
            metadata=metadata,
        )


def record_assignment_skipped(item: dict[str, Any]) -> None:
    source_type = _source_type(item)
    metadata = {"studentHash": _stable_subject_hash(str(item.get("student_id") or ""))}
    public_id = item.get("exercise_id") or item.get("lesson_id")
    content_type = "exercise" if item.get("exercise_id") else "lesson"
    if public_id:
        _safe_record(
            signal_type="assignment_skipped",
            public_id=str(public_id),
            content_type=content_type,
            version_id=item.get("version_id"),
            subject_id=item.get("subject"),
            topic_id=_first_topic(item),
            source_type=source_type,
            metadata=metadata,
        )


def record_publish_event(version: dict[str, Any], *, operation: str) -> None:
    lesson = version.get("lesson") or {}
    _safe_record(
        signal_type=operation,
        public_id=str(version.get("public_id") or ""),
        content_type="lesson",
        version_id=version.get("version_id"),
        subject_id=lesson.get("subject_id"),
        topic_id=lesson.get("topic_id"),
        source_type="curriculum_authoring",
        metadata={"operation": operation},
    )


def content_quality_summary(
    *,
    content_type: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    rows = curriculum_analytics_repo.list_metrics(
        content_type=content_type,
        subject_id=subject_id,
        topic_id=topic_id,
        limit=limit,
    )
    items = [_metric_response(row) for row in rows]
    items.sort(key=lambda item: item["priorityScore"], reverse=True)
    return {
        "items": items[:limit],
        "count": min(len(items), limit),
        "privacy": {
            "aggregateOnly": True,
            "rawStudentAnswers": False,
            "answerKeys": False,
            "studentIdentifiers": False,
        },
    }


def _safe_record(
    *,
    signal_type: str,
    public_id: str,
    content_type: str,
    version_id: Any = None,
    subject_id: Any = None,
    topic_id: Any = None,
    source_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not public_id or signal_type not in QUALITY_SIGNALS:
        return
    item = {
        "signal_id": f"signal_{uuid4().hex}",
        "signal_type": signal_type,
        "public_id": public_id,
        "content_type": content_type,
        "version_id": str(version_id or "unknown"),
        "subject_id": str(subject_id or ""),
        "topic_id": str(topic_id or ""),
        "source_type": source_type,
        "metadata": metadata or {},
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        curriculum_analytics_repo.put_signal(item)
        curriculum_analytics_repo.increment_metric(item)
    except Exception:  # noqa: BLE001
        return


def _metric_response(row: dict[str, Any]) -> dict[str, Any]:
    wrong = int(row.get("signal_wrong_answer_count") or 0)
    skipped = int(row.get("signal_assignment_skipped_count") or 0)
    completed = int(row.get("signal_lesson_completed_count") or 0) + int(
        row.get("signal_assignment_completed_count") or 0
    )
    publish_events = int(row.get("signal_publish_count") or 0)
    archive_events = int(row.get("signal_archive_count") or 0)
    priority = wrong * 3 + skipped * 2 + publish_events + archive_events - completed
    return {
        "publicId": row.get("public_id"),
        "contentType": row.get("content_type"),
        "versionId": row.get("version_id"),
        "subjectId": row.get("subject_id"),
        "topicId": row.get("topic_id"),
        "totalSignals": int(row.get("total_count") or 0),
        "wrongAnswers": wrong,
        "assignmentSkips": skipped,
        "completions": completed,
        "publishEvents": publish_events,
        "archiveEvents": archive_events,
        "priorityScore": priority,
        "updatedAt": row.get("updated_at"),
    }


def _source_type(item: dict[str, Any]) -> str:
    raw = str(item.get("source_type") or "")
    if raw == "ai_draft":
        return "ai_draft_assignment"
    if raw == "curriculum_exercise":
        return "reviewed_assignment"
    return raw or "reviewed_assignment"


def _first_topic(item: dict[str, Any]) -> str:
    values = item.get("topic_ids") or []
    return str(values[0]) if values else ""


def _stable_subject_hash(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"student:{digest}"
