"""Stable security failure taxonomy and deliberately small public projection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any
from uuid import uuid4


class SecurityErrorCode(StrEnum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    IDENTITY_CONFLICT = "identity_conflict"
    PARENT_BINDING_REQUIRED = "parent_binding_required"
    TEACHER_REVIEW_PENDING = "teacher_review_pending"
    ACTION_NOT_ALLOWED = "action_not_allowed"
    RESOURCE_NOT_FOUND = "resource_not_found"
    IDENTITY_PROVIDER_UNAVAILABLE = "identity_provider_unavailable"
    AUTHORIZATION_TEMPORARILY_UNAVAILABLE = "authorization_temporarily_unavailable"
    INVALID_CREDENTIALS = "invalid_credentials"
    EMAIL_VERIFICATION_REQUIRED = "email_verification_required"
    ACCOUNT_DISABLED = "account_disabled"
    EMAIL_ALREADY_REGISTERED = "email_already_registered"
    PASSWORD_REQUIREMENTS_NOT_MET = "password_requirements_not_met"
    VERIFICATION_CODE_INVALID = "verification_code_invalid"
    VERIFICATION_CODE_EXPIRED = "verification_code_expired"
    PASSWORD_RESET_REQUEST_INVALID = "password_reset_request_invalid"
    AUTH_REQUEST_RATE_LIMITED = "auth_request_rate_limited"


_PUBLIC_MESSAGES: dict[SecurityErrorCode, str] = {
    SecurityErrorCode.AUTHENTICATION_REQUIRED: "Please sign in to continue.",
    SecurityErrorCode.INVALID_TOKEN: "Your session is not valid. Please sign in again.",
    SecurityErrorCode.TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
    SecurityErrorCode.IDENTITY_CONFLICT: "Contact support and share the reference shown so we can restore your account.",
    SecurityErrorCode.PARENT_BINDING_REQUIRED: "Complete the parent connection before continuing.",
    SecurityErrorCode.TEACHER_REVIEW_PENDING: "Your teacher application is still under review.",
    SecurityErrorCode.ACTION_NOT_ALLOWED: "You cannot perform this action.",
    SecurityErrorCode.RESOURCE_NOT_FOUND: "The requested resource was not found.",
    SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE: "Try again in a few minutes. If the problem continues, contact support and share the reference shown.",
    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: "This action is temporarily unavailable. Try again later.",
    SecurityErrorCode.INVALID_CREDENTIALS: "Check your email and password, then try signing in again.",
    SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED: "Verify your email, then sign in again.",
    SecurityErrorCode.ACCOUNT_DISABLED: "Contact support and share the reference shown to restore access to your account.",
    SecurityErrorCode.EMAIL_ALREADY_REGISTERED: "This email already has an account. Sign in instead, or reset your password.",
    SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET: "Choose a stronger password that meets the listed requirements, then try again.",
    SecurityErrorCode.VERIFICATION_CODE_INVALID: "Check the verification code and try again.",
    SecurityErrorCode.VERIFICATION_CODE_EXPIRED: "Request a new verification code, then try again.",
    SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID: "Request a new password reset code, then try again.",
    SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED: "Wait a few minutes before trying this action again.",
}

_HTTP_STATUS: dict[SecurityErrorCode, int] = {
    SecurityErrorCode.AUTHENTICATION_REQUIRED: 401,
    SecurityErrorCode.INVALID_TOKEN: 401,
    SecurityErrorCode.TOKEN_EXPIRED: 401,
    SecurityErrorCode.IDENTITY_CONFLICT: 409,
    SecurityErrorCode.PARENT_BINDING_REQUIRED: 409,
    SecurityErrorCode.TEACHER_REVIEW_PENDING: 409,
    SecurityErrorCode.ACTION_NOT_ALLOWED: 403,
    SecurityErrorCode.RESOURCE_NOT_FOUND: 404,
    SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE: 503,
    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: 503,
    SecurityErrorCode.INVALID_CREDENTIALS: 401,
    SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED: 403,
    SecurityErrorCode.ACCOUNT_DISABLED: 403,
    SecurityErrorCode.EMAIL_ALREADY_REGISTERED: 409,
    SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET: 400,
    SecurityErrorCode.VERIFICATION_CODE_INVALID: 400,
    SecurityErrorCode.VERIFICATION_CODE_EXPIRED: 400,
    SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID: 400,
    SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED: 429,
}

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def normalize_correlation_id(value: str | None) -> str:
    """Keep bounded opaque request IDs; replace malformed input without echoing it."""
    candidate = str(value or "").strip()
    return candidate if _CORRELATION_ID.fullmatch(candidate) else str(uuid4())


@dataclass(slots=True)
class SecurityDecisionError(Exception):
    """Internal error that never projects its diagnostic detail to a client."""

    code: SecurityErrorCode
    correlation_id: str | None = None
    internal_detail: str | None = None

    @property
    def status_code(self) -> int:
        return _HTTP_STATUS[self.code]

    def public_body(self) -> dict[str, str]:
        return safe_error_body(self.code, self.correlation_id)


def safe_error_body(
    code: SecurityErrorCode,
    correlation_id: str | None = None,
    **_ignored_sensitive_detail: Any,
) -> dict[str, str]:
    """Return the complete and only public security-error body."""
    return {
        "code": code.value,
        "message": _PUBLIC_MESSAGES[code],
        "correlationId": normalize_correlation_id(correlation_id),
    }


def security_http_status(code: SecurityErrorCode) -> int:
    return _HTTP_STATUS[code]


@dataclass(frozen=True, slots=True)
class SecurityHttpResponse:
    status_code: int
    body: dict[str, str]
    headers: dict[str, str]


def safe_error_response(
    code: SecurityErrorCode,
    correlation_id: str | None = None,
    *,
    retry_after_seconds: int | None = None,
    **sensitive_detail: Any,
) -> SecurityHttpResponse:
    """Create a safe transport projection, emitting Retry-After only for temporary outages."""
    headers: dict[str, str] = {}
    if retry_after_seconds is not None:
        if code not in {
            SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
            SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        }:
            raise ValueError("Retry-After is only valid for temporary dependency errors")
        if not 1 <= retry_after_seconds <= 120:
            raise ValueError("Retry-After must be between 1 and 120 seconds")
        headers["Retry-After"] = str(retry_after_seconds)
    return SecurityHttpResponse(
        status_code=security_http_status(code),
        body=safe_error_body(code, correlation_id, **sensitive_detail),
        headers=headers,
    )
