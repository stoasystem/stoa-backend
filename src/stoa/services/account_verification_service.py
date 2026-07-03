"""Email verification policy helpers for Cognito-backed account lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


EMAIL_VERIFICATION_POLICY = "cognito_sign_up_confirm_sign_up"
LOGIN_CODE_POLICY = "deferred_cognito_custom_auth_required"
RESEND_COOLDOWN_SECONDS = 60

STATUS_REGISTERED = "registered"
STATUS_UNVERIFIED = "unverified"
STATUS_PENDING = "pending_verification"
STATUS_VERIFIED = "verified"
STATUS_EXPIRED = "expired_verification"
STATUS_RESEND_LIMITED = "resend_limited"
STATUS_BLOCKED = "blocked"
STATUS_LEGACY_ADMIN_VERIFIED = "admin_marked_verified"

ACTIVE = "active"
PENDING_EMAIL = "pending_email_verification"
LIMITED = "limited_onboarding"
BLOCKED = "blocked"

VERIFIED_STATUSES = {STATUS_VERIFIED, STATUS_LEGACY_ADMIN_VERIFIED}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def verification_status(profile: dict[str, Any] | None) -> str:
    if not profile:
        return STATUS_UNVERIFIED
    return (
        profile.get("email_verification_status")
        or profile.get("emailVerificationStatus")
        or STATUS_LEGACY_ADMIN_VERIFIED
    )


def is_email_verified(profile: dict[str, Any] | None) -> bool:
    return verification_status(profile) in VERIFIED_STATUSES


def email_verification_required(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return True
    if "email_verification_required" in profile:
        return bool(profile.get("email_verification_required"))
    return verification_status(profile) not in VERIFIED_STATUSES


def account_activation_status(profile: dict[str, Any] | None) -> str:
    status = verification_status(profile)
    if status in VERIFIED_STATUSES:
        return ACTIVE
    if status == STATUS_BLOCKED:
        return BLOCKED
    if status in {STATUS_PENDING, STATUS_REGISTERED, STATUS_UNVERIFIED, STATUS_EXPIRED}:
        return PENDING_EMAIL
    if status == STATUS_RESEND_LIMITED:
        return LIMITED
    return PENDING_EMAIL


def can_return_tokens(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return is_email_verified(profile) or not email_verification_required(profile)


def registration_profile_fields(now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now_iso()
    return {
        "account_registration_status": STATUS_REGISTERED,
        "account_activation_status": PENDING_EMAIL,
        "email_verification_status": STATUS_PENDING,
        "email_verification_policy": EMAIL_VERIFICATION_POLICY,
        "email_verification_required": True,
        "email_verification_requested_at": timestamp,
        "email_verification_updated_at": timestamp,
        "email_verification_resend_count": 0,
    }


def verified_fields(now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now_iso()
    return {
        "email_verification_status": STATUS_VERIFIED,
        "account_activation_status": ACTIVE,
        "email_verification_required": False,
        "email_verified_at": timestamp,
        "email_verification_updated_at": timestamp,
    }


def expired_fields(now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now_iso()
    return {
        "email_verification_status": STATUS_EXPIRED,
        "account_activation_status": PENDING_EMAIL,
        "email_verification_required": True,
        "email_verification_updated_at": timestamp,
    }


def resend_limited_fields(now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now_iso()
    return {
        "email_verification_status": STATUS_RESEND_LIMITED,
        "account_activation_status": LIMITED,
        "email_verification_required": True,
        "email_verification_updated_at": timestamp,
    }


def resend_record_fields(profile: dict[str, Any], now: str | None = None) -> dict[str, Any]:
    timestamp = now or utc_now_iso()
    return {
        "email_verification_status": STATUS_PENDING,
        "account_activation_status": PENDING_EMAIL,
        "email_verification_required": True,
        "email_verification_last_resend_at": timestamp,
        "email_verification_updated_at": timestamp,
        "email_verification_resend_count": int(profile.get("email_verification_resend_count") or 0) + 1,
    }


def resend_allowed(profile: dict[str, Any], now: datetime | None = None) -> bool:
    last_resend = parse_iso(profile.get("email_verification_last_resend_at"))
    if not last_resend:
        return True
    current = now or datetime.now(timezone.utc)
    if last_resend.tzinfo is None:
        last_resend = last_resend.replace(tzinfo=timezone.utc)
    return current - last_resend >= timedelta(seconds=RESEND_COOLDOWN_SECONDS)


def binding_status_for_profiles(
    new_profile: dict[str, Any],
    existing_profile: dict[str, Any] | None,
) -> str:
    if not is_email_verified(new_profile) or (
        existing_profile is not None and not is_email_verified(existing_profile)
    ):
        return "active_pending_verification"
    return "active"


def public_state(profile: dict[str, Any]) -> dict[str, Any]:
    status = verification_status(profile)
    return {
        "emailVerificationStatus": status,
        "emailVerificationRequired": email_verification_required(profile),
        "accountActivationStatus": account_activation_status(profile),
        "emailVerificationPolicy": profile.get(
            "email_verification_policy",
            EMAIL_VERIFICATION_POLICY if status not in VERIFIED_STATUSES else "legacy_or_verified",
        ),
        "emailVerifiedAt": profile.get("email_verified_at"),
        "emailVerificationRequestedAt": profile.get("email_verification_requested_at"),
        "emailVerificationLastResendAt": profile.get("email_verification_last_resend_at"),
        "emailVerificationResendCount": int(profile.get("email_verification_resend_count") or 0),
        "resendAllowed": resend_allowed(profile) and status not in VERIFIED_STATUSES,
    }


def support_summary(profile: dict[str, Any]) -> dict[str, Any]:
    state = public_state(profile)
    return {
        "userId": profile.get("user_id", ""),
        "email": profile.get("email", ""),
        "role": profile.get("role", ""),
        "parentBindingStatus": profile.get("parent_binding_status")
        or profile.get("child_binding_status"),
        **state,
    }
