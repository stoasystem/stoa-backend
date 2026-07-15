"""Capability-bounded routine administrator and grant lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

from stoa.db.repositories import (
    capability_repo,
    identity_repo,
    privileged_identity_repo,
    security_audit_repo,
    user_repo,
)


def provision_admin(
    *,
    actor: dict[str, Any],
    command_id: str,
    target_email: str,
    issuer: str,
    subject: str,
    reason: str,
    provider: Any,
    user_pool_id: str = "",
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    _require_manager(actor)
    timestamp = _now(now)
    target_id = f"admin_{sha256(subject.strip().encode()).hexdigest()[:24]}"
    command, created = privileged_identity_repo.create_command(
        {
            "command_id": _required(command_id, "command_id"),
            "operation": "provision_admin",
            "target_id": target_id,
            "target_email": _email(target_email),
            "issuer": _required(issuer, "issuer").rstrip("/"),
            "subject": _required(subject, "subject"),
            "reason": _required(reason, "reason"),
            "approved_by": _actor_id(actor),
            "status": "approved",
            "version": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    if not created and command.get("status") == "active":
        return _command_response(command, idempotent=True)
    return _reconcile_admin(command, provider=provider, user_pool_id=user_pool_id, now=timestamp)


def change_admin_status(
    *,
    actor: dict[str, Any],
    command_id: str,
    target_id: str,
    operation: str,
    reason: str,
    provider: Any,
    provider_username: str,
    user_pool_id: str = "",
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    _require_manager(actor)
    if operation not in {"suspend", "revoke", "restore"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_identity_operation"})
    timestamp = _now(now)
    command, created = privileged_identity_repo.create_command(
        {
            "command_id": _required(command_id, "command_id"),
            "operation": operation,
            "target_id": _required(target_id, "target_id"),
            "issuer": "local-lifecycle",
            "subject": _required(provider_username, "provider_username"),
            "reason": _required(reason, "reason"),
            "approved_by": _actor_id(actor),
            "status": "approved",
            "version": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    terminal = {"suspend": "suspended", "revoke": "revoked", "restore": "active"}[operation]
    if not created and command.get("status") == terminal:
        return _command_response(command, idempotent=True)
    if operation == "restore":
        return _restore_admin(command, provider, user_pool_id=user_pool_id, now=timestamp)

    profile = user_repo.get_user(target_id)
    if not profile or profile.get("role") != "admin":
        raise HTTPException(status_code=404, detail={"code": "privileged_identity_not_found"})
    # Deny first. Provider removal/sign-out is defense in depth and cannot delay revocation.
    user_repo.put_user({**profile, "account_status": terminal, "updated_at": timestamp})
    provider_complete = True
    try:
        provider.admin_remove_user_from_group(
            UserPoolId=user_pool_id, Username=provider_username, GroupName="admins"
        )
        provider.admin_user_global_sign_out(UserPoolId=user_pool_id, Username=provider_username)
    except Exception:
        provider_complete = False
    updated = privileged_identity_repo.update_command(
        command_id,
        expected_version=int(command["version"]),
        status=terminal,
        updated_at=timestamp,
        evidence_reference=f"privileged-identity:{command_id}",
    )
    _audit(command, status=terminal, timestamp=timestamp, provider_complete=provider_complete)
    return {**_command_response(updated), "providerDefenseComplete": provider_complete}


def grant_capability(
    *, actor: dict[str, Any], target_id: str, reason: str, **grant: Any
) -> dict[str, Any]:
    _require_manager(actor)
    item = capability_repo.grant_capability(
        user_id=target_id,
        grantor_id=_actor_id(actor),
        reason=_required(reason, "reason"),
        **grant,
    )
    _audit_capability(actor, target_id, item, "capability_granted", reason)
    return _grant_response(item)


def revoke_capability(
    *, actor: dict[str, Any], target_id: str, reason: str, **grant: Any
) -> dict[str, Any]:
    _require_manager(actor)
    command_id = _required(grant.pop("command_id", None), "command_id")
    item = capability_repo.revoke_capability(
        user_id=target_id,
        actor_id=_actor_id(actor),
        reason=_required(reason, "reason"),
        action_id=command_id,
        **grant,
    )
    _audit_capability(actor, target_id, item, "capability_revoked", reason)
    return _grant_response(item)


def restore_capability(
    *, actor: dict[str, Any], target_id: str, reason: str, **grant: Any
) -> dict[str, Any]:
    _require_manager(actor)
    del target_id, reason, grant
    raise HTTPException(
        status_code=409,
        detail={
            "code": "capability_regrant_required",
            "message": "Issue a new approved capability grant command.",
        },
    )


def _reconcile_admin(
    command: dict[str, Any], *, provider: Any, user_pool_id: str, now: str
) -> dict[str, Any]:
    pending = {
        "user_id": command["target_id"],
        "email": command["target_email"],
        "role": "admin",
        "account_status": "pending_review",
        "identity_command_id": command["command_id"],
        "updated_at": now,
    }
    user_repo.put_user(pending)
    try:
        if hasattr(provider, "ensure_admin_identity"):
            provider.ensure_admin_identity(
                email=command["target_email"], target_id=command["target_id"], group="admins"
            )
        else:
            provider.admin_add_user_to_group(
                UserPoolId=user_pool_id, Username=command["subject"], GroupName="admins"
            )
        identity_repo.create_identity_binding(
            issuer=command["issuer"],
            subject=command["subject"],
            user_id=command["target_id"],
            created_at=now,
            created_by=command["command_id"],
        )
    except Exception as exc:
        _mark_provider_failed(command, now)
        raise HTTPException(status_code=503, detail={"code": "identity_change_temporarily_unavailable"}) from exc
    user_repo.put_user({**pending, "account_status": "active"})
    updated = privileged_identity_repo.update_command(
        command["command_id"],
        expected_version=int(command["version"]),
        status="active",
        updated_at=now,
        evidence_reference=f"privileged-identity:{command['command_id']}",
    )
    _audit(command, status="active", timestamp=now, provider_complete=True)
    return _command_response(updated)


def _restore_admin(command: dict[str, Any], provider: Any, *, user_pool_id: str, now: str) -> dict[str, Any]:
    profile = user_repo.get_user(command["target_id"])
    if not profile or profile.get("role") != "admin" or profile.get("account_status") == "deleted":
        raise HTTPException(status_code=409, detail={"code": "identity_restore_not_allowed"})
    try:
        provider.admin_add_user_to_group(
            UserPoolId=user_pool_id, Username=command["subject"], GroupName="admins"
        )
    except Exception as exc:
        _mark_provider_failed(command, now)
        raise HTTPException(status_code=503, detail={"code": "identity_change_temporarily_unavailable"}) from exc
    user_repo.put_user({**profile, "account_status": "active", "updated_at": now})
    updated = privileged_identity_repo.update_command(
        command["command_id"],
        expected_version=int(command["version"]),
        status="active",
        updated_at=now,
        evidence_reference=f"privileged-identity:{command['command_id']}",
    )
    _audit(command, status="active", timestamp=now, provider_complete=True)
    return _command_response(updated)


def _mark_provider_failed(command: dict[str, Any], timestamp: str) -> None:
    privileged_identity_repo.update_command(
        command["command_id"],
        expected_version=int(command["version"]),
        status="provider_failed",
        updated_at=timestamp,
        evidence_reference=f"privileged-identity:{command['command_id']}",
    )
    _audit(command, status="provider_failed", timestamp=timestamp, provider_complete=False)


def _require_manager(actor: dict[str, Any]) -> None:
    if actor.get("role") != "admin" or actor.get("account_status") != "active":
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})
    projected = actor.get("capabilities")
    allowed = isinstance(projected, dict) and (
        projected.get(capability_repo.ADMIN_IDENTITY_MANAGER) is True
        or str(projected.get(capability_repo.ADMIN_IDENTITY_MANAGER)).lower() == "granted"
    )
    grants = actor.get("current_grants") or []
    allowed = allowed or any(
        isinstance(grant, dict)
        and grant.get("capability") == capability_repo.ADMIN_IDENTITY_MANAGER
        and grant.get("status") == "active"
        and int(grant.get("version") or 0) > 0
        for grant in grants
    )
    if not allowed:
        raise HTTPException(status_code=403, detail={"code": "action_not_allowed"})


def _audit(command: dict[str, Any], *, status: str, timestamp: str, provider_complete: bool) -> None:
    security_audit_repo.append_event(
        command["target_id"],
        {
            "event_id": f"event_{uuid4().hex}",
            "event_type": f"admin_identity_{command['operation']}",
            "actor_id": command["approved_by"],
            "actor_role": "admin",
            "target_id": command["target_id"],
            "target_type": "admin_identity",
            "result_code": status,
            "version": command["version"],
            "reason_code": "approved_identity_command",
            "evidence_reference": f"privileged-identity:{command['command_id']}",
            "command_id": command["command_id"],
            "created_at": timestamp,
        },
    )
    del provider_complete  # deliberately not provider payload or text


def _audit_capability(
    actor: dict[str, Any], target_id: str, item: dict[str, Any], event_type: str, reason: str
) -> None:
    security_audit_repo.append_event(
        target_id,
        {
            "event_id": f"event_{uuid4().hex}",
            "event_type": event_type,
            "actor_id": _actor_id(actor),
            "actor_role": "admin",
            "target_id": target_id,
            "target_type": "capability_grant",
            "version": item.get("version"),
            "reason_code": "approved_capability_command",
            "evidence_reference": f"capability-grant:{item.get('grant_id')}",
            "created_at": item.get("updated_at") or item.get("effective_at"),
        },
    )
    del reason  # reason is retained on the grant, not copied into safe audit projection


def _command_response(command: dict[str, Any], *, idempotent: bool = False) -> dict[str, Any]:
    return {
        "commandId": command.get("command_id"),
        "targetId": command.get("target_id"),
        "operation": command.get("operation"),
        "status": command.get("status"),
        "evidenceReference": command.get("evidence_reference"),
        "idempotent": idempotent,
    }


def _grant_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "grantId": item.get("grant_id"),
        "targetId": item.get("user_id"),
        "capability": item.get("capability"),
        "scope": item.get("scope"),
        "status": item.get("status"),
        "version": item.get("version"),
        "generation": item.get("generation"),
    }


def _actor_id(actor: dict[str, Any]) -> str:
    return _required(actor.get("user_id") or actor.get("sub"), "actor_id")


def _required(value: Any, name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail={"code": "required_field", "field": name})
    return cleaned


def _email(value: Any) -> str:
    cleaned = _required(value, "target_email").casefold()
    if "@" not in cleaned or len(cleaned) > 320:
        raise HTTPException(status_code=422, detail={"code": "valid_email_required"})
    return cleaned


def _now(clock: Callable[[], datetime] | None) -> str:
    return (clock or (lambda: datetime.now(UTC)))().isoformat()
