"""Stable security failure taxonomy and deliberately small public projection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from stoa.rule_violation import (
    RuleContract,
    RuleViolation,
    current_correlation_id,
    normalize_correlation_id,
    register_codes,
)

__all__ = [
    "SECURITY_ERROR_REGISTRY",
    "SecurityDecisionError",
    "SecurityErrorCode",
    "normalize_correlation_id",
    "safe_error_body",
    "safe_error_response",
    "security_http_status",
]


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

    @property
    def contract(self) -> RuleContract:
        return SECURITY_ERROR_REGISTRY[self]


_C = SecurityErrorCode

# Retry-After goes with the two temporary outages: the identity provider's (the
# sign-in routes have always asked for 15 seconds) and the authorization
# store's (the upload routes have always asked for 30).
SECURITY_ERROR_REGISTRY: dict[SecurityErrorCode, RuleContract] = {
    _C.AUTHENTICATION_REQUIRED: RuleContract(401, "Please sign in to continue."),
    _C.INVALID_TOKEN: RuleContract(401, "Your session is not valid. Please sign in again."),
    _C.TOKEN_EXPIRED: RuleContract(401, "Your session has expired. Please sign in again."),
    _C.IDENTITY_CONFLICT: RuleContract(
        409, "Contact support and share the reference shown so we can restore your account."
    ),
    _C.PARENT_BINDING_REQUIRED: RuleContract(
        409, "Complete the parent connection before continuing."
    ),
    _C.TEACHER_REVIEW_PENDING: RuleContract(409, "Your teacher application is still under review."),
    _C.ACTION_NOT_ALLOWED: RuleContract(403, "You cannot perform this action."),
    _C.RESOURCE_NOT_FOUND: RuleContract(404, "The requested resource was not found."),
    _C.IDENTITY_PROVIDER_UNAVAILABLE: RuleContract(
        503,
        "Try again in a few minutes. If the problem continues, contact support and share the reference shown.",
        retry_after_seconds=15,
    ),
    _C.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: RuleContract(
        503,
        "This action is temporarily unavailable. Try again later.",
        retry_after_seconds=30,
    ),
    _C.INVALID_CREDENTIALS: RuleContract(
        401, "Check your email and password, then try signing in again."
    ),
    _C.EMAIL_VERIFICATION_REQUIRED: RuleContract(403, "Verify your email, then sign in again."),
    _C.ACCOUNT_DISABLED: RuleContract(
        403, "Contact support and share the reference shown to restore access to your account."
    ),
    _C.EMAIL_ALREADY_REGISTERED: RuleContract(
        409, "This email already has an account. Sign in instead, or reset your password."
    ),
    _C.PASSWORD_REQUIREMENTS_NOT_MET: RuleContract(
        400, "Choose a stronger password that meets the listed requirements, then try again."
    ),
    _C.VERIFICATION_CODE_INVALID: RuleContract(400, "Check the verification code and try again."),
    _C.VERIFICATION_CODE_EXPIRED: RuleContract(
        400, "Request a new verification code, then try again."
    ),
    _C.PASSWORD_RESET_REQUEST_INVALID: RuleContract(
        400, "Request a new password reset code, then try again."
    ),
    _C.AUTH_REQUEST_RATE_LIMITED: RuleContract(
        429, "Wait a few minutes before trying this action again."
    ),
}

register_codes("security", SecurityErrorCode, SECURITY_ERROR_REGISTRY)


@dataclass(slots=True)
class SecurityDecisionError(RuleViolation):
    """Internal error that never projects its diagnostic detail to a client."""

    code: SecurityErrorCode
    correlation_id: str | None = None
    internal_detail: str | None = None


def safe_error_body(
    code: SecurityErrorCode,
    correlation_id: str | None = None,
    **_ignored_sensitive_detail: Any,
) -> dict[str, object]:
    """Return the complete and only public security-error body.

    The id is the caller's, or the request's own; never one made up here.
    """
    return {
        "code": code.value,
        "message": code.contract.safe_message,
        "correlationId": normalize_correlation_id(correlation_id)
        if correlation_id
        else current_correlation_id(),
    }


def security_http_status(code: SecurityErrorCode) -> int:
    return code.contract.http_status


@dataclass(frozen=True, slots=True)
class SecurityHttpResponse:
    status_code: int
    body: dict[str, object]
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
        if code.contract.retry_after_seconds is None:
            raise ValueError("Retry-After is only valid for temporary dependency errors")
        if not 1 <= retry_after_seconds <= 120:
            raise ValueError("Retry-After must be between 1 and 120 seconds")
        headers["Retry-After"] = str(retry_after_seconds)
    return SecurityHttpResponse(
        status_code=security_http_status(code),
        body=safe_error_body(code, correlation_id, **sensitive_detail),
        headers=headers,
    )




def redacted_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    """Strip the echoed request body out of a 422 response.

    FastAPI puts the offending input in `input` and `ctx`, so a request that
    fails validation comes back carrying whatever was sent — including the
    plaintext password on the registration route. Only the field location and
    the message survive, which is all a client needs to point at the field.
    """
    safe = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        message = str(error.get("msg", ""))
        entry = {
            "type": str(error.get("type", "value_error")),
            "loc": list(error.get("loc", ())),
            "msg": message,
        }
        code = validation_message_code(message)
        if code:
            entry["code"] = code
        safe.append(entry)
    return safe


# The prose above is English. A client that ships other languages needs
# something stable to translate from, so the messages it is expected to show a
# person carry a code beside them.
_VALIDATION_MESSAGE_CODES: tuple[tuple[str, str], ...] = (
    ("Age must be a whole number", "age_out_of_range"),
    ("Parent name and parent email are required", "parent_contact_required"),
)


def validation_message_code(message: str) -> str | None:
    """A stable code for a message a client is expected to render."""
    for marker, code in _VALIDATION_MESSAGE_CODES:
        if marker in message:
            return code
    return None
