"""Backend-mediated report artifact edit preview/apply workflow."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Any
from uuid import uuid4

from stoa.db.repositories import report_repo
from stoa.services import report_artifact_service, report_recovery_service

MAX_TEXT_LENGTHS = {
    "title": 200,
    "summary": 2000,
    "teacherNote": 1200,
}
MAX_LIST_ITEMS = 10
MAX_LIST_TEXT_LENGTH = 400
EDITABLE_FIELDS = frozenset(
    {
        "title",
        "summary",
        "strengths",
        "highlights",
        "weakTopics",
        "concerns",
        "recommendations",
        "teacherNote",
    }
)


@dataclass(frozen=True)
class ReportArtifactEditError(Exception):
    status_code: int
    detail: str
    error_class: str | None = None


def create_artifact_edit_preview(
    report: dict,
    *,
    operator: str,
    reason: str,
    proposed_fields: dict[str, Any],
    source: str = "admin_api",
    correlation_id: str | None = None,
) -> dict:
    fields = _validate_proposed_fields(proposed_fields)
    source_json_key = _required_artifact_key(report, "json_s3_key")
    source_html_key = _required_artifact_key(report, "html_s3_key", fallback_key="s3_key")
    current_artifact = _read_current_artifact(source_json_key)
    content = _content_from_artifact(current_artifact)
    diff = _build_diff(content, fields)
    event_at = _now_iso()
    source_version_id = _current_artifact_version_id(report)
    draft = {
        "draft_id": uuid4().hex,
        "report_id": report["report_id"],
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "week_start": report.get("week_start"),
        "source_updated_at": report.get("updated_at"),
        "source_artifact_version_id": source_version_id,
        "source_json_s3_key": source_json_key,
        "source_html_s3_key": source_html_key,
        "created_by": operator,
        "created_at": event_at,
        "updated_at": event_at,
        "reason": _safe_text(reason, max_length=500),
        "proposed_fields": fields,
        "diff": diff,
        "status": "draft",
    }
    report_repo.put_report_artifact_edit_draft(report["report_id"], draft)
    _write_artifact_edit_audit(
        report,
        action="create_report_artifact_edit_preview",
        actor=operator,
        reason=reason,
        source=source,
        result="draft",
        before=_metadata_snapshot(report),
        after={
            "draft_id": draft["draft_id"],
            "status": "draft",
            "source_artifact_version_id": source_version_id,
            "validation_result": "passed",
            "changed_fields": [item["field"] for item in diff if item["changed"]],
        },
        event_at=event_at,
        correlation_id=correlation_id,
    )
    return sanitize_artifact_edit_preview(draft)


def get_artifact_edit_preview(report: dict, draft_id: str) -> dict:
    draft = report_repo.get_report_artifact_edit_draft(report["report_id"], draft_id)
    if not draft:
        raise ReportArtifactEditError(status_code=404, detail="Report artifact edit preview not found")
    _assert_draft_matches_report(report, draft)
    return sanitize_artifact_edit_preview(draft)


def apply_artifact_edit_preview(
    report: dict,
    *,
    draft_id: str,
    operator: str,
    reason: str,
    source: str = "admin_api",
    correlation_id: str | None = None,
    s3_client: Any | None = None,
) -> dict:
    draft = report_repo.get_report_artifact_edit_draft(report["report_id"], draft_id)
    if not draft:
        raise ReportArtifactEditError(status_code=404, detail="Report artifact edit preview not found")
    _assert_draft_matches_report(report, draft)
    if draft.get("status") != "draft":
        raise ReportArtifactEditError(status_code=409, detail="Report artifact edit preview is not applyable")
    _assert_not_stale(report, draft, operator, source, correlation_id)

    source_json_key = str(draft.get("source_json_s3_key") or "")
    current_artifact = _read_current_artifact(source_json_key, s3_client=s3_client)
    next_artifact = _apply_fields_to_artifact(
        current_artifact,
        _validate_proposed_fields(draft.get("proposed_fields") or {}),
    )
    version_id = _new_version_id()
    version_keys = report_artifact_service.build_report_artifact_version_keys(
        str(report.get("parent_id") or ""),
        str(report.get("student_id") or ""),
        str(report.get("week_start") or ""),
        version_id,
    )
    html_artifact = _render_html_from_artifact(next_artifact)
    applied_at = _now_iso()
    report_artifact_service.write_report_artifacts(
        version_keys,
        next_artifact,
        html_artifact,
        s3_client=s3_client,
    )

    previous_version_id = _current_artifact_version_id(report)
    update_fields = {
        "artifact_version_id": version_id,
        "artifact_version_created_at": applied_at,
        "artifact_version_created_by": operator,
        "json_s3_key": version_keys.json_key,
        "html_s3_key": version_keys.html_key,
        "s3_key": version_keys.html_key,
        "previous_artifact_version_id": previous_version_id,
        "previous_json_s3_key": draft.get("source_json_s3_key"),
        "previous_html_s3_key": draft.get("source_html_s3_key"),
        "last_operation": "edit_report_artifact",
        "last_operation_at": applied_at,
        "last_operation_by": operator,
        "last_operation_result": "success",
        "updated_at": applied_at,
    }
    current_status = str(report.get("status") or "generated")
    if not report_repo.try_apply_report_artifact_edit(
        report["report_id"],
        expected_updated_at=report.get("updated_at"),
        expected_artifact_version_id=report.get("artifact_version_id"),
        expected_json_s3_key=draft.get("source_json_s3_key"),
        expected_html_s3_key=draft.get("source_html_s3_key"),
        status=current_status,
        fields=update_fields,
    ):
        _delete_versioned_artifacts(version_keys, s3_client=s3_client)
        _write_refused_apply(
            report,
            draft,
            operator,
            source,
            "Report artifact changed after preview creation",
            correlation_id,
        )
        raise ReportArtifactEditError(
            status_code=409,
            detail="Report artifact changed after preview creation",
        )
    if not report_repo.mark_report_artifact_edit_draft_applied(
        report["report_id"],
        draft_id,
        applied_at=applied_at,
        applied_by=operator,
        artifact_version_id=version_id,
    ):
        raise ReportArtifactEditError(
            status_code=409,
            detail="Report artifact edit preview is not applyable",
        )

    before = _metadata_snapshot(report)
    after = {
        **before,
        "status": current_status,
        **update_fields,
        "draft_id": draft_id,
        "validation_result": "passed",
        "source_artifact_version_id": previous_version_id,
        "new_artifact_version_id": version_id,
    }
    _write_artifact_edit_audit(
        report,
        action="apply_report_artifact_edit",
        actor=operator,
        reason=reason,
        source=source,
        result="success",
        before=before,
        after=after,
        event_at=applied_at,
        correlation_id=correlation_id,
    )
    applied_draft = {
        **draft,
        "status": "applied",
        "applied_at": applied_at,
        "applied_by": operator,
        "artifact_version_id": version_id,
        "updated_at": applied_at,
    }
    return {
        "draft": sanitize_artifact_edit_preview(applied_draft),
        "report": sanitize_artifact_edit_result(after),
    }


def sanitize_artifact_edit_preview(draft: dict) -> dict:
    return {
        "draft_id": str(draft.get("draft_id") or ""),
        "report_id": str(draft.get("report_id") or ""),
        "parent_id": draft.get("parent_id"),
        "student_id": draft.get("student_id"),
        "week_start": draft.get("week_start"),
        "source_updated_at": draft.get("source_updated_at"),
        "source_artifact_version_id": draft.get("source_artifact_version_id"),
        "created_by": draft.get("created_by"),
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
        "reason": report_recovery_service.redact_private_artifact_text(draft.get("reason")),
        "proposed_fields": _validate_proposed_fields(draft.get("proposed_fields") or {}),
        "diff": _sanitize_diff(draft.get("diff")),
        "status": str(draft.get("status") or ""),
        "applied_by": draft.get("applied_by"),
        "applied_at": draft.get("applied_at"),
        "artifact_version_id": draft.get("artifact_version_id"),
    }


def sanitize_artifact_edit_result(report: dict) -> dict:
    return {
        "report_id": report.get("report_id"),
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "week_start": report.get("week_start"),
        "status": report.get("status"),
        "artifact_version_id": report.get("artifact_version_id"),
        "artifact_version_created_at": report.get("artifact_version_created_at"),
        "artifact_version_created_by": report.get("artifact_version_created_by"),
        "previous_artifact_version_id": report.get("previous_artifact_version_id"),
        "last_operation": report.get("last_operation"),
        "last_operation_at": report.get("last_operation_at"),
        "last_operation_by": report.get("last_operation_by"),
        "last_operation_result": report.get("last_operation_result"),
        "updated_at": report.get("updated_at"),
    }


def _validate_proposed_fields(proposed_fields: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proposed_fields, dict) or not proposed_fields:
        raise ReportArtifactEditError(status_code=422, detail="At least one editable field is required")
    fields: dict[str, Any] = {}
    for key, raw_value in proposed_fields.items():
        if key not in EDITABLE_FIELDS:
            raise ReportArtifactEditError(status_code=422, detail=f"Field is not editable: {key}")
        if key in {"title", "summary", "teacherNote"}:
            fields[key] = _optional_safe_text(raw_value, field_name=key, max_length=MAX_TEXT_LENGTHS[key])
        elif key in {"strengths", "highlights", "recommendations", "concerns"}:
            fields[key] = _safe_text_list(raw_value, field_name=key)
        elif key == "weakTopics":
            fields[key] = _safe_weak_topics(raw_value)
    return fields


def _optional_safe_text(raw_value: Any, *, field_name: str, max_length: int) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ReportArtifactEditError(status_code=422, detail=f"Field must be a string: {field_name}")
    if _contains_private_marker(raw_value):
        raise ReportArtifactEditError(status_code=422, detail="Proposed edit contains private artifact marker")
    return _safe_text(raw_value, max_length=max_length)


def _safe_text_list(raw_value: Any, *, field_name: str) -> list[str]:
    if not isinstance(raw_value, list):
        raise ReportArtifactEditError(status_code=422, detail=f"Field must be a list: {field_name}")
    if len(raw_value) > MAX_LIST_ITEMS:
        raise ReportArtifactEditError(status_code=422, detail=f"Field has too many items: {field_name}")
    items = []
    for item in raw_value:
        if not isinstance(item, str):
            raise ReportArtifactEditError(status_code=422, detail=f"Field items must be strings: {field_name}")
        if _contains_private_marker(item):
            raise ReportArtifactEditError(status_code=422, detail="Proposed edit contains private artifact marker")
        items.append(_safe_text(item, max_length=MAX_LIST_TEXT_LENGTH))
    return items


def _safe_weak_topics(raw_value: Any) -> list[dict[str, str]]:
    if not isinstance(raw_value, list):
        raise ReportArtifactEditError(status_code=422, detail="Field must be a list: weakTopics")
    if len(raw_value) > MAX_LIST_ITEMS:
        raise ReportArtifactEditError(status_code=422, detail="Field has too many items: weakTopics")
    topics = []
    for item in raw_value:
        if not isinstance(item, dict):
            raise ReportArtifactEditError(status_code=422, detail="weakTopics items must be objects")
        topic = _optional_safe_text(item.get("topic"), field_name="weakTopics.topic", max_length=100)
        note = _optional_safe_text(item.get("note"), field_name="weakTopics.note", max_length=400)
        if not topic:
            raise ReportArtifactEditError(status_code=422, detail="weakTopics topic is required")
        topics.append({"topic": topic, "note": note or ""})
    return topics


def _build_diff(content: dict[str, Any], fields: dict[str, Any]) -> list[dict[str, Any]]:
    diff = []
    for requested_field, after_value in fields.items():
        field = _canonical_content_field(requested_field)
        before_value = _field_value_for_diff(content, field)
        normalized_after = _field_value_for_diff({_canonical_content_field(requested_field): after_value}, field)
        diff.append(
            {
                "field": field,
                "before": before_value,
                "after": normalized_after,
                "changed": before_value != normalized_after,
            }
        )
    return diff


def _sanitize_diff(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sanitized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "field": str(item.get("field") or ""),
                "before": _sanitize_preview_value(item.get("before")),
                "after": _sanitize_preview_value(item.get("after")),
                "changed": bool(item.get("changed")),
            }
        )
    return sanitized


def _sanitize_preview_value(value: Any) -> Any:
    if isinstance(value, str):
        return report_recovery_service.redact_private_artifact_text(value)
    if isinstance(value, list):
        return [_sanitize_preview_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_preview_value(raw) for key, raw in value.items()}
    return value


def _field_value_for_diff(content: dict[str, Any], field: str) -> Any:
    value = content.get(field)
    if value is None:
        return None
    return _sanitize_preview_value(value)


def _apply_fields_to_artifact(artifact: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    next_artifact = deepcopy(artifact)
    content = _content_from_artifact(next_artifact)
    for requested_field, value in fields.items():
        field = _canonical_content_field(requested_field)
        if requested_field == "concerns":
            content[field] = [{"topic": "Concern", "note": item} for item in value]
        else:
            content[field] = value
    next_artifact["content"] = content
    return next_artifact


def _content_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    content = artifact.get("content")
    if not isinstance(content, dict):
        raise ReportArtifactEditError(status_code=422, detail="Report artifact content is not editable")
    return content


def _canonical_content_field(field: str) -> str:
    if field == "highlights":
        return "strengths"
    if field == "concerns":
        return "weakTopics"
    return field


def _render_html_from_artifact(artifact: dict[str, Any]) -> str:
    report = artifact.get("report") if isinstance(artifact.get("report"), dict) else {}
    content = _content_from_artifact(artifact)
    student_name = str(report.get("studentName") or "Student")
    week_start = str(report.get("weekStart") or "")
    week_end = str(report.get("weekEnd") or "")
    title = str(content.get("title") or f"Weekly report for {student_name}")
    summary = str(content.get("summary") or "")
    recommendations = content.get("recommendations") if isinstance(content.get("recommendations"), list) else []
    weak_topics = content.get("weakTopics") if isinstance(content.get("weakTopics"), list) else []
    strengths = content.get("strengths") if isinstance(content.get("strengths"), list) else []
    recommendation_items = "".join(f"<li>{escape(str(item))}</li>" for item in recommendations)
    strength_items = "".join(f"<li>{escape(str(item))}</li>" for item in strengths)
    weak_topic_items = "".join(
        f"<li><strong>{escape(str(topic.get('topic', '')))}</strong>: "
        f"{escape(str(topic.get('note', '')))}</li>"
        for topic in weak_topics
        if isinstance(topic, dict)
    )
    teacher_note = content.get("teacherNote")
    teacher_note_html = f"<p><strong>Teacher note:</strong> {escape(str(teacher_note))}</p>" if teacher_note else ""
    week_label = f"{week_start} to {week_end}" if week_start and week_end else week_start
    return f"""<!doctype html>
<html>
  <body>
    <h1>{escape(title)}</h1>
    <p><strong>Week:</strong> {escape(week_label)}</p>
    <p>{escape(summary)}</p>
    <h2>Highlights</h2>
    <ul>{strength_items}</ul>
    <h2>Recommendations</h2>
    <ul>{recommendation_items}</ul>
    <h2>Weak topics</h2>
    <ul>{weak_topic_items}</ul>
    {teacher_note_html}
  </body>
</html>"""


def _read_current_artifact(s3_key: str, *, s3_client: Any | None = None) -> dict[str, Any]:
    try:
        return report_artifact_service.get_report_json(str(s3_key), s3_client=s3_client)
    except Exception as exc:
        raise ReportArtifactEditError(
            status_code=422,
            detail="Report JSON artifact is unavailable or invalid",
            error_class=type(exc).__name__,
        ) from exc


def _assert_draft_matches_report(report: dict, draft: dict) -> None:
    if (
        draft.get("report_id") != report.get("report_id")
        or draft.get("parent_id") != report.get("parent_id")
        or draft.get("student_id") != report.get("student_id")
        or draft.get("week_start") != report.get("week_start")
    ):
        raise ReportArtifactEditError(status_code=409, detail="Report artifact edit preview does not match report")


def _assert_not_stale(
    report: dict,
    draft: dict,
    operator: str,
    source: str,
    correlation_id: str | None,
) -> None:
    stale = (
        draft.get("source_updated_at") != report.get("updated_at")
        or draft.get("source_artifact_version_id") != _current_artifact_version_id(report)
        or draft.get("source_json_s3_key") != report.get("json_s3_key")
        or draft.get("source_html_s3_key") != (report.get("html_s3_key") or report.get("s3_key"))
    )
    if stale:
        _write_refused_apply(
            report,
            draft,
            operator,
            source,
            "Report artifact changed after preview creation",
            correlation_id,
        )
        raise ReportArtifactEditError(
            status_code=409,
            detail="Report artifact changed after preview creation",
        )


def _write_refused_apply(
    report: dict,
    draft: dict,
    operator: str,
    source: str,
    detail: str,
    correlation_id: str | None,
) -> None:
    event_at = _now_iso()
    before = _metadata_snapshot(report)
    _write_artifact_edit_audit(
        report,
        action="apply_report_artifact_edit",
        actor=operator,
        reason=str(draft.get("reason") or "admin_report_artifact_edit"),
        source=source,
        result="refused",
        before=before,
        after={
            "draft_id": draft.get("draft_id"),
            "validation_result": "failed",
            "refusal_reason": detail,
            "source_artifact_version_id": draft.get("source_artifact_version_id"),
            **before,
        },
        event_at=event_at,
        error_message=detail,
        correlation_id=correlation_id,
    )


def _write_artifact_edit_audit(
    report: dict,
    *,
    action: str,
    actor: str,
    reason: str,
    source: str,
    result: str,
    before: dict[str, Any],
    after: dict[str, Any],
    event_at: str,
    error_class: str | None = None,
    error_message: str | None = None,
    correlation_id: str | None = None,
) -> None:
    report_repo.put_report_audit_event(
        str(report["report_id"]),
        {
            "event_id": uuid4().hex,
            "event_at": event_at,
            "report_id": report.get("report_id"),
            "parent_id": report.get("parent_id"),
            "student_id": report.get("student_id"),
            "week_start": report.get("week_start"),
            "actor": actor,
            "action": action,
            "reason": _safe_text(reason, max_length=500),
            "source": source,
            "result": result,
            "before": _redacted_metadata(before),
            "after": _redacted_metadata(after),
            "error_class": error_class,
            "error_message": report_recovery_service.redact_private_artifact_text(error_message),
            "correlation_id": correlation_id,
        },
    )


def _metadata_snapshot(report: dict) -> dict[str, Any]:
    return {
        "report_id": report.get("report_id"),
        "parent_id": report.get("parent_id"),
        "student_id": report.get("student_id"),
        "week_start": report.get("week_start"),
        "status": report.get("status"),
        "email_status": report.get("email_status"),
        "artifact_version_id": report.get("artifact_version_id"),
        "artifact_version_created_at": report.get("artifact_version_created_at"),
        "artifact_version_created_by": report.get("artifact_version_created_by"),
        "previous_artifact_version_id": report.get("previous_artifact_version_id"),
        "json_s3_key": report.get("json_s3_key"),
        "html_s3_key": report.get("html_s3_key"),
        "s3_key": report.get("s3_key"),
        "last_operation": report.get("last_operation"),
        "last_operation_at": report.get("last_operation_at"),
        "last_operation_by": report.get("last_operation_by"),
        "last_operation_result": report.get("last_operation_result"),
        "updated_at": report.get("updated_at"),
    }


def _redacted_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report_recovery_service.redact_private_artifact_text(raw) if isinstance(raw, str) else raw
        for key, raw in value.items()
        if not key.endswith("_s3_key") and key != "s3_key"
    }


def _required_artifact_key(report: dict, key: str, *, fallback_key: str | None = None) -> str:
    value = report.get(key)
    if not value and fallback_key:
        value = report.get(fallback_key)
    if not value:
        raise ReportArtifactEditError(status_code=422, detail="Report artifact metadata is incomplete")
    return str(value)


def _current_artifact_version_id(report: dict) -> str | None:
    value = report.get("artifact_version_id")
    return str(value) if value else None


def _new_version_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"v{timestamp}-{uuid4().hex[:8]}"


def _delete_versioned_artifacts(
    keys: report_artifact_service.ReportArtifactKeys,
    *,
    s3_client: Any | None,
) -> None:
    try:
        report_artifact_service.delete_report_artifacts(keys, s3_client=s3_client)
    except Exception:
        pass


def _safe_text(value: object, *, max_length: int) -> str:
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    return text.strip()[:max_length]


def _contains_private_marker(value: str) -> bool:
    return any(
        token in value
        for token in (
            "weekly-reports/",
            "json_s3_key",
            "html_s3_key",
            "s3_key",
            "presignedUrl",
            "presigned_url",
            "X-Amz-",
            "https://s3",
            "<html",
            "access_token",
            "id_token",
            "refresh_token",
        )
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
