"""Metadata-only audit retention manifest helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from stoa.db.repositories import report_repo
from stoa.services import release_evidence_service, report_recovery_evidence_service, report_recovery_service


SCHEMA_VERSION = "v1"
SUPPORTED_SCOPES = {"recovery_job", "report", "support_handoff", "release_evidence"}
REFUSED_ACTIONS = {
    "delete",
    "expire",
    "shorten_retention",
    "worm_write",
    "object_lock",
    "legal_hold",
    "external_write",
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
PRIVATE_FREE_TEXT_PATTERN = re.compile(
    r"\b(access_token|id_token|refresh_token|password|secret|cookie)\b\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


class AuditRetentionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_status_response(
    *,
    references: list[dict[str, Any]],
    request_id: str | None,
    limit: int = 25,
) -> dict[str, Any]:
    items = []
    for reference in references[:limit]:
        resolved = _resolve_reference(reference, include_evidence=False, target_limit=0, audit_limit=0)
        items.append(
            {
                "reference": resolved["reference"],
                "status": _status_for_resolved(resolved),
                "reason": resolved.get("reason"),
                "counts": resolved.get("counts", {}),
                "privacy": resolved.get("privacy") or _privacy_result(resolved.get("evidence")),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now_iso(),
        "request_id": request_id,
        "scope_count": len(items),
        "items": items,
        "privacy": _privacy_result(items),
    }


def build_manifest(
    *,
    reason: str,
    generated_by: str,
    request_id: str | None,
    references: list[dict[str, Any]],
    retention_category: str = "operational",
    retention_action: str = "seal_metadata",
    target_limit: int = 25,
    audit_limit: int = 25,
) -> dict[str, Any]:
    manifest_id = f"audit-retention-{uuid4().hex}"
    generated_at = now_iso()
    safe_reason = _redact_text(reason) or ""
    safe_operator = _redact_text(generated_by) or "unknown-admin"
    action = str(retention_action or "seal_metadata").strip()

    refusal_reasons: list[str] = []
    missing_refs: list[dict[str, Any]] = []
    skipped_refs: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []

    if action in REFUSED_ACTIONS:
        refusal_reasons.append(f"retention action {action} is not supported by v2.6 metadata-only readiness")
    elif action not in {"seal_metadata", "preview", "download"}:
        refusal_reasons.append(f"retention action {action or 'missing'} is unsupported")

    if not references:
        refusal_reasons.append("at least one audit evidence reference is required")

    if not refusal_reasons:
        for reference in references[:10]:
            resolved = _resolve_reference(
                reference,
                include_evidence=True,
                target_limit=target_limit,
                audit_limit=audit_limit,
            )
            raw_status = str(resolved.get("status") or "unsupported")
            if raw_status == "unsupported":
                skipped_refs.append({"reference": resolved["reference"], "reason": resolved.get("reason")})
                continue
            if raw_status == "refused":
                refusal_reasons.append(str(resolved.get("reason") or "reference refused"))
                continue
            if raw_status == "missing" or not resolved.get("evidence"):
                missing_refs.append({"reference": resolved["reference"], "reason": resolved.get("reason")})
                continue
            evidence = _sanitize_value(resolved.get("evidence") or {})
            evidence_items.append(
                {
                    "item_id": _item_id(resolved["reference"]),
                    "scope": resolved["reference"]["scope"],
                    "reference": resolved["reference"],
                    "status": "sealed",
                    "summary": evidence,
                    "digest": _digest(evidence),
                }
            )

    manifest_status = _manifest_status(
        evidence_count=len(evidence_items),
        missing_count=len(missing_refs),
        skipped_count=len(skipped_refs),
        refusal_count=len(refusal_reasons),
    )
    manifest_body = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "generated_at": generated_at,
        "generated_by": safe_operator,
        "reason": safe_reason,
        "scope": {
            "references": [_sanitize_reference(reference) for reference in references[:10]],
            "reference_count": len(references[:10]),
        },
        "retention_category": _safe_category(retention_category),
        "retention_clock": {
            "source": "audit_event_at",
            "started_at": generated_at,
        },
        "items": evidence_items,
        "verification": {
            "item_count": len(evidence_items),
            "missing_references": missing_refs,
            "skipped_references": skipped_refs,
            "refusal_reasons": refusal_reasons,
            "privacy": {"metadata_only": True, "private_artifact_fields_omitted": True},
        },
        "status": manifest_status,
    }
    privacy = _privacy_result(manifest_body)
    manifest_body["verification"]["privacy"] = privacy
    if not privacy["passed"]:
        manifest_body = _refusal_envelope(
            manifest_body,
            privacy=privacy,
            refusal_reason="privacy denylist check failed",
        )
    manifest_body["verification"]["manifest_digest"] = _digest(_manifest_digest_body(manifest_body))
    write_manifest_audit_event(
        manifest_body,
        actor=safe_operator,
        request_id=request_id,
        reason=safe_reason,
        retention_action=action,
    )
    return manifest_body


def write_manifest_audit_event(
    manifest: dict[str, Any],
    *,
    actor: str,
    request_id: str | None,
    reason: str,
    retention_action: str,
) -> dict[str, Any]:
    event = {
        "event_id": uuid4().hex,
        "event_at": now_iso(),
        "manifest_id": manifest["manifest_id"],
        "actor": _redact_text(actor),
        "action": "audit_retention_manifest",
        "reason": _redact_text(reason),
        "source": "admin_api",
        "result": "refused" if manifest.get("status") == "refused" else "generated",
        "correlation_id": request_id,
        "metadata": {
            "schema_version": manifest.get("schema_version"),
            "retention_action": _redact_text(retention_action),
            "retention_category": manifest.get("retention_category"),
            "manifest_status": manifest.get("status"),
            "manifest_digest": manifest.get("verification", {}).get("manifest_digest"),
            "item_count": manifest.get("verification", {}).get("item_count"),
            "missing_reference_count": len(manifest.get("verification", {}).get("missing_references") or []),
            "skipped_reference_count": len(manifest.get("verification", {}).get("skipped_references") or []),
            "privacy_passed": manifest.get("verification", {}).get("privacy", {}).get("passed"),
        },
    }
    report_repo.put_audit_retention_audit_event(manifest["manifest_id"], event)
    return event


def _resolve_reference(
    reference: dict[str, Any],
    *,
    include_evidence: bool,
    target_limit: int,
    audit_limit: int,
) -> dict[str, Any]:
    scope = _redact_text(reference.get("scope"))
    if scope == "release_evidence":
        return _resolve_release_evidence(reference, include_evidence=include_evidence)
    safe_ref = _sanitize_reference(reference)
    if scope not in SUPPORTED_SCOPES:
        return {"reference": safe_ref, "status": "unsupported", "reason": f"unsupported scope: {scope or 'missing'}"}
    if scope == "recovery_job":
        return _resolve_recovery_job(safe_ref, include_evidence=include_evidence, target_limit=target_limit, audit_limit=audit_limit)
    if scope == "report":
        return _resolve_report(safe_ref, include_evidence=include_evidence, audit_limit=audit_limit)
    return _resolve_support_handoff(safe_ref, include_evidence=include_evidence, audit_limit=audit_limit)


def _resolve_recovery_job(
    reference: dict[str, Any],
    *,
    include_evidence: bool,
    target_limit: int,
    audit_limit: int,
) -> dict[str, Any]:
    job_id = reference.get("job_id")
    if not job_id:
        return {"reference": reference, "status": "missing", "reason": "missing job_id"}
    job = report_repo.get_recovery_job(str(job_id))
    if not job:
        return {"reference": reference, "status": "missing", "reason": "recovery job not found"}
    evidence: dict[str, Any] | None = None
    counts = {"jobs": 1}
    if include_evidence:
        targets = report_repo.list_recovery_job_targets(str(job_id), limit=target_limit).get("Items", [])
        audits = report_repo.list_recovery_job_audit_events(str(job_id), limit=audit_limit).get("Items", [])
        counts = {"jobs": 1, "targets": len(targets), "job_audit": len(audits)}
        evidence = report_recovery_evidence_service.build_export_response(
            scope="recovery_job",
            request_id=None,
            filters={"job_id": str(job_id), "target_limit": target_limit, "audit_limit": audit_limit},
            jobs=[job],
            targets=targets,
            job_audit=audits,
        )
    return {"reference": reference, "status": "unsealed", "counts": counts, "evidence": evidence}


def _resolve_report(
    reference: dict[str, Any],
    *,
    include_evidence: bool,
    audit_limit: int,
) -> dict[str, Any]:
    required = ("parent_id", "student_id", "week_start")
    if any(not reference.get(field) for field in required):
        return {"reference": reference, "status": "missing", "reason": "missing report reference fields"}
    report = report_repo.get_report_for_child_by_week(
        str(reference["parent_id"]),
        str(reference["student_id"]),
        str(reference["week_start"]),
    )
    if not report:
        return {"reference": reference, "status": "missing", "reason": "report not found"}
    evidence = None
    audits: list[dict[str, Any]] = []
    if include_evidence:
        audits = report_repo.list_report_audit_events(str(report["report_id"]), limit=audit_limit).get("Items", [])
        evidence = {
            "scope": "report",
            "report": _report_summary(report),
            "report_audit": [report_recovery_evidence_service.audit_summary(event) for event in audits],
            "privacy": {"metadata_only": True, "private_artifact_fields_omitted": True},
        }
    return {"reference": reference, "status": "unsealed", "counts": {"reports": 1, "report_audit": len(audits)}, "evidence": evidence}


def _resolve_support_handoff(
    reference: dict[str, Any],
    *,
    include_evidence: bool,
    audit_limit: int,
) -> dict[str, Any]:
    package_id = reference.get("package_id")
    if not package_id:
        return {"reference": reference, "status": "missing", "reason": "missing package_id"}
    audits = report_repo.list_support_handoff_audit_events(str(package_id), limit=audit_limit).get("Items", [])
    if not audits:
        return {"reference": reference, "status": "missing", "reason": "support handoff audit not found"}
    evidence = None
    if include_evidence:
        evidence = {
            "scope": "support_handoff",
            "package_id": _redact_text(package_id),
            "support_handoff_audit": [_generic_audit_summary(event) for event in audits],
            "privacy": {"metadata_only": True, "private_artifact_fields_omitted": True},
        }
    return {"reference": reference, "status": "unsealed", "counts": {"support_handoff_audit": len(audits)}, "evidence": evidence}


def _resolve_release_evidence(reference: dict[str, Any], *, include_evidence: bool) -> dict[str, Any]:
    bundle = reference.get("release_evidence")
    if not isinstance(bundle, dict):
        return {"reference": {"scope": "release_evidence"}, "status": "missing", "reason": "missing release_evidence bundle"}
    validation = release_evidence_service.validate_release_bundle(bundle)
    if validation.get("status") != "passed" or not validation.get("privacy", {}).get("passed", True):
        return {
            "reference": {"scope": "release_evidence", "release": _release_reference_id(bundle)},
            "status": "refused",
            "reason": "release evidence validation failed",
            "evidence": _strip_denylist(validation) if include_evidence else None,
            "privacy": _privacy_result(validation),
        }
    return {
        "reference": {"scope": "release_evidence", "release": _release_reference_id(bundle)},
        "status": "unsealed",
        "counts": {"release_evidence": 1},
        "evidence": _strip_denylist(validation) if include_evidence else None,
    }


def _status_for_resolved(resolved: dict[str, Any]) -> str:
    status = str(resolved.get("status") or "unsupported")
    if status in {"unsupported", "refused"}:
        return status
    if status == "missing":
        return "skipped"
    return "unsealed"


def _manifest_status(*, evidence_count: int, missing_count: int, skipped_count: int, refusal_count: int) -> str:
    if refusal_count:
        return "refused"
    if evidence_count == 0:
        return "refused"
    if missing_count or skipped_count:
        return "partial"
    return "sealed"


def _report_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": _redact_text(report.get("report_id")),
        "parent_id": _redact_text(report.get("parent_id")),
        "student_id": _redact_text(report.get("student_id")),
        "student_name": _redact_text(report.get("student_name")),
        "week_start": _redact_text(report.get("week_start")),
        "status": _redact_text(report.get("status")),
        "email_status": _redact_text(report.get("email_status")),
        "artifact_version_id": _redact_text(report.get("artifact_version_id") or "original"),
        "previous_artifact_version_id": _redact_text(report.get("previous_artifact_version_id")),
        "updated_at": _redact_text(report.get("updated_at")),
        "last_operation": _redact_text(report.get("last_operation")),
        "last_operation_result": _redact_text(report.get("last_operation_result")),
    }


def _generic_audit_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": _redact_text(event.get("event_id")),
        "event_at": _redact_text(event.get("event_at")),
        "actor": _redact_text(event.get("actor")),
        "action": _redact_text(event.get("action")),
        "reason": _redact_text(event.get("reason")),
        "source": _redact_text(event.get("source")),
        "result": _redact_text(event.get("result")),
        "metadata": report_recovery_evidence_service.sanitize_metadata(event.get("metadata")) or {},
        "correlation_id": _redact_text(event.get("correlation_id")),
    }


def _sanitize_reference(reference: dict[str, Any]) -> dict[str, Any]:
    scope = _redact_text(reference.get("scope"))
    safe: dict[str, Any] = {"scope": scope}
    for key in ("job_id", "parent_id", "student_id", "week_start", "package_id"):
        if reference.get(key) is not None:
            safe[key] = _redact_text(reference.get(key))
    if isinstance(reference.get("release_evidence"), dict):
        safe["release_evidence"] = _sanitize_value(reference["release_evidence"])
    return safe


def _sanitize_value(value: object) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "denylist" or _is_private_key(key_text):
                continue
            sanitized[key_text] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return _strip_denylist(value)


def _strip_denylist(value: object) -> Any:
    if isinstance(value, dict):
        return {str(key): _strip_denylist(item) for key, item in value.items() if str(key) != "denylist"}
    if isinstance(value, list):
        return [_strip_denylist(item) for item in value]
    return value


def _privacy_result(value: object) -> dict[str, Any]:
    hits = release_evidence_service.private_marker_hits(_strip_denylist(value))
    return {
        "metadata_only": True,
        "private_artifact_fields_omitted": True,
        "passed": not hits,
        "violation_count": len(hits),
        "violations": [{"path": "[REDACTED]", "marker": "[private-marker]"} for _ in hits],
    }


def _manifest_digest_body(manifest: dict[str, Any]) -> dict[str, Any]:
    body = dict(manifest)
    verification = dict(body.get("verification") or {})
    verification.pop("manifest_digest", None)
    body["verification"] = verification
    return body


def _digest(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _item_id(reference: dict[str, Any]) -> str:
    digest = _digest(reference).split(":", 1)[1][:16]
    return f"{reference.get('scope')}-{digest}"


def _safe_category(value: str) -> str:
    category = str(value or "operational").strip()
    if category not in {"operational", "incident", "release", "fixture", "support_handoff"}:
        return "operational"
    return category


def _release_reference_id(bundle: dict[str, Any]) -> str:
    milestone = _redact_text(bundle.get("milestone")) or "release"
    phase = _redact_text(bundle.get("phase")) or "unknown"
    generated_at = _redact_text(bundle.get("generated_at")) or "undated"
    return f"{milestone}-phase-{phase}-{generated_at}"


def _redact_text(value: object) -> str | None:
    if value is None:
        return None
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    text = PRIVATE_FREE_TEXT_PATTERN.sub("[private-credential]", text)
    if release_evidence_service.private_marker_hits(text):
        return "[REDACTED]"
    return text


def _is_private_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in PRIVATE_KEY_FRAGMENTS)


def _refusal_envelope(
    manifest: dict[str, Any],
    *,
    privacy: dict[str, Any],
    refusal_reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": manifest["schema_version"],
        "manifest_id": manifest["manifest_id"],
        "generated_at": manifest["generated_at"],
        "generated_by": manifest["generated_by"],
        "reason": manifest["reason"],
        "scope": {"references": manifest.get("scope", {}).get("references", []), "reference_count": manifest.get("scope", {}).get("reference_count", 0)},
        "retention_category": manifest["retention_category"],
        "retention_clock": manifest["retention_clock"],
        "items": [],
        "verification": {
            "item_count": 0,
            "missing_references": [],
            "skipped_references": [],
            "refusal_reasons": [*(manifest.get("verification", {}).get("refusal_reasons") or []), refusal_reason],
            "privacy": privacy,
        },
        "status": "refused",
    }
