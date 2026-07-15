from __future__ import annotations

import random

import pytest

from stoa.security.client_error_actions import (
    CLIENT_ERROR_ACTIONS,
    ClientAction,
    client_error_actions_document,
    interpret_client_error,
    render_client_error_actions,
)
from stoa.security.errors import SecurityErrorCode, safe_error_response


def test_client_action_contract_exhaustively_covers_error_enum():
    assert set(CLIENT_ERROR_ACTIONS) == set(SecurityErrorCode)
    assert all(len(mapping.http_statuses) == 1 for mapping in CLIENT_ERROR_ACTIONS.values())
    assert all(mapping.safe_copy and mapping.message_key for mapping in CLIENT_ERROR_ACTIONS.values())


def test_client_action_contract_routes_every_conflict_to_recovery():
    for code, mapping in CLIENT_ERROR_ACTIONS.items():
        if 409 in mapping.http_statuses:
            assert mapping.action in {
                ClientAction.COMPLETE_PARENT_BINDING,
                ClientAction.WAIT_FOR_TEACHER_REVIEW,
                ClientAction.START_ACCOUNT_RECOVERY,
                ClientAction.REAUTHENTICATE,
            }


def test_client_action_refreshes_expired_token_exactly_once():
    first = interpret_client_error(SecurityErrorCode.TOKEN_EXPIRED, method="GET")
    second = interpret_client_error(
        SecurityErrorCode.TOKEN_EXPIRED, method="GET", refresh_attempts=1
    )
    assert first.automatically_retry is True and first.consume_refresh_attempt is True
    assert second.automatically_retry is False and second.action is ClientAction.REAUTHENTICATE


@pytest.mark.parametrize(
    "code", [SecurityErrorCode.ACTION_NOT_ALLOWED, SecurityErrorCode.RESOURCE_NOT_FOUND]
)
def test_client_action_never_retries_forbidden_or_hidden(code):
    decision = interpret_client_error(code, method="GET", retry_after="10")
    assert decision.automatically_retry is False


def test_client_action_retry_is_bounded_to_idempotent_reads():
    read = interpret_client_error(
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        method="GET",
        retry_after="20",
        rng=random.Random(7),
    )
    assert read.automatically_retry is True
    assert read.retry_delay_seconds is not None
    assert 16 <= read.retry_delay_seconds <= 24

    write = interpret_client_error(
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        method="POST",
        retry_after="20",
        idempotency_key="explicit-resume-key",
    )
    assert write.automatically_retry is False
    assert write.allow_user_resumption is True


@pytest.mark.parametrize("retry_after", [None, "0", "121", "tomorrow"])
def test_client_action_rejects_invalid_retry_after(retry_after):
    decision = interpret_client_error(
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        method="GET",
        retry_after=retry_after,
    )
    assert decision.automatically_retry is False


def test_safe_error_retry_header_semantics_and_body_shape():
    response = safe_error_response(
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        "corr-503",
        retry_after_seconds=15,
        provider_payload="provider-canary",
    )
    assert response.headers == {"Retry-After": "15"}
    assert response.body == {
        "code": "identity_provider_unavailable",
        "message": "Try again in a few minutes. If the problem continues, contact support and share the reference shown.",
        "correlationId": "corr-503",
    }
    with pytest.raises(ValueError):
        safe_error_response(SecurityErrorCode.ACTION_NOT_ALLOWED, retry_after_seconds=5)


def test_client_action_generated_json_is_deterministic_and_safe():
    expected = render_client_error_actions()
    assert expected == render_client_error_actions()
    assert expected == open("docs/security/client-error-actions.json", encoding="utf-8").read()
    lowered = expected.lower()
    for forbidden in ("cognito", "dynamodb", "policy_version", "resource exists", "group"):
        assert forbidden not in lowered
    ownership = client_error_actions_document()["ownership"]
    assert "Phase 478" in ownership["rendering"]
