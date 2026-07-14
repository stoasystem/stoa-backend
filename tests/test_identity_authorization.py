from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

from botocore.exceptions import ClientError
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
from stoa.security.identity import resolve_actor
from stoa.security.tokens import VerifiedAccessToken


class FakeIdentityRepository:
    def __init__(self, *, binding=None, account=None, grants=None, error=None):
        self.binding = binding
        self.account = account
        self.grants = list(grants or [])
        self.error = error
        self.reads = []

    async def get_binding(self, issuer, subject):
        self.reads.append(("binding", issuer, subject))
        if self.error:
            raise self.error
        return self.binding

    async def get_account(self, user_id):
        self.reads.append(("account", user_id))
        if self.error:
            raise self.error
        return self.account

    async def get_current_grants(self, user_id):
        self.reads.append(("grants", user_id))
        if self.error:
            raise self.error
        return self.grants


def verified_token(*groups):
    return VerifiedAccessToken(
        issuer="https://identity.test/primary",
        subject="subject-1",
        client_id="student-client",
        groups=groups or ("students",),
    )


def active_repository(**overrides):
    values = {
        "binding": {"status": "active", "user_id": "student-1"},
        "account": {
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "email": "not-an-identity@example.invalid",
            "capabilities": ["cannot-broaden"],
        },
        "grants": [
            {
                "capability": "student_support_lookup",
                "scope": "student:student-1",
                "version": 2,
                "status": "active",
            },
            {
                "capability": "revoked_capability",
                "scope": "*",
                "version": 3,
                "status": "revoked",
            },
        ],
    }
    values.update(overrides)
    return FakeIdentityRepository(**values)


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


@pytest.mark.asyncio
async def test_identity_resolves_only_binding_one_group_active_role_and_fresh_grants():
    repository = active_repository()

    actor = await resolve_actor(verified_token("students", "unrelated-group"), repository)

    assert actor.user_id == "student-1"
    assert actor.role is CanonicalRole.STUDENT
    assert [grant.capability for grant in actor.current_grants] == ["student_support_lookup"]
    assert repository.reads == [
        ("binding", "https://identity.test/primary", "subject-1"),
        ("account", "student-1"),
        ("grants", "student-1"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "repository"),
    [
        (verified_token("students"), active_repository(binding=None)),
        (verified_token("students", "admins"), active_repository()),
        (verified_token("unrelated-group"), active_repository()),
        (verified_token("tutor"), active_repository()),
        (verified_token("admins"), active_repository()),
        (
            verified_token("students"),
            active_repository(account={"role": "student", "account_status": "suspended"}),
        ),
        (
            verified_token("students"),
            active_repository(account={"role": "tutor", "account_status": "active"}),
        ),
    ],
)
async def test_identity_conflicts_never_fallback_or_select_highest_role(token, repository):
    with pytest.raises(SecurityDecisionError) as exc_info:
        await resolve_actor(token, repository)
    assert exc_info.value.code is SecurityErrorCode.IDENTITY_CONFLICT
    assert all(read[0] != "email" for read in repository.reads)


@pytest.mark.asyncio
async def test_identity_repository_outage_is_temporary_authorization_failure():
    repository = active_repository(error=TimeoutError("offline"))
    with pytest.raises(SecurityDecisionError) as exc_info:
        await resolve_actor(verified_token(), repository)
    assert exc_info.value.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
    assert "offline" not in repr(exc_info.value.public_body())


@pytest.mark.asyncio
async def test_identity_status_and_grant_revocation_apply_on_next_resolution():
    repository = active_repository()
    first = await resolve_actor(verified_token(), repository)
    assert len(first.current_grants) == 1

    repository.grants[0]["status"] = "revoked"
    second = await resolve_actor(verified_token(), repository)
    assert second.current_grants == ()

    repository.account["account_status"] = "suspended"
    with pytest.raises(SecurityDecisionError) as exc_info:
        await resolve_actor(verified_token(), repository)
    assert exc_info.value.code is SecurityErrorCode.IDENTITY_CONFLICT


def test_capability_grant_version_conflict_and_current_filtering(monkeypatch):
    from stoa.db.repositories import capability_repo

    class FakeTable:
        def __init__(self):
            self.items = {}

        def put_item(self, *, Item, ConditionExpression):
            key = (Item["PK"], Item["SK"])
            if key in self.items:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
                )
            self.items[key] = dict(Item)

        def update_item(self, *, Key, ExpressionAttributeValues, **_kwargs):
            key = (Key["PK"], Key["SK"])
            item = self.items.get(key)
            expected = ExpressionAttributeValues[":expected_version"]
            if not item or item["version"] != expected:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
                )
            item.update(
                status=ExpressionAttributeValues[":status"],
                version=ExpressionAttributeValues[":next_version"],
                updated_at=ExpressionAttributeValues[":changed_at"],
            )
            return {"Attributes": dict(item)}

        def query(self, **_kwargs):
            return {"Items": list(self.items.values())}

    table = FakeTable()
    monkeypatch.setattr(capability_repo, "get_table", lambda: table)
    grant = capability_repo.grant_capability(
        user_id="admin-1",
        grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global",
        grantor_id="admin-0",
        reason="approved change",
        effective_at="2026-07-14T12:00:00Z",
    )
    assert grant["version"] == 1
    assert len(
        capability_repo.get_current_grants(
            "admin-1",
            now=datetime.fromisoformat("2026-07-14T12:01:00+00:00"),
            table_factory=lambda: table,
        )
    ) == 1

    revoked = capability_repo.revoke_capability(
        user_id="admin-1",
        grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global",
        expected_version=1,
        actor_id="admin-0",
        reason="access removed",
        changed_at="2026-07-14T12:02:00Z",
    )
    assert revoked["version"] == 2
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: table) == []
    with pytest.raises(capability_repo.CapabilityVersionConflict):
        capability_repo.restore_capability(
            user_id="admin-1",
            grant_id="grant-1",
            capability=capability_repo.ADMIN_IDENTITY_MANAGER,
            scope="global",
            expected_version=1,
            actor_id="admin-0",
            reason="stale approval",
            changed_at="2026-07-14T12:03:00Z",
        )


def test_security_audit_projection_never_copies_sensitive_inputs():
    from stoa.db.repositories.security_audit_repo import project_audit_event

    projected = project_audit_event(
        {
            "event_id": "event-1",
            "event_type": "capability_revoked",
            "actor_id": "admin-1",
            "target_id": "teacher-1",
            "version": 2,
            "reason_code": "approved_change",
            "capabilities": ["secret-capability"],
            "application": {"statement": "private"},
            "token": "token-canary",
            "email": "email-canary",
            "provider_payload": "provider-canary",
        }
    )
    assert projected == {
        "event_id": "event-1",
        "event_type": "capability_revoked",
        "actor_id": "admin-1",
        "target_id": "teacher-1",
        "version": 2,
        "reason_code": "approved_change",
    }


def test_identity_binding_conditional_create_cannot_repoint(monkeypatch):
    from stoa.db.repositories import identity_repo

    class FakeTable:
        def __init__(self):
            self.items = {}

        def put_item(self, *, Item, ConditionExpression):
            key = (Item["PK"], Item["SK"])
            if key in self.items:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                    "PutItem",
                )
            self.items[key] = dict(Item)

        def get_item(self, *, Key, ConsistentRead):
            return {"Item": self.items.get((Key["PK"], Key["SK"]))}

    table = FakeTable()
    monkeypatch.setattr(identity_repo, "get_table", lambda: table)
    created = identity_repo.create_identity_binding(
        issuer="https://identity.test/primary",
        subject="subject-1",
        user_id="student-1",
        created_at="2026-07-14T12:00:00Z",
        created_by="admin-1",
    )
    same = identity_repo.create_identity_binding(
        issuer="https://identity.test/primary",
        subject="subject-1",
        user_id="student-1",
        created_at="2026-07-14T12:01:00Z",
        created_by="admin-2",
    )
    assert same == created

    with pytest.raises(identity_repo.IdentityBindingConflict):
        identity_repo.create_identity_binding(
            issuer="https://identity.test/primary",
            subject="subject-1",
            user_id="attacker-1",
            created_at="2026-07-14T12:02:00Z",
            created_by="admin-2",
        )
    binding = identity_repo.get_identity_binding(
        "https://identity.test/primary", "subject-1"
    )
    assert binding["user_id"] == "student-1"


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
