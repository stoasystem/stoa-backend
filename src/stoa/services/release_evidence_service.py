"""Release evidence validation and safe-fixture inventory helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from stoa.services import report_recovery_service


SCHEMA_VERSION = "v1"

REQUIRED_BUNDLE_FIELDS = (
    "schema_version",
    "milestone",
    "phase",
    "generated_at",
    "environment",
    "backend",
    "frontend",
    "infra",
    "api_checks",
    "browser_smoke",
    "privacy",
    "quality_gates",
)

VALID_STATUSES = {"passed", "failed", "skipped", "blocked"}

APPROVED_FIXTURES: dict[str, dict[str, str]] = {
    "stoa-safe-fixture-v2-2-rollback-2026-06-06": {
        "parent_id": "safe-fixture-parent-v2-2",
        "student_id": "safe-fixture-student-v2-2",
        "week_start": "2026-06-01",
        "expected_artifact_version_id": "original",
    }
}

PRIVATE_KEY_FRAGMENTS = (
    "s3_key",
    "presigned",
    "access_token",
    "accesstoken",
    "id_token",
    "refresh_token",
    "password",
    "cookie",
    "secret",
)

PRIVATE_TEXT_PATTERNS = (
    re.compile(r"weekly-reports/", re.IGNORECASE),
    re.compile(r"presignedUrl", re.IGNORECASE),
    re.compile(r"presigned_url", re.IGNORECASE),
    re.compile(r"https://s3", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"<html", re.IGNORECASE),
    re.compile(r"raw_json", re.IGNORECASE),
    re.compile(r"raw_html", re.IGNORECASE),
)

MUTATION_CLEANUP_MODES = {"cleanup", "restore", "cleanup_restore"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_release_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_BUNDLE_FIELDS if field not in bundle]
    status_errors = _status_errors(bundle)
    privacy_hits = private_marker_hits(bundle)
    fixture_errors = _fixture_errors(bundle.get("fixture"))
    schema_errors = []
    if bundle.get("schema_version") not in {None, SCHEMA_VERSION}:
        schema_errors.append(f"schema_version must be {SCHEMA_VERSION}")

    status = "passed"
    if missing or status_errors or privacy_hits or fixture_errors or schema_errors:
        status = "failed"

    return {
        "schema_version": SCHEMA_VERSION,
        "validated_at": now_iso(),
        "status": status,
        "missing_required_fields": missing,
        "schema_errors": schema_errors,
        "status_errors": status_errors,
        "fixture_errors": fixture_errors,
        "privacy": {
            "passed": not privacy_hits,
            "violation_count": len(privacy_hits),
            "violations": privacy_hits,
            "denylist": [pattern.pattern for pattern in PRIVATE_TEXT_PATTERNS],
        },
        "bundle": sanitize_value(bundle),
    }


def build_fixture_inventory_response(
    *,
    fixture_name: str | None,
    report: dict[str, Any] | None,
    audit_events: list[dict[str, Any]] | None = None,
    expected_artifact_version_id: str | None = None,
) -> dict[str, Any]:
    approved = approved_fixture_config(fixture_name)
    expected_version = expected_artifact_version_id or approved.get("expected_artifact_version_id")
    current_version = _artifact_version(report)
    status = _fixture_status(
        fixture_name=fixture_name,
        report=report,
        approved=bool(approved),
        expected_artifact_version_id=expected_version,
        current_artifact_version_id=current_version,
    )
    response = {
        "generated_at": now_iso(),
        "fixture_name": fixture_name,
        "approved": bool(approved),
        "status": status,
        "identity": {
            "parent_id": _safe_string(report.get("parent_id") if report else approved.get("parent_id")),
            "student_id": _safe_string(report.get("student_id") if report else approved.get("student_id")),
            "week_start": _safe_string(report.get("week_start") if report else approved.get("week_start")),
        },
        "artifact_versions": {
            "current": current_version,
            "expected_baseline": expected_version,
            "previous": _safe_string(report.get("previous_artifact_version_id")) if report else None,
            "created_at": _safe_string(report.get("artifact_version_created_at")) if report else None,
            "created_by": _safe_string(report.get("artifact_version_created_by")) if report else None,
        },
        "report": {
            "report_id": _safe_string(report.get("report_id")) if report else None,
            "status": _safe_string(report.get("status")) if report else None,
            "email_status": _safe_string(report.get("email_status")) if report else None,
            "last_operation": _safe_string(report.get("last_operation")) if report else None,
            "updated_at": _safe_string(report.get("updated_at")) if report else None,
        },
        "audit_refs": [_audit_ref(event) for event in (audit_events or [])[:10]],
        "mutation_refusal": {
            "would_refuse_without_fixture_name": True,
            "would_refuse_without_mutation_mode": True,
            "allowed_when_status": "ready",
        },
    }
    hits = private_marker_hits(response)
    response["privacy"] = {
        "metadata_only": True,
        "private_artifact_fields_omitted": True,
        "passed": not hits,
        "violation_count": len(hits),
        "violations": hits,
    }
    return response


def mutation_refusal_reasons(
    *,
    fixture_name: str | None,
    mutation_mode: str | None,
    fixture_status: str | None,
    privacy_passed: bool = True,
) -> list[str]:
    reasons: list[str] = []
    if not fixture_name:
        reasons.append("missing fixture name")
    elif not approved_fixture_config(fixture_name):
        reasons.append("fixture name is not approved")
    if not mutation_mode:
        reasons.append("missing mutation mode")
    if fixture_status != "ready" and mutation_mode not in MUTATION_CLEANUP_MODES:
        reasons.append(f"fixture status {fixture_status or 'unknown'} is not mutation-ready")
    if not privacy_passed:
        reasons.append("privacy denylist check failed")
    return reasons


def approved_fixture_config(fixture_name: str | None) -> dict[str, str]:
    if not fixture_name:
        return {}
    return APPROVED_FIXTURES.get(fixture_name, {})


def private_marker_hits(value: object, path: str = "$") -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _is_private_key(key_text):
                hits.append({"path": child_path, "marker": key_text})
            hits.extend(private_marker_hits(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(private_marker_hits(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in PRIVATE_TEXT_PATTERNS:
            if pattern.search(value):
                hits.append({"path": path, "marker": pattern.pattern})
    return hits


def sanitize_value(value: object) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_private_key(key_text):
                continue
            sanitized[key_text] = sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _safe_string(value)
    return value


def _safe_string(value: object) -> str | None:
    if value is None:
        return None
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    if any(pattern.search(text) for pattern in PRIVATE_TEXT_PATTERNS):
        return "[REDACTED]"
    return text


def _is_private_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in PRIVATE_KEY_FRAGMENTS)


def _status_errors(value: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "status" and isinstance(item, str) and item not in VALID_STATUSES:
                errors.append(f"{child_path} has invalid status {item!r}")
            errors.extend(_status_errors(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_status_errors(item, f"{path}[{index}]"))
    return errors


def _fixture_errors(fixture: object) -> list[str]:
    if fixture in (None, {}, []):
        return []
    if not isinstance(fixture, dict):
        return ["fixture must be an object"]
    mutation_mode = fixture.get("mutation_mode")
    approved_name = fixture.get("approved_fixture_name") or fixture.get("fixture_name")
    mutation_performed = bool(mutation_mode or fixture.get("mutation_performed"))
    if not mutation_performed:
        return []
    errors = []
    if not approved_name:
        errors.append("fixture mutation evidence requires approved_fixture_name")
    elif not approved_fixture_config(str(approved_name)):
        errors.append("fixture mutation evidence references an unapproved fixture")
    if not mutation_mode:
        errors.append("fixture mutation evidence requires mutation_mode")
    return errors


def _fixture_status(
    *,
    fixture_name: str | None,
    report: dict[str, Any] | None,
    approved: bool,
    expected_artifact_version_id: str | None,
    current_artifact_version_id: str | None,
) -> str:
    if not fixture_name or not approved:
        return "disabled"
    if not report:
        return "missing"
    if expected_artifact_version_id and current_artifact_version_id != expected_artifact_version_id:
        return "dirty"
    return "ready"


def _artifact_version(report: dict[str, Any] | None) -> str | None:
    if not report:
        return None
    return _safe_string(report.get("artifact_version_id") or "original")


def _audit_ref(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": _safe_string(event.get("event_id")),
        "event_at": _safe_string(event.get("event_at")),
        "action": _safe_string(event.get("action")),
        "result": _safe_string(event.get("result")),
        "correlation_id": _safe_string(event.get("correlation_id")),
    }
