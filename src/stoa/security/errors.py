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
    render_message,
)
from stoa.models.user import REGISTRATION_MESSAGE_PARAMS, registration_message

__all__ = [
    "SECURITY_ERROR_REGISTRY",
    "SecurityClientAction",
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


class SecurityClientAction(StrEnum):
    """What a client does about a security refusal (was `client_error_actions.py`)."""

    REAUTHENTICATE = "reauthenticate"
    COMPLETE_PARENT_BINDING = "complete_parent_binding"
    WAIT_FOR_TEACHER_REVIEW = "wait_for_teacher_review"
    START_ACCOUNT_RECOVERY = "start_account_recovery"
    CONTACT_SUPPORT = "contact_support"
    RETRY_LATER = "retry_later"
    VERIFY_EMAIL = "verify_email"
    CORRECT_INPUT = "correct_input"
    REQUEST_NEW_CODE = "request_new_code"


_C = SecurityErrorCode
_A = SecurityClientAction


def _outage(action: SecurityClientAction, retry_after_seconds: int) -> RuleContract:
    """A temporary outage: an idempotent read may be retried twice, after the wait."""
    return RuleContract(
        503,
        action,
        retryable=True,
        idempotent_only=True,
        max_attempts=2,
        retry_after_seconds=retry_after_seconds,
    )


# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.security`).
#
# Retry-After goes with the two temporary outages: the identity provider's (the
# sign-in routes have always asked for 15 seconds) and the authorization
# store's (the upload routes have always asked for 30). An expired session is
# refreshed once, automatically. Forbidden and hidden resources carry no action:
# there is nothing for the client to do.
SECURITY_ERROR_REGISTRY: dict[SecurityErrorCode, RuleContract] = {
    _C.AUTHENTICATION_REQUIRED: RuleContract(401, _A.REAUTHENTICATE),
    _C.INVALID_TOKEN: RuleContract(401, _A.REAUTHENTICATE),
    _C.TOKEN_EXPIRED: RuleContract(401, _A.REAUTHENTICATE, retryable=True, max_attempts=1),
    _C.IDENTITY_CONFLICT: RuleContract(409, _A.START_ACCOUNT_RECOVERY),
    _C.PARENT_BINDING_REQUIRED: RuleContract(409, _A.COMPLETE_PARENT_BINDING),
    _C.TEACHER_REVIEW_PENDING: RuleContract(409, _A.WAIT_FOR_TEACHER_REVIEW),
    _C.ACTION_NOT_ALLOWED: RuleContract(403),
    _C.RESOURCE_NOT_FOUND: RuleContract(404),
    _C.IDENTITY_PROVIDER_UNAVAILABLE: _outage(_A.RETRY_LATER, 15),
    _C.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: _outage(_A.RETRY_LATER, 30),
    _C.INVALID_CREDENTIALS: RuleContract(401, _A.CORRECT_INPUT),
    _C.EMAIL_VERIFICATION_REQUIRED: RuleContract(403, _A.VERIFY_EMAIL),
    _C.ACCOUNT_DISABLED: RuleContract(403, _A.CONTACT_SUPPORT),
    _C.EMAIL_ALREADY_REGISTERED: RuleContract(409, _A.REAUTHENTICATE),
    _C.PASSWORD_REQUIREMENTS_NOT_MET: RuleContract(400, _A.CORRECT_INPUT),
    _C.VERIFICATION_CODE_INVALID: RuleContract(400, _A.CORRECT_INPUT),
    _C.VERIFICATION_CODE_EXPIRED: RuleContract(400, _A.REQUEST_NEW_CODE),
    _C.PASSWORD_RESET_REQUEST_INVALID: RuleContract(400, _A.START_ACCOUNT_RECOVERY),
    _C.AUTH_REQUEST_RATE_LIMITED: RuleContract(429, _A.RETRY_LATER),
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

    The id is the caller's, or the request's own; never one made up here. The
    message is in the request's language.
    """
    return {
        "code": code.value,
        "message": render_message(code),
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

    The messages a person is expected to read carry a code, and are rendered
    from the catalog in the request's language; the rest is pydantic's English.
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
            entry["msg"] = render_message(code, **REGISTRATION_MESSAGE_PARAMS[code])
        safe.append(entry)
    return safe


# A client that ships other languages needs something stable to translate
# from, so the messages it is expected to show a person carry a code. The
# validator raises the catalog's English sentence, which is how it is found.
VALIDATION_MESSAGE_CODES: tuple[str, ...] = tuple(REGISTRATION_MESSAGE_PARAMS)


def validation_message_code(message: str) -> str | None:
    """A stable code for a message a client is expected to render."""
    for code in VALIDATION_MESSAGE_CODES:
        if registration_message(code) in message:
            return code
    return None
