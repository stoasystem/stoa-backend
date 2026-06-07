"""Support handoff package composition helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from stoa.db.repositories import report_repo
from stoa.services import release_evidence_service, report_recovery_service


SCHEMA_VERSION = "v1"
ALLOWED_DESTINATIONS = {"preview", "copy", "download"}
REFUSED_DESTINATIONS = {"external_write"}
MAX_RECOVERY_JOB_REFS = 5
PRIVATE_FREE_TEXT_PATTERN = re.compile(
    r"\b(access_token|id_token|refresh_token|password|secret|cookie)\b\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


class SupportHandoffError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_package(
    *,
    reason: str,
    destination_mode: str,
    generated_by: str,
    request_id: str | None,
    recovery_sections: list[dict[str, Any]] | None = None,
    release_evidence: dict[str, Any] | None = None,
    fixture: dict[str, Any] | None = None,
    operator_note: str | None = None,
) -> dict[str, Any]:
    destination = _destination_mode(destination_mode)
    package_id = f"support-handoff-{uuid4().hex}"
    generated_at = now_iso()
    references: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    missing_references: list[dict[str, str]] = []
    skipped_sections: list[dict[str, str]] = []
    refusal_reasons: list[str] = []
    validation_failures: list[str] = []

    safe_reason = _redact_text(reason) or ""
    safe_operator = _redact_text(generated_by) or "unknown-admin"

    if destination in REFUSED_DESTINATIONS:
        refusal_reasons.append("direct external writes require approved connector or secret-backed credential path")
    else:
        for section in recovery_sections or []:
            section_ref = _string_or_none(section.get("job_id"))
            if not section_ref:
                skipped_sections.append({"type": "recovery_job", "reason": "missing job_id"})
                continue
            references.append({"type": "recovery_job", "id": section_ref})
            if section.get("missing"):
                missing_references.append({"type": "recovery_job", "id": section_ref})
                validation_failures.append(f"recovery job reference not found: {section_ref}")
                continue
            sections.append(
                {
                    "type": "recovery_job_support_package",
                    "reference": {"type": "recovery_job", "id": section_ref},
                    "status": "included",
                    "data": _sanitize_value(section.get("data") or {}),
                }
            )

        if release_evidence is not None:
            references.append({"type": "release_evidence", "id": _release_reference_id(release_evidence)})
            validated = _release_validation_result(release_evidence)
            if validated.get("status") != "passed" or not validated.get("privacy", {}).get("passed", True):
                validation_failures.append("release evidence validation failed")
            sections.append(
                {
                    "type": "release_evidence_validation",
                    "reference": {"type": "release_evidence", "id": _release_reference_id(release_evidence)},
                    "status": validated.get("status"),
                    "data": validated,
                }
            )

        if fixture is not None:
            fixture_name = _string_or_none(fixture.get("fixture_name")) or "unknown-fixture"
            references.append({"type": "safe_fixture", "id": fixture_name})
            sections.append(
                {
                    "type": "safe_fixture_status",
                    "reference": {"type": "safe_fixture", "id": fixture_name},
                    "status": _string_or_none(fixture.get("status")) or "unknown",
                    "data": _sanitize_value(fixture),
                }
            )

        if operator_note is not None:
            sections.append(
                {
                    "type": "operator_note",
                    "reference": None,
                    "status": "included",
                    "data": {"note": _redact_text(operator_note)},
                }
            )

    if not references and operator_note is None and not refusal_reasons:
        raise SupportHandoffError(422, "At least one evidence reference or operator note is required")

    if validation_failures:
        refusal_reasons.extend(validation_failures)
    validation_status = "refused" if refusal_reasons else "passed"
    destination_status = "refused" if refusal_reasons else "ready"
    package = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "generated_at": generated_at,
        "generated_by": safe_operator,
        "reason": safe_reason,
        "destination": {
            "mode": destination,
            "status": destination_status,
            "refusal_reasons": refusal_reasons,
        },
        "evidence_references": references,
        "sections": sections,
        "validation": {
            "status": validation_status,
            "failures": validation_failures,
            "missing_references": missing_references,
            "skipped_sections": skipped_sections,
            "privacy": {
                "metadata_only": True,
                "private_artifact_fields_omitted": True,
                "passed": True,
                "violation_count": 0,
                "violations": [],
            },
        },
        "audit": {
            "correlation_id": request_id,
            "audit_event_refs": [],
        },
    }
    _attach_output_mode(package)
    hits = release_evidence_service.private_marker_hits(package)
    package["validation"]["privacy"] = {
        "metadata_only": True,
        "private_artifact_fields_omitted": True,
        "passed": not hits,
        "violation_count": len(hits),
        "violations": hits,
    }
    if hits:
        package["validation"]["status"] = "failed"
        package["destination"]["status"] = "refused"
        package["destination"]["refusal_reasons"] = [
            *package["destination"]["refusal_reasons"],
            "privacy denylist check failed",
        ]
    return package


def write_audit_event(
    package: dict[str, Any],
    *,
    actor: str,
    reason: str,
    request_id: str | None,
) -> dict[str, Any]:
    result = "refused" if package["destination"]["status"] == "refused" else "generated"
    event = {
        "event_id": uuid4().hex,
        "event_at": now_iso(),
        "package_id": package["package_id"],
        "actor": _redact_text(actor),
        "action": "support_handoff_package",
        "reason": _redact_text(reason),
        "source": "admin_api",
        "result": result,
        "correlation_id": request_id,
        "metadata": {
            "schema_version": package["schema_version"],
            "destination_mode": package["destination"]["mode"],
            "validation_result": package["validation"]["status"],
            "evidence_reference_ids": [_redact_text(ref.get("id")) for ref in package["evidence_references"]],
            "refusal_reasons": package["destination"]["refusal_reasons"],
            "privacy_passed": package["validation"]["privacy"]["passed"],
        },
    }
    report_repo.put_support_handoff_audit_event(package["package_id"], event)
    package["audit"]["audit_event_refs"].append(
        {
            "event_id": event["event_id"],
            "event_at": event["event_at"],
            "action": event["action"],
            "result": event["result"],
        }
    )
    return event


def _destination_mode(value: str) -> str:
    mode = str(value or "").strip()
    if mode in ALLOWED_DESTINATIONS or mode in REFUSED_DESTINATIONS:
        return mode
    raise SupportHandoffError(422, f"Unsupported destination mode: {mode or 'missing'}")


def _attach_output_mode(package: dict[str, Any]) -> None:
    mode = package["destination"]["mode"]
    if mode == "copy":
        package["copy"] = {
            "format": "markdown",
            "text": _copy_text(package),
        }
    elif mode == "download":
        package["download"] = {
            "filename": f"{package['package_id']}.json",
            "content_type": "application/json",
        }


def _copy_text(package: dict[str, Any]) -> str:
    refs = ", ".join(str(ref.get("id")) for ref in package["evidence_references"]) or "none"
    return "\n".join(
        [
            f"# Support Handoff Package {package['package_id']}",
            f"Generated: {package['generated_at']}",
            f"Reason: {package['reason']}",
            f"Destination: {package['destination']['mode']}",
            f"Evidence references: {refs}",
            f"Validation: {package['validation']['status']}",
        ]
    )


def _release_reference_id(bundle: dict[str, Any]) -> str:
    milestone = _string_or_none(bundle.get("milestone")) or "release"
    phase = _string_or_none(bundle.get("phase")) or "unknown"
    generated_at = _string_or_none(bundle.get("generated_at")) or "undated"
    return f"{milestone}-phase-{phase}-{generated_at}"


def _release_validation_result(bundle: dict[str, Any]) -> dict[str, Any]:
    validated = release_evidence_service.validate_release_bundle(bundle)
    privacy = validated.get("privacy") if isinstance(validated.get("privacy"), dict) else {}
    return {
        "schema_version": validated.get("schema_version"),
        "validated_at": validated.get("validated_at"),
        "status": validated.get("status"),
        "missing_required_fields": validated.get("missing_required_fields", []),
        "schema_errors": validated.get("schema_errors", []),
        "status_errors": validated.get("status_errors", []),
        "fixture_errors": validated.get("fixture_errors", []),
        "privacy": {
            "passed": privacy.get("passed", False),
            "violation_count": privacy.get("violation_count", 0),
        },
    }


def _sanitize_value(value: object) -> Any:
    return release_evidence_service.sanitize_value(value)


def _redact_text(value: object) -> str | None:
    text = report_recovery_service.redact_private_artifact_text(value)
    if text is None:
        return None
    return PRIVATE_FREE_TEXT_PATTERN.sub("[private-credential]", text)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return _redact_text(value)
