"""No-privilege teacher application, review, invitation, and activation lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import secrets
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import (
    capability_repo,
    identity_repo,
    security_audit_repo,
    teacher_application_repo,
    user_repo,
)


FORBIDDEN_APPLICATION_FIELDS = frozenset(
    {"document", "documents", "credential", "credentials", "file", "files", "blob", "upload"}
)
ALLOWED_APPLICATION_FIELDS = frozenset(
    {"application_id", "email", "email_verified", "full_name", "subjects", "statement"}
)


def submit_application(
    payload: dict[str, Any],
    *,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Persist an immutable candidacy version without creating any identity privilege."""
    if FORBIDDEN_APPLICATION_FIELDS.intersection(payload):
        raise HTTPException(status_code=422, detail={"code": "credential_documents_deferred"})
    unexpected = set(payload) - ALLOWED_APPLICATION_FIELDS
    if unexpected:
        raise HTTPException(status_code=422, detail={"code": "application_fields_not_allowed"})
    email = _email(payload.get("email"))
    if payload.get("email_verified") is not True:
        raise HTTPException(status_code=422, detail={"code": "verified_email_required"})
    application_id = str(payload.get("application_id") or f"teacherapp_{uuid4().hex}").strip()
    existing = teacher_application_repo.list_application_versions(application_id)
    version = max((int(item.get("version") or 0) for item in existing), default=0) + 1
    timestamp = _timestamp(now)
    row = teacher_application_repo.create_application_version(
        {
            "application_id": application_id,
            "version": version,
            "status": "pending_review",
            "verified_email": email,
            "full_name": _bounded(payload.get("full_name"), 120, "full_name"),
            "subjects": _subjects(payload.get("subjects")),
            "statement": _bounded(payload.get("statement"), 2000, "statement"),
            "created_at": timestamp,
        }
    )
    _audit(
        stream_id=application_id,
        event_type="teacher_application_submitted",
        actor_id=f"application:{application_id}",
        target_id=application_id,
        version=version,
        reason_code="public_application",
        created_at=timestamp,
    )
    return _application_metadata(row)


def review_application(
    *,
    actor: dict[str, Any],
    application_id: str,
    version: int,
    decision: str,
    reason: str,
    invitation_expiry_seconds: int = 900,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_review_decision"})
    clean_reason = _bounded(reason, 1000, "reason")
    application = teacher_application_repo.get_application_version(application_id, version)
    if not application:
        raise HTTPException(status_code=404, detail={"code": "application_version_not_found"})
    timestamp_dt = (now or (lambda: datetime.now(UTC)))()
    timestamp = timestamp_dt.isoformat()
    reviewer_id = _actor_id(actor)
    review_id = f"review_{uuid4().hex}"
    teacher_application_repo.create_review(
        {
            "application_id": application_id,
            "version": int(version),
            "review_id": review_id,
            "decision": decision,
            "internal_reason": clean_reason,
            "reviewer_id": reviewer_id,
            "created_at": timestamp,
        }
    )
    evidence = f"teacher-review:{review_id}"
    _audit(
        stream_id=application_id,
        event_type=f"teacher_application_{decision}",
        actor_id=reviewer_id,
        target_id=application_id,
        version=version,
        reason_code="review_recorded",
        evidence_reference=evidence,
        created_at=timestamp,
    )
    response: dict[str, Any] = {
        "applicationId": application_id,
        "version": version,
        "decision": decision,
        "evidenceReference": evidence,
    }
    if decision == "approved":
        token = secrets.token_urlsafe(32)
        digest = _token_digest(token)
        invitation_id = f"invitation_{uuid4().hex}"
        expires_at = timestamp_dt + timedelta(seconds=max(60, invitation_expiry_seconds))
        teacher_application_repo.create_invitation(
            {
                "invitation_id": invitation_id,
                "token_digest": digest,
                "application_id": application_id,
                "application_version": int(version),
                "verified_email": application["verified_email"],
                "status": "issued",
                "version": 1,
                "issued_by": reviewer_id,
                "issued_at": timestamp,
                "expires_at": expires_at.isoformat(),
                "reason": clean_reason,
            }
        )
        _audit(
            stream_id=application_id,
            event_type="teacher_invitation_issued",
            actor_id=reviewer_id,
            target_id=application_id,
            version=version,
            reason_code="approved_version",
            evidence_reference=f"teacher-invitation:{invitation_id}",
            created_at=timestamp,
        )
        response.update(
            invitationToken=token,
            invitationId=invitation_id,
            expiresAt=expires_at.isoformat(),
        )
    return response


def activate_from_invitation(
    *,
    token: str,
    verified_email: str,
    issuer: str,
    subject: str,
    provider: Any,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Consume once and resume one deny-first activation command across partial failures."""
    digest = _token_digest(token)
    invitation = teacher_application_repo.get_invitation(digest)
    if not invitation:
        raise HTTPException(status_code=409, detail={"code": "invitation_invalid"})
    email = _email(verified_email)
    if not hmac.compare_digest(str(invitation.get("verified_email") or ""), email):
        raise HTTPException(status_code=409, detail={"code": "invitation_email_mismatch"})
    instant = (now or (lambda: datetime.now(UTC)))()
    if _parse_timestamp(invitation.get("expires_at")) <= instant:
        raise HTTPException(status_code=409, detail={"code": "invitation_expired"})

    command_id = str(invitation.get("command_id") or f"teacheractivate_{digest[:24]}")
    existing = teacher_application_repo.get_activation_command(command_id)
    if invitation.get("status") != "issued":
        if not existing or existing.get("status") not in {"provider_failed", "reconciling"}:
            raise HTTPException(status_code=409, detail={"code": "invitation_already_used"})
        return _resume_activation(existing, provider=provider, now=instant)

    user_id = f"teacher_{sha256(command_id.encode()).hexdigest()[:24]}"
    command = teacher_application_repo.create_activation_command(
        {
            "command_id": command_id,
            "application_id": invitation["application_id"],
            "application_version": int(invitation["application_version"]),
            "invitation_id": invitation["invitation_id"],
            "verified_email": email,
            "issuer": issuer.strip().rstrip("/"),
            "subject": subject.strip(),
            "user_id": user_id,
            "status": "pending",
            "version": 1,
            "created_at": instant.isoformat(),
            "updated_at": instant.isoformat(),
        }
    )
    won = teacher_application_repo.claim_invitation(
        digest,
        command_id=command_id,
        consumed_at=instant.isoformat(),
    )
    if not won:
        raise HTTPException(status_code=409, detail={"code": "invitation_already_used"})
    _audit(
        stream_id=command["application_id"],
        event_type="teacher_invitation_consumed",
        actor_id=user_id,
        target_id=user_id,
        version=command["application_version"],
        reason_code="same_verified_email",
        command_id=command_id,
        created_at=instant.isoformat(),
    )
    return _resume_activation(command, provider=provider, now=instant)


def full_application_for_reviewer(
    actor: dict[str, Any], application_id: str, version: int
) -> dict[str, Any]:
    _require_capability(actor, capability_repo.TEACHER_IDENTITY_REVIEWER)
    item = teacher_application_repo.get_application_version(application_id, version)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "application_version_not_found"})
    return {
        **_application_metadata(item),
        "fullName": item.get("full_name"),
        "subjects": item.get("subjects") or [],
        "statement": item.get("statement"),
    }


def _resume_activation(command: dict[str, Any], *, provider: Any, now: datetime) -> dict[str, Any]:
    if command.get("status") == "active":
        raise HTTPException(status_code=409, detail={"code": "invitation_already_used"})
    user_id = command["user_id"]
    pending_profile = {
        "user_id": user_id,
        "role": "teacher",
        "account_status": "pending_review",
        "email": command["verified_email"],
        "activation_command_id": command["command_id"],
        "updated_at": now.isoformat(),
    }
    user_repo.put_user(pending_profile)
    try:
        if hasattr(provider, "ensure_teacher_identity"):
            provider.ensure_teacher_identity(
                email=command["verified_email"], user_id=user_id, group="teachers"
            )
        else:
            provider.admin_add_user_to_group(Username=command["subject"], GroupName="teachers")
        identity_repo.create_identity_binding(
            issuer=command["issuer"],
            subject=command["subject"],
            user_id=user_id,
            created_at=now.isoformat(),
            created_by=command["command_id"],
        )
    except Exception as exc:
        latest = teacher_application_repo.get_activation_command(command["command_id"]) or command
        teacher_application_repo.update_activation_command(
            command["command_id"],
            expected_version=int(latest["version"]),
            status="provider_failed",
            updated_at=now.isoformat(),
            evidence_reference=f"teacher-activation:{command['command_id']}",
        )
        _audit(
            stream_id=command["application_id"],
            event_type="teacher_activation_deferred",
            actor_id=user_id,
            target_id=user_id,
            version=command["application_version"],
            reason_code="provider_step_incomplete",
            command_id=command["command_id"],
            created_at=now.isoformat(),
        )
        raise HTTPException(status_code=503, detail={"code": "activation_temporarily_unavailable"}) from exc

    active_profile = {**pending_profile, "account_status": "active", "updated_at": now.isoformat()}
    user_repo.put_user(active_profile)
    latest = teacher_application_repo.get_activation_command(command["command_id"]) or command
    completed = teacher_application_repo.update_activation_command(
        command["command_id"],
        expected_version=int(latest["version"]),
        status="active",
        updated_at=now.isoformat(),
        evidence_reference=f"teacher-activation:{command['command_id']}",
    )
    _audit(
        stream_id=command["application_id"],
        event_type="teacher_identity_activated",
        actor_id=user_id,
        target_id=user_id,
        version=command["application_version"],
        reason_code="identity_reconciled",
        evidence_reference=completed.get("evidence_reference"),
        command_id=command["command_id"],
        created_at=now.isoformat(),
    )
    return {
        "status": "active",
        "userId": user_id,
        "applicationId": command["application_id"],
        "applicationVersion": command["application_version"],
        "evidenceReference": completed.get("evidence_reference"),
    }


def _require_capability(actor: dict[str, Any], required: str) -> None:
    if actor.get("role") != "admin" or actor.get("account_status") != "active":
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})
    grants = actor.get("current_grants") or []
    from_current_grants = any(
        isinstance(grant, dict)
        and grant.get("capability") == required
        and grant.get("status") == "active"
        and int(grant.get("version") or 0) > 0
        for grant in grants
    )
    projected = actor.get("capabilities")
    from_actor_projection = isinstance(projected, dict) and (
        projected.get(required) is True or str(projected.get(required)).lower() == "granted"
    )
    if not from_current_grants and not from_actor_projection:
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})


def _audit(**event: Any) -> None:
    stream_id = str(event.pop("stream_id"))
    security_audit_repo.append_event(
        stream_id,
        {"event_id": f"event_{uuid4().hex}", **event},
    )


def _application_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "applicationId": item.get("application_id"),
        "version": int(item.get("version") or 0),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
    }


def _actor_id(actor: dict[str, Any]) -> str:
    value = str(actor.get("user_id") or actor.get("sub") or "").strip()
    if not value:
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})
    return value


def _token_digest(token: str) -> str:
    clean = str(token or "").strip()
    if not clean:
        raise HTTPException(status_code=409, detail={"code": "invitation_invalid"})
    return sha256(clean.encode("utf-8")).hexdigest()


def _email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if not email or "@" not in email or len(email) > 320:
        raise HTTPException(status_code=422, detail={"code": "valid_email_required"})
    return email


def _bounded(value: Any, limit: int, field: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or len(cleaned) > limit:
        raise HTTPException(status_code=422, detail={"code": "invalid_application_field", "field": field})
    return cleaned


def _subjects(value: Any) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise HTTPException(status_code=422, detail={"code": "invalid_application_field", "field": "subjects"})
    return [_bounded(item, 80, "subjects") for item in value]


def _timestamp(now: Callable[[], datetime] | None) -> str:
    return (now or (lambda: datetime.now(UTC)))().isoformat()


def _parse_timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
