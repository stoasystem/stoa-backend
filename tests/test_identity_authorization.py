from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    ResourceType,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode, safe_error_body
from stoa.security.events import contains_canary, project_security_event
from stoa.security.identity import AccountStatus, Actor, CanonicalRole


async def _resolver(_resource_id: str):
    return {"exists": True}


def actor_contract(role: CanonicalRole = CanonicalRole.STUDENT, status=AccountStatus.ACTIVE):
    group = role.value if isinstance(role, CanonicalRole) else "student"
    return Actor(
        user_id="user-1",
        issuer="https://issuer.example",
        subject="subject-1",
        role=role,
        account_status=status,
        cognito_group=group,
        auth_context={"token_use": "access"},
    )


def test_actor_contract_is_single_role_immutable_and_active_only_authorizes():
    actor = actor_contract()
    assert actor.can_authorize is True
    with pytest.raises((ValueError, TypeError)):
        actor_contract(role="tutor")
    with pytest.raises((ValueError, TypeError)):
        actor_contract(role=["student", "admin"])
    assert actor_contract(status=AccountStatus.SUSPENDED).can_authorize is False
    with pytest.raises(FrozenInstanceError):
        actor.user_id = "changed"


def test_safe_error_contract_has_exact_fields_and_drops_internal_detail():
    canary = "provider-debug-token-canary"
    error = SecurityDecisionError(
        SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE,
        "corr-123",
        internal_detail=canary,
    )
    assert error.status_code == 503
    assert error.public_body() == {
        "code": "identity_provider_unavailable",
        "message": "Sign-in is temporarily unavailable. Try again later.",
        "correlationId": "corr-123",
    }
    assert canary not in repr(error.public_body())
    assert set(safe_error_body(SecurityErrorCode.ACTION_NOT_ALLOWED)) == {
        "code",
        "message",
        "correlationId",
    }


def test_security_event_contract_is_allowlisted_and_redacts_canaries():
    canaries = ("token-canary", "student-content-canary", "object/key/canary")
    projected = project_security_event(
        {
            "actor_id": "actor-1",
            "canonical_role": "teacher",
            "resource_type": "question",
            "action": "read",
            "purpose": "teacher_help",
            "policy_version": "472.v1",
            "result_code": "action_not_allowed",
            "correlation_id": "corr-1",
            "evidence_reference": "evidence-1",
            "token": canaries[0],
            "email": "student-content-canary",
            "provider_payload": {"key": canaries[2]},
        }
    )
    assert set(projected) == {
        "actor_id",
        "canonical_role",
        "resource_type",
        "action",
        "purpose",
        "policy_version",
        "result_code",
        "correlation_id",
        "evidence_reference",
    }
    assert contains_canary(projected, canaries) is False


def test_authorization_contract_requires_classification_and_resolver():
    spec = AuthorizationSpec(
        resource_type=ResourceType.QUESTION,
        action=AuthorizationAction.READ,
        purpose=AuthorizationPurpose.TEACHER_HELP,
        resolver=_resolver,
    )
    assert spec.resolver is _resolver
    with pytest.raises(TypeError):
        AuthorizationSpec(resource_type=ResourceType.QUESTION, action=AuthorizationAction.READ)
    with pytest.raises(ValueError):
        AuthorizationSpec(
            resource_type=ResourceType.QUESTION,
            action=AuthorizationAction.READ,
            purpose=AuthorizationPurpose.TEACHER_HELP,
            resolver=None,
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing-binding",
        "multiple-groups",
        "group-role-mismatch",
        "revoked-current-grant",
        "authorization-store-outage",
    ],
    ids=lambda value: f"T-472-03-identity-{value}",
)
def test_identity_authorization_future_fail_closed_cases(case):
    """Red executable surface for Plans 02 and 05; no fallback can become allow."""
    from stoa.security.identity_resolution import evaluate_identity_case

    decision = evaluate_identity_case(case)
    assert decision.allowed is False
    assert decision.code in {
        SecurityErrorCode.IDENTITY_CONFLICT,
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
    }
