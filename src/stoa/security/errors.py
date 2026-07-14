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


_PUBLIC_MESSAGES: dict[SecurityErrorCode, str] = {
    SecurityErrorCode.AUTHENTICATION_REQUIRED: "Please sign in to continue.",
    SecurityErrorCode.INVALID_TOKEN: "Your session is not valid. Please sign in again.",
    SecurityErrorCode.TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
    SecurityErrorCode.IDENTITY_CONFLICT: "Your account needs recovery before you can continue.",
    SecurityErrorCode.PARENT_BINDING_REQUIRED: "Complete the parent connection before continuing.",
    SecurityErrorCode.TEACHER_REVIEW_PENDING: "Your teacher application is still under review.",
    SecurityErrorCode.ACTION_NOT_ALLOWED: "You cannot perform this action.",
    SecurityErrorCode.RESOURCE_NOT_FOUND: "The requested resource was not found.",
    SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE: "Sign-in is temporarily unavailable. Try again later.",
    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: "This action is temporarily unavailable. Try again later.",
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
}

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def normalize_correlation_id(value: str | None) -> str:
    """Keep bounded opaque request IDs; replace malformed input without echoing it."""
    candidate = str(value or "").strip()
    return candidate if _CORRELATION_ID.fullmatch(candidate) else str(uuid4())


@dataclass(frozen=True, slots=True)
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
