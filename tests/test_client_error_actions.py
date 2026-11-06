"""docs/security/client-error-actions.json is the code registry, written out (#273)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import generate_client_error_actions as generator
from stoa.rule_violation import catalog_key, registered_codes
from stoa.security.errors import SecurityClientAction, SecurityErrorCode, safe_error_response

_DOCUMENT = Path("docs/security/client-error-actions.json")


def test_generated_json_is_current_and_deterministic():
    rendered = generator.render()
    assert rendered == generator.render()
    assert rendered == _DOCUMENT.read_text(encoding="utf-8")


def test_every_registered_code_is_listed_with_its_contract():
    errors = generator.document()["errors"]
    registry = registered_codes()
    assert set(errors) == set(registry)
    for value, (domain, code) in registry.items():
        entry = errors[value]
        contract = code.contract
        assert entry["domain"] == domain
        assert entry["http_status"] == contract.http_status
        assert entry["message_key"] == catalog_key(code) == f"error.{value}"
        assert entry["retry"]["retryable"] is contract.retryable
        assert entry["retry"]["retry_after_seconds"] == contract.retry_after_seconds


def test_generated_json_names_no_internals_and_no_sentences():
    rendered = generator.render().lower()
    for forbidden in ("cognito", "dynamodb", "policy_version", "resource exists", "group"):
        assert forbidden not in rendered
    # The message is the catalog's; the contract document carries only its key.
    assert "sign in" not in rendered


def test_every_conflict_is_routed_to_recovery():
    recovering = {
        SecurityClientAction.COMPLETE_PARENT_BINDING,
        SecurityClientAction.WAIT_FOR_TEACHER_REVIEW,
        SecurityClientAction.START_ACCOUNT_RECOVERY,
        SecurityClientAction.REAUTHENTICATE,
    }
    for code in SecurityErrorCode:
        if code.contract.http_status == 409:
            assert code.contract.action in recovering, code


def test_expired_session_is_refreshed_once_and_nothing_else_retries_unasked():
    expired = SecurityErrorCode.TOKEN_EXPIRED.contract
    assert expired.retryable and expired.max_attempts == 1 and not expired.idempotent_only
    for code in SecurityErrorCode:
        contract = code.contract
        if code is SecurityErrorCode.TOKEN_EXPIRED:
            continue
        if contract.retryable:
            # Only an outage, only an idempotent read, only after the wait.
            assert contract.http_status == 503, code
            assert contract.idempotent_only and contract.retry_after_seconds, code


@pytest.mark.parametrize(
    "code", [SecurityErrorCode.ACTION_NOT_ALLOWED, SecurityErrorCode.RESOURCE_NOT_FOUND]
)
def test_forbidden_or_hidden_is_never_retried_and_has_nothing_to_do(code):
    assert code.contract.retryable is False
    assert code.contract.action is None


def test_password_reset_refusal_starts_recovery_without_replaying_the_write():
    contract = SecurityErrorCode.PASSWORD_RESET_REQUEST_INVALID.contract
    assert contract.action is SecurityClientAction.START_ACCOUNT_RECOVERY
    assert contract.retryable is False


def test_safe_error_retry_header_semantics_and_body_shape():
    response = safe_error_response(
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        "corr-503",
        retry_after_seconds=15,
        provider_payload="provider-canary",
    )
    assert response.headers == {"Retry-After": "15"}
    assert set(response.body) == {"code", "message", "correlationId"}
    assert response.body["code"] == "identity_provider_unavailable"
    assert response.body["correlationId"] == "corr-503"
    assert "provider-canary" not in json.dumps(response.body)
    with pytest.raises(ValueError):
        safe_error_response(SecurityErrorCode.ACTION_NOT_ALLOWED, retry_after_seconds=5)
