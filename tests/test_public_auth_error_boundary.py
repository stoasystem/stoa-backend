from __future__ import annotations

from botocore.exceptions import ClientError
import pytest

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
