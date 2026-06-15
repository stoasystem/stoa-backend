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
    "assignment_started",
    "assignment_completed",
    "assignment_skipped",
    "assignment_archived",
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
    metadata = _assignment_metadata(item, event="completed", correct=correct)
    _record_assignment_targets(item, signal_type="assignment_completed", metadata=metadata)


def record_assignment_started(item: dict[str, Any]) -> None:
    metadata = _assignment_metadata(item, event="started")
    _record_assignment_targets(item, signal_type="assignment_started", metadata=metadata)


def record_assignment_skipped(item: dict[str, Any]) -> None:
    metadata = _assignment_metadata(item, event="skipped")
    _record_assignment_targets(item, signal_type="assignment_skipped", metadata=metadata)


def record_assignment_archived(item: dict[str, Any]) -> None:
    metadata = _assignment_metadata(item, event="archived")
    _record_assignment_targets(item, signal_type="assignment_archived", metadata=metadata)


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


def warehouse_readiness() -> dict[str, Any]:
    rows = curriculum_analytics_repo.list_metrics(limit=1)
    has_metrics = bool(rows)
    return {
        "state": "api-ready" if has_metrics else "empty",
        "exportAllowed": True,
        "liveWarehouseConfigured": False,
        "schemaVersion": "stoa.curriculum_analytics.v1",
        "sources": _warehouse_sources(),
        "sourceSchemas": _warehouse_source_schemas(),
        "lastMetricAt": rows[0].get("updated_at") if has_metrics else None,
        "blockers": ["live_warehouse_not_configured"],
        "warnings": [] if has_metrics else ["no_aggregate_metrics_recorded"],
        "privacy": _analytics_privacy_contract(),
    }


def warehouse_export(
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
    items = [_warehouse_export_row(row) for row in rows[:limit]]
    return {
        "schemaVersion": "stoa.curriculum_analytics.v1",
        "sourceSchemas": _warehouse_source_schemas(),
        "items": items,
        "count": len(items),
        "filters": {
            "contentType": content_type,
            "subjectId": subject_id,
            "topicId": topic_id,
            "limit": limit,
        },
        "window": {
            "type": "latest_aggregate_metrics",
            "aggregation": "lifetime",
            "liveWarehouseRequired": False,
            "sampled": True,
        },
        "privacy": _analytics_privacy_contract(),
    }


def operator_dashboard(
    *,
    subject_id: str | None = None,
    topic_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    rows = curriculum_analytics_repo.list_metrics(subject_id=subject_id, topic_id=topic_id, limit=limit)
    metrics = [_metric_response(row) for row in rows]
    metrics.sort(key=lambda item: item["priorityScore"], reverse=True)
    summary = _dashboard_summary(metrics)
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "filters": {"subjectId": subject_id, "topicId": topic_id, "limit": limit},
        "sampleSize": len(metrics),
        "sampled": True,
        "summary": summary,
        "sequencingCoverage": {
            "assignmentStarts": summary["assignmentStarts"],
            "assignmentCompletions": summary["assignmentCompletions"],
            "assignmentSkips": summary["assignmentSkips"],
            "assignmentArchives": summary["assignmentArchives"],
        },
        "qualityHotspots": metrics[:5],
        "interventions": _dashboard_interventions(metrics),
        "emptyState": None if metrics else "No aggregate learning analytics have been recorded yet.",
        "privacy": _analytics_privacy_contract(),
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
    started = int(row.get("signal_assignment_started_count") or 0)
    archived = int(row.get("signal_assignment_archived_count") or 0)
    lesson_completed = int(row.get("signal_lesson_completed_count") or 0)
    assignment_completed = int(row.get("signal_assignment_completed_count") or 0)
    completed = lesson_completed + assignment_completed
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
        "assignmentStarts": started,
        "assignmentSkips": skipped,
        "assignmentArchives": archived,
        "assignmentCompletions": assignment_completed,
        "lessonCompletions": lesson_completed,
        "completions": completed,
        "publishEvents": publish_events,
        "archiveEvents": archive_events,
        "priorityScore": priority,
        "updatedAt": row.get("updated_at"),
    }


def _warehouse_export_row(row: dict[str, Any]) -> dict[str, Any]:
    metric = _metric_response(row)
    return {
        "metricId": f"{metric['contentType']}:{metric['publicId']}:{metric['versionId']}",
        "schemaVersion": "stoa.curriculum_analytics.v1",
        "publicId": metric["publicId"],
        "contentType": metric["contentType"],
        "versionId": metric["versionId"],
        "subjectId": metric["subjectId"],
        "topicId": metric["topicId"],
        "metrics": {
            "totalSignals": metric["totalSignals"],
            "wrongAnswers": metric["wrongAnswers"],
            "assignmentStarts": metric["assignmentStarts"],
            "assignmentSkips": metric["assignmentSkips"],
            "assignmentArchives": metric["assignmentArchives"],
            "assignmentCompletions": metric["assignmentCompletions"],
            "lessonCompletions": metric["lessonCompletions"],
            "completions": metric["completions"],
            "publishEvents": metric["publishEvents"],
            "archiveEvents": metric["archiveEvents"],
            "priorityScore": metric["priorityScore"],
        },
        "aggregationWindow": "lifetime",
        "updatedAt": metric["updatedAt"],
    }


def _dashboard_summary(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contentItems": len(metrics),
        "totalSignals": sum(item["totalSignals"] for item in metrics),
        "wrongAnswers": sum(item["wrongAnswers"] for item in metrics),
        "assignmentStarts": sum(item["assignmentStarts"] for item in metrics),
        "assignmentSkips": sum(item["assignmentSkips"] for item in metrics),
        "assignmentArchives": sum(item["assignmentArchives"] for item in metrics),
        "assignmentCompletions": sum(item["assignmentCompletions"] for item in metrics),
        "lessonCompletions": sum(item["lessonCompletions"] for item in metrics),
        "completions": sum(item["completions"] for item in metrics),
        "qualityHotspots": sum(1 for item in metrics if item["priorityScore"] > 0),
    }


def _dashboard_interventions(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interventions = []
    for item in metrics:
        if item["priorityScore"] <= 0:
            continue
        reasons = []
        if item["wrongAnswers"]:
            reasons.append("wrong_answers")
        if item["assignmentSkips"]:
            reasons.append("assignment_skips")
        if item["assignmentArchives"]:
            reasons.append("assignment_archives")
        interventions.append(
            {
                "publicId": item["publicId"],
                "contentType": item["contentType"],
                "subjectId": item["subjectId"],
                "topicId": item["topicId"],
                "priorityScore": item["priorityScore"],
                "reasons": reasons,
            }
        )
    return interventions[:5]


def _warehouse_sources() -> list[dict[str, Any]]:
    return [
        {"name": "learning_memory", "state": "schema-ready"},
        {"name": "assignment_outcomes", "state": "schema-ready"},
        {"name": "curriculum_progress", "state": "schema-ready"},
        {"name": "content_quality_metrics", "state": "export-ready"},
        {"name": "operator_interventions", "state": "schema-ready"},
        {"name": "warehouse", "state": "not_configured"},
    ]


def _warehouse_source_schemas() -> dict[str, dict[str, Any]]:
    return {
        "learning_memory": {
            "rowState": "schema-only",
            "fields": ["studentHash", "subjectId", "topicId", "freshnessStatus", "lastEvidenceAt"],
        },
        "assignment_outcomes": {
            "rowState": "schema-only",
            "fields": ["assignmentHash", "sourceType", "subjectId", "topicIds", "event", "correct", "attemptCount"],
        },
        "curriculum_progress": {
            "rowState": "schema-only",
            "fields": ["studentHash", "subjectId", "topicId", "lessonId", "status", "completedAt"],
        },
        "content_quality_metrics": {
            "rowState": "exported",
            "fields": ["metricId", "publicId", "contentType", "versionId", "subjectId", "topicId", "metrics"],
        },
        "operator_interventions": {
            "rowState": "derived",
            "fields": ["publicId", "contentType", "subjectId", "topicId", "priorityScore", "reasons"],
        },
    }


def _analytics_privacy_contract() -> dict[str, bool]:
    return {
        "aggregateOnly": True,
        "rawStudentAnswers": False,
        "answerKeys": False,
        "studentIdentifiers": False,
    }


def _source_type(item: dict[str, Any]) -> str:
    raw = str(item.get("source_type") or "")
    if raw == "ai_draft":
        return "ai_draft_assignment"
    if raw == "curriculum_exercise":
        return "reviewed_assignment"
    return raw or "reviewed_assignment"


def _record_assignment_targets(
    item: dict[str, Any],
    *,
    signal_type: str,
    metadata: dict[str, Any],
) -> None:
    for target in _assignment_targets(item):
        _safe_record(
            signal_type=signal_type,
            public_id=target["public_id"],
            content_type=target["content_type"],
            version_id=item.get("version_id"),
            subject_id=item.get("subject"),
            topic_id=_first_topic(item),
            source_type=_source_type(item),
            metadata=metadata,
        )


def _assignment_targets(item: dict[str, Any]) -> list[dict[str, str]]:
    targets = []
    if item.get("exercise_id"):
        targets.append({"public_id": str(item.get("exercise_id")), "content_type": "exercise"})
    if item.get("lesson_id"):
        targets.append({"public_id": str(item.get("lesson_id")), "content_type": "lesson"})
    if not targets and item.get("source_type") == "ai_draft" and item.get("source_id"):
        targets.append({"public_id": str(item.get("source_id")), "content_type": "ai_draft"})
    return targets


def _assignment_metadata(
    item: dict[str, Any],
    *,
    event: str,
    correct: bool | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "event": event,
        "studentHash": _stable_subject_hash(str(item.get("student_id") or "")),
        "sourceType": item.get("source_type"),
        "topicIds": [str(topic_id) for topic_id in item.get("topic_ids", [])],
    }
    if correct is not None:
        metadata["correct"] = correct
    return metadata


def _first_topic(item: dict[str, Any]) -> str:
    values = item.get("topic_ids") or []
    return str(values[0]) if values else ""


def _stable_subject_hash(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"student:{digest}"
