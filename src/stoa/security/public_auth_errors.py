"""Closed, redacted boundary for failures from the public identity provider."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import blake2s
import logging
import secrets

from botocore.exceptions import ClientError
from fastapi.responses import JSONResponse

from stoa.security.errors import SecurityErrorCode, safe_error_response


logger = logging.getLogger(__name__)
_DIGEST_KEY = secrets.token_bytes(32)
_RETRY_AFTER_SECONDS = 15


class PublicAuthOperation(StrEnum):
    REGISTER = "register"
    LOGIN = "login"
    VERIFICATION_RESEND = "verification_resend"
    VERIFICATION_CONFIRM = "verification_confirm"
    FORGOT_PASSWORD = "forgot_password"
    RESET_PASSWORD = "reset_password"
    REFRESH = "refresh"
    LOGOUT = "logout"


@dataclass(frozen=True, slots=True)
class NormalizedPublicAuthFailure:
    operation: PublicAuthOperation
    code: SecurityErrorCode
    correlation_id: str
    category: str
    provider_code_digest: str
    retry_after_seconds: int | None = None
    publicly_accepted: bool = False

    @property
    def telemetry(self) -> dict[str, str]:
        return {
            "operation": self.operation.value,
            "correlation_id": self.correlation_id,
            "category": self.category,
            "provider_code_digest": self.provider_code_digest,
        }


_COMMON: dict[str, tuple[SecurityErrorCode, str]] = {
    "UserDisabledException": (SecurityErrorCode.ACCOUNT_DISABLED, "account_disabled"),
    "LimitExceededException": (SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED, "rate_limited"),
    "TooManyRequestsException": (SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED, "rate_limited"),
}

_OPERATION_MAPPINGS: dict[PublicAuthOperation, dict[str, tuple[SecurityErrorCode, str]]] = {
    PublicAuthOperation.REGISTER: {
        "UsernameExistsException": (SecurityErrorCode.EMAIL_ALREADY_REGISTERED, "account_exists"),
        "InvalidPasswordException": (SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET, "password_policy"),
        "InvalidParameterException": (SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET, "password_policy"),
    },
    PublicAuthOperation.LOGIN: {
        "NotAuthorizedException": (SecurityErrorCode.INVALID_CREDENTIALS, "invalid_credentials"),
        "UserNotFoundException": (SecurityErrorCode.INVALID_CREDENTIALS, "invalid_credentials"),
        "UserNotConfirmedException": (SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED, "verification_required"),
    },
    PublicAuthOperation.VERIFICATION_RESEND: {},
    PublicAuthOperation.VERIFICATION_CONFIRM: {
        "CodeMismatchException": (SecurityErrorCode.VERIFICATION_CODE_INVALID, "invalid_code"),
        "InvalidParameterException": (SecurityErrorCode.VERIFICATION_CODE_INVALID, "invalid_code"),
        "NotAuthorizedException": (SecurityErrorCode.VERIFICATION_CODE_INVALID, "invalid_code"),
        "UserNotFoundException": (SecurityErrorCode.VERIFICATION_CODE_INVALID, "invalid_code"),
        "ExpiredCodeException": (SecurityErrorCode.VERIFICATION_CODE_EXPIRED, "expired_code"),
    },
    PublicAuthOperation.FORGOT_PASSWORD: {
        "UserNotFoundException": (
            SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID,
            "recovery_accepted",
        ),
        "UserDisabledException": (
            SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID,
            "recovery_accepted",
        ),
        "NotAuthorizedException": (
            SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID,
            "recovery_accepted",
        ),
    },
    PublicAuthOperation.RESET_PASSWORD: {
        "CodeMismatchException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
        "ExpiredCodeException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
        "UserDisabledException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
        "NotAuthorizedException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
        "InvalidPasswordException": (SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET, "password_policy"),
        "InvalidParameterException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
        "UserNotFoundException": (SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID, "invalid_reset"),
    },
    PublicAuthOperation.REFRESH: {
        "NotAuthorizedException": (SecurityErrorCode.INVALID_TOKEN, "invalid_token"),
    },
    PublicAuthOperation.LOGOUT: {
        "NotAuthorizedException": (SecurityErrorCode.INVALID_TOKEN, "invalid_token"),
    },
}


def _provider_code(error: ClientError) -> str:
    value = error.response.get("Error", {}).get("Code")
    return str(value or "unknown")


def _provider_code_digest(code: str) -> str:
    return blake2s(code.encode("utf-8"), key=_DIGEST_KEY, digest_size=12).hexdigest()


def normalize_cognito_failure(
    operation: PublicAuthOperation,
    error: ClientError,
    correlation_id: str,
) -> NormalizedPublicAuthFailure:
    """Normalize only allowlisted provider codes; everything else fails safely closed."""
    provider_code = _provider_code(error)
    mapped = _OPERATION_MAPPINGS[operation].get(provider_code) or _COMMON.get(provider_code)
    if mapped is None:
        code, category = SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE, "provider_unavailable"
        retry_after = _RETRY_AFTER_SECONDS
    else:
        code, category = mapped
        retry_after = None
    failure = NormalizedPublicAuthFailure(
        operation=operation,
        code=code,
        correlation_id=correlation_id,
        category=category,
        provider_code_digest=_provider_code_digest(provider_code),
        retry_after_seconds=retry_after,
        publicly_accepted=(
            operation is PublicAuthOperation.FORGOT_PASSWORD
            and category == "recovery_accepted"
        ),
    )
    logger.warning("public_auth_provider_failure", extra={"public_auth": failure.telemetry})
    return failure


def public_auth_error_response(failure: NormalizedPublicAuthFailure) -> JSONResponse:
    if failure.publicly_accepted:
        raise ValueError("accepted provider outcomes cannot be projected as public errors")
    safe = safe_error_response(
        failure.code,
        failure.correlation_id,
        retry_after_seconds=failure.retry_after_seconds,
    )
    return JSONResponse(
        status_code=safe.status_code,
        content=safe.body,
        headers={**safe.headers, "X-Correlation-ID": failure.correlation_id},
    )
