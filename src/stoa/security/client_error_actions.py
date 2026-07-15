"""Shared safe client recovery contract for structured security failures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
import random

from stoa.security.errors import SecurityErrorCode, security_http_status


CONTRACT_VERSION = "472.2"
MAX_RETRY_AFTER_SECONDS = 120
MAX_BACKOFF_SECONDS = 120.0


class ClientAction(StrEnum):
    REAUTHENTICATE = "reauthenticate"
    COMPLETE_PARENT_BINDING = "complete_parent_binding"
    WAIT_FOR_TEACHER_REVIEW = "wait_for_teacher_review"
    START_ACCOUNT_RECOVERY = "start_account_recovery"
    CONTACT_SUPPORT = "contact_support"
    RETRY_LATER = "retry_later"
    VERIFY_EMAIL = "verify_email"
    CORRECT_INPUT = "correct_input"
    REQUEST_NEW_CODE = "request_new_code"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    automatic: bool
    idempotent_reads_only: bool
    max_attempts: int
    requires_retry_after: bool
    user_resumption_with_idempotency_key: bool = False


@dataclass(frozen=True, slots=True)
class ClientErrorAction:
    message_key: str
    safe_copy: str
    action: ClientAction
    show_correlation_id: bool
    support_guidance: str
    http_statuses: tuple[int, ...]
    retry: RetryPolicy


_NO_RETRY = RetryPolicy(False, False, 0, False)
_OUTAGE_RETRY = RetryPolicy(True, True, 2, True, True)


def _entry(
    code: SecurityErrorCode,
    message_key: str,
    safe_copy: str,
    action: ClientAction,
    *,
    show_correlation_id: bool = False,
    retry: RetryPolicy = _NO_RETRY,
) -> ClientErrorAction:
    return ClientErrorAction(
        message_key=message_key,
        safe_copy=safe_copy,
        action=action,
        show_correlation_id=show_correlation_id,
        support_guidance=(
            "Share the correlation ID with support."
            if show_correlation_id
            else "Do not display internal authorization details."
        ),
        http_statuses=(security_http_status(code),),
        retry=retry,
    )


CLIENT_ERROR_ACTIONS: dict[SecurityErrorCode, ClientErrorAction] = {
    SecurityErrorCode.AUTHENTICATION_REQUIRED: _entry(
        SecurityErrorCode.AUTHENTICATION_REQUIRED,
        "security.sign_in_required",
        "Please sign in to continue.",
        ClientAction.REAUTHENTICATE,
    ),
    SecurityErrorCode.INVALID_TOKEN: _entry(
        SecurityErrorCode.INVALID_TOKEN,
        "security.session_invalid",
        "Your session is no longer valid. Please sign in again.",
        ClientAction.REAUTHENTICATE,
    ),
    SecurityErrorCode.TOKEN_EXPIRED: _entry(
        SecurityErrorCode.TOKEN_EXPIRED,
        "security.session_expired",
        "Your session expired. We will try once to restore it.",
        ClientAction.REAUTHENTICATE,
        retry=RetryPolicy(True, False, 1, False),
    ),
    SecurityErrorCode.IDENTITY_CONFLICT: _entry(
        SecurityErrorCode.IDENTITY_CONFLICT,
        "security.account_recovery_required",
        "Contact support and share the reference shown so we can restore your account.",
        ClientAction.START_ACCOUNT_RECOVERY,
        show_correlation_id=True,
    ),
    SecurityErrorCode.PARENT_BINDING_REQUIRED: _entry(
        SecurityErrorCode.PARENT_BINDING_REQUIRED,
        "security.parent_connection_required",
        "Complete the parent connection before continuing.",
        ClientAction.COMPLETE_PARENT_BINDING,
    ),
    SecurityErrorCode.TEACHER_REVIEW_PENDING: _entry(
        SecurityErrorCode.TEACHER_REVIEW_PENDING,
        "security.teacher_review_pending",
        "Your teacher application is still under review.",
        ClientAction.WAIT_FOR_TEACHER_REVIEW,
    ),
    SecurityErrorCode.ACTION_NOT_ALLOWED: _entry(
        SecurityErrorCode.ACTION_NOT_ALLOWED,
        "security.action_unavailable",
        "This action is not available for your account.",
        ClientAction.NONE,
    ),
    SecurityErrorCode.RESOURCE_NOT_FOUND: _entry(
        SecurityErrorCode.RESOURCE_NOT_FOUND,
        "security.resource_unavailable",
        "The requested item is unavailable.",
        ClientAction.NONE,
    ),
    SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE: _entry(
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        "security.sign_in_temporarily_unavailable",
        "Try again in a few minutes. If the problem continues, contact support and share the reference shown.",
        ClientAction.RETRY_LATER,
        show_correlation_id=True,
        retry=_OUTAGE_RETRY,
    ),
    SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE: _entry(
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        "security.action_temporarily_unavailable",
        "This action is temporarily unavailable. Try again shortly.",
        ClientAction.RETRY_LATER,
        show_correlation_id=True,
        retry=_OUTAGE_RETRY,
    ),
    SecurityErrorCode.INVALID_CREDENTIALS: _entry(
        SecurityErrorCode.INVALID_CREDENTIALS,
        "auth.invalid_credentials",
        "Check your email and password, then try signing in again.",
        ClientAction.CORRECT_INPUT,
    ),
    SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED: _entry(
        SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED,
        "auth.email_verification_required",
        "Verify your email, then sign in again.",
        ClientAction.VERIFY_EMAIL,
    ),
    SecurityErrorCode.ACCOUNT_DISABLED: _entry(
        SecurityErrorCode.ACCOUNT_DISABLED,
        "auth.account_disabled",
        "Contact support and share the reference shown to restore access to your account.",
        ClientAction.CONTACT_SUPPORT,
        show_correlation_id=True,
    ),
    SecurityErrorCode.EMAIL_ALREADY_REGISTERED: _entry(
        SecurityErrorCode.EMAIL_ALREADY_REGISTERED,
        "auth.email_already_registered",
        "This email already has an account. Sign in instead, or reset your password.",
        ClientAction.REAUTHENTICATE,
    ),
    SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET: _entry(
        SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET,
        "auth.password_requirements_not_met",
        "Choose a stronger password that meets the listed requirements, then try again.",
        ClientAction.CORRECT_INPUT,
    ),
    SecurityErrorCode.VERIFICATION_CODE_INVALID: _entry(
        SecurityErrorCode.VERIFICATION_CODE_INVALID,
        "auth.verification_code_invalid",
        "Check the verification code and try again.",
        ClientAction.CORRECT_INPUT,
    ),
    SecurityErrorCode.VERIFICATION_CODE_EXPIRED: _entry(
        SecurityErrorCode.VERIFICATION_CODE_EXPIRED,
        "auth.verification_code_expired",
        "Request a new verification code, then try again.",
        ClientAction.REQUEST_NEW_CODE,
    ),
    SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID: _entry(
        SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID,
        "auth.password_reset_request_invalid",
        "Request a new password reset code, then try again.",
        ClientAction.START_ACCOUNT_RECOVERY,
    ),
    SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED: _entry(
        SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED,
        "auth.request_rate_limited",
        "Wait a few minutes before trying this action again.",
        ClientAction.RETRY_LATER,
    ),
}

if set(CLIENT_ERROR_ACTIONS) != set(SecurityErrorCode):
    missing = set(SecurityErrorCode) - set(CLIENT_ERROR_ACTIONS)
    extra = set(CLIENT_ERROR_ACTIONS) - set(SecurityErrorCode)
    raise RuntimeError(f"client action registry is not exhaustive: missing={missing}, extra={extra}")


@dataclass(frozen=True, slots=True)
class ClientDecision:
    action: ClientAction
    automatically_retry: bool = False
    retry_delay_seconds: float | None = None
    consume_refresh_attempt: bool = False
    allow_user_resumption: bool = False


def interpret_client_error(
    code: SecurityErrorCode,
    *,
    method: str,
    refresh_attempts: int = 0,
    retry_after: str | None = None,
    idempotency_key: str | None = None,
    rng: random.Random | None = None,
) -> ClientDecision:
    """Reference interpreter proving bounded behavior; clients implement rendering in Phase 478."""
    mapping = CLIENT_ERROR_ACTIONS[code]
    if code is SecurityErrorCode.TOKEN_EXPIRED:
        return ClientDecision(
            action=mapping.action,
            automatically_retry=refresh_attempts == 0,
            consume_refresh_attempt=refresh_attempts == 0,
        )
    if security_http_status(code) in {403, 404}:
        return ClientDecision(action=mapping.action)
    if security_http_status(code) != 503:
        return ClientDecision(action=mapping.action)

    idempotent_read = method.upper() in {"GET", "HEAD", "OPTIONS"}
    parsed_retry_after = _parse_retry_after(retry_after)
    if not idempotent_read:
        return ClientDecision(
            action=mapping.action,
            allow_user_resumption=bool(idempotency_key),
        )
    if parsed_retry_after is None:
        return ClientDecision(action=mapping.action)
    jitter = (rng or random.Random()).uniform(0.8, 1.2)
    return ClientDecision(
        action=mapping.action,
        automatically_retry=True,
        retry_delay_seconds=min(parsed_retry_after * jitter, MAX_BACKOFF_SECONDS),
    )


def _parse_retry_after(value: str | None) -> int | None:
    try:
        seconds = int(value or "")
    except (TypeError, ValueError):
        return None
    return seconds if 1 <= seconds <= MAX_RETRY_AFTER_SECONDS else None


def client_error_actions_document() -> dict[str, object]:
    return {
        "schemaVersion": CONTRACT_VERSION,
        "ownership": {
            "contract": "Phase 472 generates and tests this shared behavior contract.",
            "rendering": "Phase 478 owns web and mobile rendering and application integration.",
        },
        "errors": {
            code.value: {
                **asdict(action),
                "action": action.action.value,
                "http_statuses": list(action.http_statuses),
            }
            for code, action in sorted(CLIENT_ERROR_ACTIONS.items(), key=lambda item: item[0].value)
        },
    }


def render_client_error_actions() -> str:
    return json.dumps(client_error_actions_document(), indent=2, sort_keys=True) + "\n"
