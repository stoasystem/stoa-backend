"""Metadata-only audit retention manifest helpers."""

from __future__ import annotations

import boto3
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from stoa.config import settings
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


class ImmutableEvidenceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_request_id(value: object) -> str | None:
    text = _redact_text(value)
    if not text:
        return None
    return text[:240]


def build_status_response(
    *,
    references: list[dict[str, Any]],
    request_id: str | None,
    limit: int = 25,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
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
    request_id = sanitize_request_id(request_id)
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


def build_immutable_status_response(
    *,
    references: list[dict[str, Any]],
    request_id: str | None,
    limit: int = 25,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    retention_status = build_status_response(
        references=references,
        request_id=request_id,
        limit=limit,
    )
    hold_status = build_legal_hold_status_response(
        references=references,
        request_id=request_id,
        limit=limit,
    )
    response = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now_iso(),
        "request_id": request_id,
        "immutable_storage": _immutable_storage_public_status(),
        "audit_retention": retention_status,
        "legal_hold": hold_status,
    }
    response["privacy"] = _privacy_result(response)
    return response


def persist_immutable_manifest(
    *,
    reason: str,
    generated_by: str,
    request_id: str | None,
    references: list[dict[str, Any]],
    retention_category: str = "operational",
    target_limit: int = 25,
    audit_limit: int = 25,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    manifest = build_manifest(
        reason=reason,
        generated_by=generated_by,
        request_id=request_id,
        references=references,
        retention_category=retention_category,
        retention_action="seal_metadata",
        target_limit=target_limit,
        audit_limit=audit_limit,
    )
    storage_status = _immutable_storage_status()
    if manifest.get("status") == "refused":
        persist_status = _immutable_refusal_status(
            "manifest refused before immutable persistence",
            storage_status=storage_status,
        )
        write_immutable_persistence_audit_event(
            manifest,
            actor=generated_by,
            request_id=request_id,
            reason=reason,
            result="refused",
            metadata=persist_status,
        )
        return _immutable_manifest_response(manifest, persist_status)

    privacy = _privacy_result(manifest)
    if not privacy["passed"]:
        persist_status = _immutable_refusal_status(
            "privacy denylist check failed before immutable persistence",
            storage_status=storage_status,
            privacy=privacy,
        )
        write_immutable_persistence_audit_event(
            manifest,
            actor=generated_by,
            request_id=request_id,
            reason=reason,
            result="refused",
            metadata=persist_status,
        )
        return _immutable_manifest_response(manifest, persist_status)

    if storage_status["status"] != "ready":
        persist_status = _immutable_refusal_status(
            "immutable storage is not configured by CDK",
            storage_status=storage_status,
        )
        write_immutable_persistence_audit_event(
            manifest,
            actor=generated_by,
            request_id=request_id,
            reason=reason,
            result="refused",
            metadata=persist_status,
        )
        return _immutable_manifest_response(manifest, persist_status)

    manifest_digest = manifest.get("verification", {}).get("manifest_digest")
    immutable_ref_id = _immutable_ref_id(manifest)
    pending_reference = {
        "immutable_ref_id": immutable_ref_id,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": manifest_digest,
        "digest_algorithm": "sha256",
        "status": "pending_object_write",
        "scope": manifest.get("scope"),
        "retention_category": manifest.get("retention_category"),
        "retention_clock": manifest.get("retention_clock"),
        "item_count": manifest.get("verification", {}).get("item_count"),
        "privacy": privacy,
        "created_at": now_iso(),
        "created_by": _redact_text(generated_by),
        "source_request_id": request_id,
        "storage_mode": storage_status["mode"],
        "storage_cdk_managed": storage_status["cdk_managed"],
    }
    pending_created = report_repo.put_audit_retention_manifest(
        str(manifest["manifest_id"]),
        pending_reference,
    )
    if not pending_created:
        persist_status = {
            "status": "refused",
            "immutable_ref_id": None,
            "manifest_id": manifest["manifest_id"],
            "manifest_digest": manifest_digest,
            "reason": "immutable manifest reference already exists",
            "storage": _immutable_storage_public_status(storage_status),
            "privacy": privacy,
        }
        write_immutable_persistence_audit_event(
            manifest,
            actor=generated_by,
            request_id=request_id,
            reason=reason,
            result="refused",
            metadata=persist_status,
        )
        return _immutable_manifest_response(manifest, persist_status)

    try:
        object_write = _write_immutable_manifest_object(
            manifest,
            immutable_ref_id=immutable_ref_id,
            storage_status=storage_status,
        )
    except Exception as exc:
        persist_status = _immutable_refusal_status(
            "immutable object write failed",
            storage_status=storage_status,
        )
        persist_status["error_code"] = _redact_text(exc.__class__.__name__)
        report_repo.update_audit_retention_manifest_status(
            str(manifest["manifest_id"]),
            {
                "status": "refused",
                "reason": "immutable object write failed",
                "updated_at": now_iso(),
            },
            expected_status="pending_object_write",
        )
        write_immutable_persistence_audit_event(
            manifest,
            actor=generated_by,
            request_id=request_id,
            reason=reason,
            result="refused",
            metadata=persist_status,
        )
        return _immutable_manifest_response(manifest, persist_status)
    persisted = report_repo.update_audit_retention_manifest_status(
        str(manifest["manifest_id"]),
        {
            "object_digest": object_write["object_digest"],
            "object_key_digest": object_write["object_key_digest"],
            "status": "persisted",
            "updated_at": now_iso(),
        },
        expected_status="pending_object_write",
    )
    persist_status = {
        "status": "persisted" if persisted else "refused",
        "immutable_ref_id": immutable_ref_id if persisted else None,
        "manifest_id": manifest["manifest_id"],
        "manifest_digest": manifest_digest,
        "object_digest": object_write["object_digest"] if persisted else None,
        "reason": None if persisted else "immutable manifest reference status changed; reconcile pending object",
        "storage": _immutable_storage_public_status(storage_status),
        "privacy": privacy,
    }
    write_immutable_persistence_audit_event(
        manifest,
        actor=generated_by,
        request_id=request_id,
        reason=reason,
        result="persisted" if persisted else "refused",
        metadata=persist_status,
    )
    return _immutable_manifest_response(manifest, persist_status)


def write_immutable_persistence_audit_event(
    manifest: dict[str, Any],
    *,
    actor: str,
    request_id: str | None,
    reason: str,
    result: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    event = {
        "event_id": uuid4().hex,
        "event_at": now_iso(),
        "manifest_id": manifest["manifest_id"],
        "actor": _redact_text(actor),
        "action": "immutable_evidence_persist",
        "reason": _redact_text(reason),
        "source": "admin_api",
        "result": _redact_text(result),
        "correlation_id": request_id,
        "metadata": _sanitize_value(metadata),
    }
    report_repo.put_audit_retention_audit_event(manifest["manifest_id"], event)
    return event


def build_legal_hold_status_response(
    *,
    references: list[dict[str, Any]],
    request_id: str | None,
    limit: int = 25,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    items = []
    for reference in references[:limit]:
        safe_ref = _legal_hold_reference(reference)
        scope_key = _scope_key(safe_ref)
        current = report_repo.get_legal_hold_metadata(scope_key)
        items.append(
            {
                "reference": safe_ref,
                "scope_key": scope_key,
                "status": _redact_text(current.get("state")) if current else "none",
                "policy_id": _redact_text(current.get("policy_id")) if current else None,
                "hold_id": _redact_text(current.get("hold_id")) if current else None,
                "reason": _redact_text(current.get("reason")) if current else None,
                "updated_at": _redact_text(current.get("updated_at")) if current else None,
            }
        )
    response = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now_iso(),
        "request_id": request_id,
        "scope_count": len(items),
        "items": items,
    }
    response["privacy"] = _privacy_result(response)
    return response


def apply_legal_hold_metadata(
    *,
    references: list[dict[str, Any]],
    action: str,
    reason: str,
    actor: str,
    request_id: str | None,
    policy_id: str = "operational-default",
    limit: int = 10,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    safe_action = str(action or "apply").strip().lower()
    if safe_action not in {"apply", "release"}:
        raise ImmutableEvidenceError(422, "legal hold action must be apply or release")
    safe_reason = _redact_text(reason) or ""
    if not safe_reason:
        raise ImmutableEvidenceError(422, "legal hold reason is required")

    now = now_iso()
    items = []
    for reference in references[:limit]:
        safe_ref = _legal_hold_reference(reference)
        scope = safe_ref.get("scope")
        scope_key = _scope_key(safe_ref)
        if scope not in SUPPORTED_SCOPES:
            item = {
                "reference": safe_ref,
                "scope_key": scope_key,
                "status": "refused",
                "reason": f"unsupported scope: {scope or 'missing'}",
            }
            _write_legal_hold_audit(scope_key, item, actor=actor, request_id=request_id, reason=safe_reason)
            items.append(item)
            continue
        existing = report_repo.get_legal_hold_metadata(scope_key)
        if safe_action == "release" and (not existing or existing.get("state") != "active"):
            item = {
                "reference": safe_ref,
                "scope_key": scope_key,
                "status": "refused",
                "reason": "no active legal hold exists for this scope",
            }
            _write_legal_hold_audit(scope_key, item, actor=actor, request_id=request_id, reason=safe_reason)
            items.append(item)
            continue
        existing_version = _hold_version(existing)
        hold_id = (
            str(existing.get("hold_id"))
            if existing and (safe_action == "release" or existing.get("state") == "active")
            else f"legal-hold-{uuid4().hex}"
        )
        state = "active" if safe_action == "apply" else "released"
        current = {
            "hold_id": hold_id,
            "scope_key": scope_key,
            "reference": safe_ref,
            "state": state,
            "policy_id": _redact_text(policy_id) or "operational-default",
            "reason": safe_reason,
            "created_by": _redact_text(existing.get("created_by")) if existing else _redact_text(actor),
            "created_at": _redact_text(existing.get("created_at")) if existing else now,
            "updated_by": _redact_text(actor),
            "updated_at": now,
            "hold_version": existing_version + 1,
            "source_request_id": request_id,
        }
        if safe_action == "release":
            current["released_by"] = _redact_text(actor)
            current["released_at"] = now
        expected_hold_version = existing_version if existing and "hold_version" in existing else None
        expected_updated_at = (
            str(existing.get("updated_at"))
            if existing and expected_hold_version is None and existing.get("updated_at")
            else None
        )
        recorded = report_repo.put_legal_hold_metadata(
            scope_key,
            current,
            expected_hold_version=expected_hold_version,
            expected_updated_at=expected_updated_at,
        )
        if not recorded:
            item = {
                "reference": safe_ref,
                "scope_key": scope_key,
                "status": "refused",
                "reason": "legal hold metadata changed; refresh status and retry",
            }
            _write_legal_hold_audit(scope_key, item, actor=actor, request_id=request_id, reason=safe_reason)
            items.append(item)
            continue
        item = {
            "reference": safe_ref,
            "scope_key": scope_key,
            "status": state,
            "hold_id": hold_id,
            "policy_id": current["policy_id"],
            "reason": safe_reason,
            "updated_at": now,
            "hold_version": current["hold_version"],
        }
        _write_legal_hold_audit(scope_key, item, actor=actor, request_id=request_id, reason=safe_reason)
        items.append(item)
    response = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now,
        "request_id": request_id,
        "action": safe_action,
        "scope_count": len(items),
        "items": items,
    }
    response["privacy"] = _privacy_result(response)
    return response


def write_manifest_audit_event(
    manifest: dict[str, Any],
    *,
    actor: str,
    request_id: str | None,
    reason: str,
    retention_action: str,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
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


def _immutable_storage_status() -> dict[str, Any]:
    mode = str(settings.immutable_audit_storage_mode or "disabled").strip().lower()
    resource = str(settings.immutable_audit_storage_resource or "").strip()
    prefix = str(settings.immutable_audit_storage_prefix or "").strip()
    cdk_managed = bool(settings.immutable_audit_storage_cdk_managed)
    ready = mode == "cdk_managed" and cdk_managed and bool(resource) and bool(prefix)
    missing = []
    if mode != "cdk_managed":
        missing.append("immutable_audit_storage_mode")
    if not cdk_managed:
        missing.append("immutable_audit_storage_cdk_managed")
    if not resource:
        missing.append("immutable_audit_storage_resource")
    if not prefix:
        missing.append("immutable_audit_storage_prefix")
    return {
        "status": "ready" if ready else "not_configured",
        "mode": mode or "disabled",
        "cdk_managed": cdk_managed,
        "resource_configured": bool(resource),
        "prefix_configured": bool(prefix),
        "missing": missing,
    }


def _immutable_storage_public_status(status: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = status or _immutable_storage_status()
    return {
        "status": raw["status"],
        "mode": raw["mode"],
        "cdk_managed": raw["cdk_managed"],
        "resource_configured": raw["resource_configured"],
        "prefix_configured": raw["prefix_configured"],
        "missing": list(raw.get("missing") or []),
    }


def _immutable_refusal_status(
    reason: str,
    *,
    storage_status: dict[str, Any],
    privacy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "not_configured" if storage_status["status"] == "not_configured" else "refused",
        "reason": _redact_text(reason),
        "storage": _immutable_storage_public_status(storage_status),
        "privacy": privacy or {"metadata_only": True, "private_artifact_fields_omitted": True, "passed": True, "violation_count": 0, "violations": []},
    }


def _immutable_manifest_response(
    manifest: dict[str, Any],
    persist_status: dict[str, Any],
) -> dict[str, Any]:
    response = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest["manifest_id"],
        "generated_at": manifest["generated_at"],
        "generated_by": manifest["generated_by"],
        "reason": manifest["reason"],
        "retention_category": manifest["retention_category"],
        "manifest_status": manifest.get("status"),
        "manifest_digest": manifest.get("verification", {}).get("manifest_digest"),
        "item_count": manifest.get("verification", {}).get("item_count"),
        "immutable_storage": _sanitize_value(persist_status),
        "verification": {
            "privacy": manifest.get("verification", {}).get("privacy"),
            "refusal_reasons": manifest.get("verification", {}).get("refusal_reasons", []),
        },
    }
    response["privacy"] = _privacy_result(response)
    return response


def _immutable_ref_id(manifest: dict[str, Any]) -> str:
    digest = str(manifest.get("verification", {}).get("manifest_digest") or _digest(manifest))
    return "immutable-" + digest.split(":", 1)[-1][:24]


def _write_immutable_manifest_object(
    manifest: dict[str, Any],
    *,
    immutable_ref_id: str,
    storage_status: dict[str, Any],
) -> dict[str, str]:
    resource = str(settings.immutable_audit_storage_resource or "").strip()
    prefix = str(settings.immutable_audit_storage_prefix or "").strip().strip("/")
    if storage_status["status"] != "ready" or not resource or not prefix:
        raise ImmutableEvidenceError(500, "immutable storage writer called before storage is ready")
    object_key = f"{prefix}/{immutable_ref_id}.json"
    immutable_object = {
        "schema_version": SCHEMA_VERSION,
        "immutable_ref_id": immutable_ref_id,
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest.get("schema_version"),
        "canonical_digest": manifest.get("verification", {}).get("manifest_digest"),
        "digest_algorithm": "sha256",
        "created_at": manifest.get("generated_at"),
        "created_by": manifest.get("generated_by"),
        "source_request_id": manifest.get("request_id"),
        "policy_id": manifest.get("retention_category"),
        "retention_until": None,
        "legal_hold_state": "metadata_only",
        "payload": manifest,
    }
    body = json.dumps(immutable_object, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    privacy = _privacy_result(immutable_object)
    if not privacy["passed"]:
        raise ImmutableEvidenceError(422, "privacy denylist check failed before immutable object write")
    boto3.client("s3", region_name=settings.aws_region).put_object(
        Bucket=resource,
        Key=object_key,
        Body=body,
        ContentType="application/vnd.stoa.audit-retention-manifest+json",
        Metadata={
            "immutable-ref-id": immutable_ref_id,
            "manifest-id": str(manifest["manifest_id"]),
            "manifest-digest": str(manifest.get("verification", {}).get("manifest_digest") or ""),
        },
        IfNoneMatch="*",
        ServerSideEncryption="AES256",
    )
    return {
        "object_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        "object_key_digest": _digest(object_key),
    }


def _hold_version(existing: dict[str, Any] | None) -> int:
    if not existing:
        return 0
    try:
        return max(int(existing.get("hold_version") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _legal_hold_reference(reference: dict[str, Any]) -> dict[str, Any]:
    scope = _redact_text(reference.get("scope"))
    if scope == "release_evidence" and isinstance(reference.get("release_evidence"), dict):
        return {"scope": "release_evidence", "release": _release_reference_id(reference["release_evidence"])}
    return _sanitize_reference(reference)


def _scope_key(reference: dict[str, Any]) -> str:
    return _digest(reference).split(":", 1)[1][:32]


def _write_legal_hold_audit(
    scope_key: str,
    item: dict[str, Any],
    *,
    actor: str,
    request_id: str | None,
    reason: str,
) -> dict[str, Any]:
    request_id = sanitize_request_id(request_id)
    event = {
        "event_id": uuid4().hex,
        "event_at": now_iso(),
        "actor": _redact_text(actor),
        "action": "legal_hold_metadata",
        "reason": _redact_text(reason),
        "source": "admin_api",
        "result": "refused" if item.get("status") == "refused" else "recorded",
        "correlation_id": request_id,
        "metadata": _sanitize_value(item),
    }
    report_repo.put_legal_hold_audit_event(scope_key, event)
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
