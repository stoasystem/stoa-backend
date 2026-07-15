from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from types import SimpleNamespace

from stoa.config import Settings, get_settings
from stoa.routers import auth
from stoa.security.client_error_actions import CLIENT_ERROR_ACTIONS
from stoa.security.errors import SecurityErrorCode
from stoa.security.public_auth_errors import (
    PublicAuthOperation,
    normalize_cognito_failure,
    public_auth_error_response,
)


def _error(code: str, message: str = "provider-secret-canary") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "ProviderOperation")


@pytest.mark.parametrize(
    ("operation", "provider_code", "expected"),
    [
        (PublicAuthOperation.LOGIN, "NotAuthorizedException", SecurityErrorCode.INVALID_CREDENTIALS),
        (PublicAuthOperation.LOGIN, "UserNotConfirmedException", SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED),
        (PublicAuthOperation.REGISTER, "InvalidPasswordException", SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET),
        (PublicAuthOperation.VERIFICATION_CONFIRM, "ExpiredCodeException", SecurityErrorCode.VERIFICATION_CODE_EXPIRED),
        (PublicAuthOperation.RESET_PASSWORD, "CodeMismatchException", SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID),
        (PublicAuthOperation.RESET_PASSWORD, "InvalidPasswordException", SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET),
        (PublicAuthOperation.REFRESH, "NotAuthorizedException", SecurityErrorCode.INVALID_TOKEN),
    ],
)
def test_mapping_is_operation_aware_and_exhaustive(operation, provider_code, expected):
    failure = normalize_cognito_failure(operation, _error(provider_code), "corr-known")
    assert failure.code is expected
    assert failure.code in CLIENT_ERROR_ACTIONS


@pytest.mark.parametrize("operation", list(PublicAuthOperation))
def test_unknown_provider_failure_has_exact_fields_correlation_retry_and_redaction(operation):
    failure = normalize_cognito_failure(operation, _error("SecretUnknownCode"), "corr-unknown")
    response = public_auth_error_response(failure)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "15"
    assert response.headers["x-correlation-id"] == "corr-unknown"
    assert response.body == (
        b'{"code":"identity_provider_unavailable","message":"Try again in a few minutes. '
        b'If the problem continues, contact support and share the reference shown.",'
        b'"correlationId":"corr-unknown"}'
    )
    exposed = response.body.decode().lower()
    assert "secretunknowncode" not in exposed
    assert "provider-secret-canary" not in exposed
    assert "provideroperation" not in exposed
    assert set(failure.telemetry) == {
        "operation", "correlation_id", "category", "provider_code_digest"
    }
    assert "secretunknowncode" not in str(failure.telemetry).lower()
    assert "provider-secret-canary" not in str(failure.telemetry).lower()


def test_rate_limit_is_bounded_without_automatic_write_replay():
    failure = normalize_cognito_failure(
        PublicAuthOperation.REGISTER, _error("TooManyRequestsException"), "corr-rate"
    )
    response = public_auth_error_response(failure)
    assert response.status_code == 429
    assert "retry-after" not in response.headers
    assert CLIENT_ERROR_ACTIONS[failure.code].retry.automatic is False


@pytest.mark.parametrize(
    "provider_code",
    ["UserNotFoundException", "UserDisabledException", "NotAuthorizedException"],
)
def test_forgot_password_account_outcomes_are_accepted_not_public_errors(provider_code):
    failure = normalize_cognito_failure(
        PublicAuthOperation.FORGOT_PASSWORD, _error(provider_code), "corr-recovery"
    )
    assert failure.publicly_accepted is True
    with pytest.raises(ValueError, match="accepted provider outcomes"):
        public_auth_error_response(failure)


_UNKNOWN_CODE = "SecretUnknownProviderCode"
_UNKNOWN_MESSAGE = "email=secret@example.test token=secret-token pool=secret-pool"


class _FailingCognito:
    def __init__(self, failing_method: str):
        self.failing_method = failing_method

    def __getattr__(self, name: str):
        if name != self.failing_method:
            raise AssertionError(f"unexpected provider call: {name}")

        def fail(**_kwargs):
            raise _error(_UNKNOWN_CODE, _UNKNOWN_MESSAGE)

        return fail


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="offline-pool",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


@pytest.mark.parametrize(
    ("operation", "path", "payload", "provider_method"),
    [
        ("register", "/auth/register", {"email": "student@example.com", "password": "ValidPass123!", "role": "student"}, "sign_up"),
        ("login", "/auth/login", {"email": "student@example.com", "password": "ValidPass123!"}, "initiate_auth"),
        ("verification_resend", "/auth/email-verification/resend", {"email": "student@example.com"}, "resend_confirmation_code"),
        ("verification_confirm", "/auth/email-verification/confirm", {"email": "student@example.com", "confirmationCode": "123456"}, "confirm_sign_up"),
        ("forgot_password", "/auth/forgot-password", {"email": "student@example.com"}, "forgot_password"),
        ("reset_password", "/auth/reset-password", {"email": "student@example.com", "confirmationCode": "123456", "newPassword": "NewValidPass123!"}, "confirm_forgot_password"),
        ("refresh", "/auth/refresh", {"refresh_token": "secret-refresh"}, "initiate_auth"),
        ("logout", "/auth/logout", {"access_token": "secret-access"}, "global_sign_out"),
    ],
)
def test_every_public_auth_endpoint_redacts_unknown_provider_canary(
    operation, path, payload, provider_method, monkeypatch, caplog
):
    profile = {
        "user_id": "student-1",
        "email": "student@example.com",
        "role": "student",
        "registration_command": "public_self_service",
        "registration_role": "student",
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    }
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: _FailingCognito(provider_method))
    monkeypatch.setattr(auth.user_repo, "get_user_by_email", lambda _email: profile)
    monkeypatch.setattr(
        auth.public_identity_service,
        "require_public_identity_command",
        lambda _email: SimpleNamespace(user_id="student-1", activation_complete=False),
    )
    monkeypatch.setattr(
        auth.public_identity_service,
        "get_public_profile_for_command",
        lambda _command: profile,
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = _settings

    with caplog.at_level("WARNING", logger="stoa.security.public_auth_errors"):
        response = TestClient(app).post(path, json=payload)

    assert response.status_code == 503, operation
    assert response.json() == {
        "code": "identity_provider_unavailable",
        "message": "Try again in a few minutes. If the problem continues, contact support and share the reference shown.",
        "correlationId": response.headers["X-Correlation-ID"],
    }
    assert response.headers["Retry-After"] == "15"
    public_surface = response.content.decode().lower()
    telemetry = [record.public_auth for record in caplog.records if hasattr(record, "public_auth")]
    assert telemetry and telemetry[-1]["operation"] == operation
    combined = public_surface + str(telemetry).lower()
    for canary in (_UNKNOWN_CODE, _UNKNOWN_MESSAGE, "secret@example.test", "secret-token", "secret-pool"):
        assert canary.lower() not in combined


def test_generated_user_copy_is_actionable_and_provider_free():
    public_auth_codes = {
        SecurityErrorCode.IDENTITY_CONFLICT,
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        SecurityErrorCode.INVALID_CREDENTIALS,
        SecurityErrorCode.EMAIL_VERIFICATION_REQUIRED,
        SecurityErrorCode.ACCOUNT_DISABLED,
        SecurityErrorCode.EMAIL_ALREADY_REGISTERED,
        SecurityErrorCode.PASSWORD_REQUIREMENTS_NOT_MET,
        SecurityErrorCode.VERIFICATION_CODE_INVALID,
        SecurityErrorCode.VERIFICATION_CODE_EXPIRED,
        SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID,
        SecurityErrorCode.AUTH_REQUEST_RATE_LIMITED,
        SecurityErrorCode.INVALID_TOKEN,
    }
    for code in public_auth_codes:
        action = CLIENT_ERROR_ACTIONS[code]
        copy = action.safe_copy.lower()
        assert any(
            instruction in copy
            for instruction in ("sign in", "verify", "complete", "contact support", "try", "wait", "choose", "check", "request")
        ), code
        for forbidden in ("cognito", "provider", "pool", "client id", "access key", "group"):
            assert forbidden not in copy
