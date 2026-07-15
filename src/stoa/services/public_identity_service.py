"""Orchestration boundary for canonical public student and parent identities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from stoa.db.repositories import identity_repo, public_identity_repo, user_repo
from stoa.db.repositories.public_identity_repo import (
    PUBLIC_REGISTRATION_COMMAND,
    PUBLIC_ROLES,
    PublicIdentityCommandConflict,
    PublicIdentityCommandState,
)
from stoa.services import account_verification_service


PUBLIC_GROUPS = {"student": "students", "parent": "parents"}


class PublicIdentityDependencyError(RuntimeError):
    """A retryable provider or repository step interrupted convergence."""


def canonical_public_issuer(issuers: tuple[str, ...]) -> str:
    normalized = tuple(dict.fromkeys(value.strip().rstrip("/") for value in issuers if value.strip()))
    if len(normalized) != 1:
        raise PublicIdentityDependencyError("one canonical issuer is required")
    return normalized[0]


def provider_identity(provider: Any, *, user_pool_id: str, email: str) -> dict[str, Any]:
    """Read provider subject and verification state without mutating authority."""

    response = provider.admin_get_user(UserPoolId=user_pool_id, Username=email)
    attributes = {
        str(item.get("Name")): str(item.get("Value") or "")
        for item in response.get("UserAttributes") or []
        if item.get("Name")
    }
    subject = attributes.get("sub") or str(response.get("Username") or "").strip()
    return {
        "subject": subject,
        "status": str(response.get("UserStatus") or "").upper(),
        "email": str(attributes.get("email") or email).strip().casefold(),
        "email_verified": attributes.get("email_verified", "").lower() == "true",
        "enabled": response.get("Enabled", True) is True,
    }


def require_public_identity_command(email: str) -> PublicIdentityCommandState:
    command = public_identity_repo.get_public_identity_command(email)
    if (
        not command
        or command.role not in PUBLIC_ROLES
        or command.registration_command != PUBLIC_REGISTRATION_COMMAND
    ):
        raise PublicIdentityCommandConflict("public identity command is missing or invalid")
    return command


def get_completed_public_profile(command: PublicIdentityCommandState) -> dict[str, Any]:
    if not command.activation_complete:
        raise PublicIdentityCommandConflict("public identity command is not active")
    profile = user_repo.get_user(command.user_id)
    if not profile:
        raise PublicIdentityDependencyError("active public profile is missing")
    _require_matching_profile(profile, command)
    if profile.get("account_status") != "active":
        raise PublicIdentityCommandConflict("public profile is not active")
    return profile


def start_or_resume_public_registration(
    *,
    email: str,
    issuer: str,
    subject: str,
    user_id: str,
    role: str,
    profile: dict[str, Any],
    provider: Any,
    user_pool_id: str,
    now: Callable[[], datetime] | None = None,
) -> tuple[PublicIdentityCommandState, dict[str, Any]]:
    """Converge a public signup into a deny-first profile, binding, and group."""

    timestamp = _timestamp(now)
    command = public_identity_repo.create_or_get_public_identity_command(
        email=email,
        issuer=issuer,
        subject=subject,
        user_id=user_id,
        role=role,
        registration_command=PUBLIC_REGISTRATION_COMMAND,
        created_at=timestamp,
    )
    _require_fingerprint(command, issuer=issuer, subject=subject, user_id=user_id, role=role)

    existing = user_repo.get_user(command.user_id)
    pending = {
        **profile,
        "user_id": command.user_id,
        "email": command.email,
        "role": command.role,
        "registration_command": command.registration_command,
        "registration_role": command.role,
        "account_status": "pending_verification",
    }
    if existing:
        _require_matching_profile(existing, command)
        pending = dict(existing)
    elif not command.pending_profile_complete:
        user_repo.put_user(pending)
    command = _mark(command, "pending_profile_complete", timestamp)

    try:
        if not command.binding_complete:
            identity_repo.create_identity_binding(
                issuer=command.issuer,
                subject=command.subject,
                user_id=command.user_id,
                created_at=timestamp,
                created_by=PUBLIC_REGISTRATION_COMMAND,
            )
        command = _mark(command, "binding_complete", timestamp)
        if not command.canonical_group_complete:
            provider.admin_add_user_to_group(
                UserPoolId=user_pool_id,
                Username=command.email,
                GroupName=PUBLIC_GROUPS[command.role],
            )
        command = _mark(command, "canonical_group_complete", timestamp)
    except PublicIdentityCommandConflict:
        raise
    except identity_repo.IdentityBindingConflict as exc:
        raise PublicIdentityCommandConflict("public identity binding conflicts") from exc
    except Exception as exc:
        raise PublicIdentityDependencyError("public identity convergence is incomplete") from exc
    return command, pending


def confirm_and_reconcile_public_identity(
    *,
    email: str,
    issuer: str,
    provider_subject: str,
    provider_status: str,
    provider_email: str,
    provider_email_verified: bool,
    provider_enabled: bool,
    provider: Any,
    user_pool_id: str,
    now: Callable[[], datetime] | None = None,
) -> tuple[PublicIdentityCommandState, dict[str, Any]]:
    """Activate only after provider, command, group, profile, and binding converge."""

    command = require_public_identity_command(email)
    _require_fingerprint(
        command,
        issuer=issuer,
        subject=provider_subject,
        user_id=command.user_id,
        role=command.role,
    )
    if (
        provider_status.upper() != "CONFIRMED"
        or not provider_email_verified
        or not provider_enabled
        or provider_email.strip().casefold() != command.email
    ):
        raise PublicIdentityCommandConflict("provider identity is not confirmed")
    profile = user_repo.get_user(command.user_id)
    if not profile:
        raise PublicIdentityDependencyError("pending public profile is missing")
    _require_matching_profile(profile, command)
    timestamp = _timestamp(now)
    try:
        if not command.binding_complete:
            identity_repo.create_identity_binding(
                issuer=command.issuer,
                subject=command.subject,
                user_id=command.user_id,
                created_at=timestamp,
                created_by=PUBLIC_REGISTRATION_COMMAND,
            )
        command = _mark(command, "binding_complete", timestamp)
        if not command.canonical_group_complete:
            provider.admin_add_user_to_group(
                UserPoolId=user_pool_id,
                Username=command.email,
                GroupName=PUBLIC_GROUPS[command.role],
            )
        command = _mark(command, "canonical_group_complete", timestamp)
        command = _mark(command, "email_verification_complete", timestamp)
        if not command.activation_complete:
            fields = {
                **account_verification_service.verified_fields(timestamp),
                "account_status": "active",
            }
            profile = user_repo.update_email_verification_state(command.user_id, fields)
        command = _mark(command, "activation_complete", timestamp)
    except PublicIdentityCommandConflict:
        raise
    except identity_repo.IdentityBindingConflict as exc:
        raise PublicIdentityCommandConflict("public identity binding conflicts") from exc
    except Exception as exc:
        raise PublicIdentityDependencyError("public identity activation is incomplete") from exc
    return command, profile


def _mark(
    command: PublicIdentityCommandState, field: str, updated_at: str
) -> PublicIdentityCommandState:
    if getattr(command, field):
        return command
    return public_identity_repo.advance_public_identity_command(
        command.email,
        expected_version=command.version,
        updated_at=updated_at,
        **{field: True},
    )


def _require_fingerprint(
    command: PublicIdentityCommandState,
    *,
    issuer: str,
    subject: str,
    user_id: str,
    role: str,
) -> None:
    if (
        command.issuer != issuer.strip().rstrip("/")
        or command.subject != subject.strip()
        or command.user_id != user_id.strip()
        or command.role != role.strip()
        or command.registration_command != PUBLIC_REGISTRATION_COMMAND
    ):
        raise PublicIdentityCommandConflict("public identity fingerprint conflicts")


def _require_matching_profile(
    profile: dict[str, Any], command: PublicIdentityCommandState
) -> None:
    expected = {
        "user_id": command.user_id,
        "email": command.email,
        "role": command.role,
        "registration_command": command.registration_command,
        "registration_role": command.role,
    }
    if any(str(profile.get(key) or "").strip().casefold() != value.casefold() for key, value in expected.items()):
        raise PublicIdentityCommandConflict("public profile conflicts with command")


def _timestamp(now: Callable[[], datetime] | None) -> str:
    return (now or (lambda: datetime.now(UTC)))().isoformat()

__all__ = [
    "PUBLIC_REGISTRATION_COMMAND",
    "PUBLIC_ROLES",
    "PublicIdentityCommandConflict",
    "PublicIdentityCommandState",
    "PublicIdentityDependencyError",
    "canonical_public_issuer",
    "confirm_and_reconcile_public_identity",
    "provider_identity",
    "get_completed_public_profile",
    "require_public_identity_command",
    "start_or_resume_public_registration",
]
