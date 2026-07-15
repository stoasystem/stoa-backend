from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

from botocore.exceptions import ClientError
from fastapi import HTTPException
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
        "message": (
            "Try again in a few minutes. If the problem continues, contact support "
            "and share the reference shown."
        ),
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

        def get_item(self, *, Key, **_kwargs):
            item = self.items.get((Key["PK"], Key["SK"]))
            return {"Item": dict(item)} if item else {}

        def query(self, **_kwargs):
            return {"Items": list(self.items.values())}

        def apply_capability_transaction(self, operations):
            pending = dict(self.items)
            for operation in operations:
                item = operation["item"]
                key = (item["PK"], item["SK"])
                current = pending.get(key)
                if operation["condition"] == "absent" and current is not None:
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException"}}, "TransactWriteItems"
                    )
                if operation["condition"] != "absent" and (
                    not current
                    or any(current.get(name) != value for name, value in operation["expected"].items())
                ):
                    raise ClientError(
                        {"Error": {"Code": "ConditionalCheckFailedException"}}, "TransactWriteItems"
                    )
                pending[key] = dict(item)
            self.items = pending

    table = FakeTable()
    monkeypatch.setattr(capability_repo, "get_table", lambda: table)
    grant = capability_repo.grant_capability(
        user_id="admin-1",
        command_id="command-1",
        grant_id="grant-1",
        capability=capability_repo.ADMIN_IDENTITY_MANAGER,
        scope="global",
        grantor_id="admin-0",
        reason="approved change",
        effective_at="2026-07-14T12:00:00Z",
        expected_generation=0,
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
        expected_generation=1,
        expected_version=1,
        actor_id="admin-0",
        reason="access removed",
        changed_at="2026-07-14T12:02:00Z",
        action_id="revoke-command-1",
    )
    assert revoked["version"] == 2
    assert capability_repo.get_current_grants("admin-1", table_factory=lambda: table) == []
    with pytest.raises(capability_repo.CapabilityVersionConflict):
        capability_repo.revoke_capability(
            user_id="admin-1",
            grant_id="grant-1",
            capability=capability_repo.ADMIN_IDENTITY_MANAGER,
            scope="global",
            expected_generation=1,
            expected_version=1,
            actor_id="admin-0",
            reason="stale approval",
            changed_at="2026-07-14T12:03:00Z",
            action_id="different-command",
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


def test_break_glass_evidence_records_notification_and_independent_review(monkeypatch):
    from stoa.db.repositories import security_audit_repo

    rows = []

    class Table:
        def put_item(self, **kwargs):
            rows.append(kwargs["Item"])

    monkeypatch.setattr(security_audit_repo, "get_table", lambda: Table())
    notification, review = security_audit_repo.append_break_glass_evidence(
        stream_id="incident-1",
        event_id="event-1",
        actor_id="admin-1",
        resource_type="student",
        action="read",
        purpose="incident_break_glass",
        incident_id="incident-1",
        notification_reference="notify-1",
        review_reference="review-1",
        correlation_id="corr-1",
        created_at="2026-07-15T10:00:00Z",
    )
    assert notification["event_type"] == "break_glass_notification_recorded"
    assert review["event_type"] == "break_glass_review_required"
    assert len(rows) == 2
    assert "token-canary" not in repr(rows)


def test_routine_admin_lifecycle_requires_manager_and_revokes_locally_first(monkeypatch):
    from stoa.services import privileged_identity_service

    commands = {}
    profiles = {}
    bindings = {}
    audits = []
    repo = privileged_identity_service.privileged_identity_repo

    def create_command(item):
        existing = commands.get(item["command_id"])
        if existing:
            immutable = ("operation", "target_id", "issuer", "subject", "reason", "approved_by")
            if not all(existing.get(key) == item.get(key) for key in immutable):
                raise repo.PrivilegedIdentityCommandConflict("conflict")
            return dict(existing), False
        commands[item["command_id"]] = dict(item)
        return dict(item), True

    def update_command(command_id, *, expected_version, status, updated_at, evidence_reference):
        item = commands[command_id]
        if item["version"] != expected_version:
            raise repo.PrivilegedIdentityCommandConflict("stale")
        item.update(
            status=status,
            updated_at=updated_at,
            evidence_reference=evidence_reference,
            version=expected_version + 1,
        )
        return dict(item)

    monkeypatch.setattr(repo, "create_command", create_command)
    monkeypatch.setattr(repo, "update_command", update_command)
    monkeypatch.setattr(
        privileged_identity_service.user_repo,
        "put_user",
        lambda item: profiles.__setitem__(item["user_id"], dict(item)),
    )
    monkeypatch.setattr(
        privileged_identity_service.user_repo,
        "get_user",
        lambda user_id: dict(profiles[user_id]) if user_id in profiles else None,
    )
    monkeypatch.setattr(
        privileged_identity_service.identity_repo,
        "create_identity_binding",
        lambda **kwargs: bindings.setdefault((kwargs["issuer"], kwargs["subject"]), dict(kwargs)),
    )
    monkeypatch.setattr(
        privileged_identity_service.security_audit_repo,
        "append_event",
        lambda stream_id, event: audits.append((stream_id, dict(event))),
    )

    class Provider:
        def __init__(self):
            self.calls = []
            self.fail_defense = False

        def ensure_admin_identity(self, **kwargs):
            self.calls.append(("ensure", kwargs))

        def admin_remove_user_from_group(self, **kwargs):
            self.calls.append(("remove", kwargs))
            if self.fail_defense:
                raise TimeoutError("provider payload canary")

        def admin_user_global_sign_out(self, **kwargs):
            self.calls.append(("signout", kwargs))

    provider = Provider()
    no_capability = {
        "user_id": "admin-basic",
        "role": "admin",
        "account_status": "active",
        "capabilities": {},
    }
    with pytest.raises(HTTPException) as denied:
        privileged_identity_service.provision_admin(
            actor=no_capability,
            command_id="command-1",
            target_email="new-admin@example.test",
            issuer="https://identity.test/primary",
            subject="new-admin-subject",
            reason="approved routine provision",
            provider=provider,
        )
    assert denied.value.status_code == 403
    assert commands == {}
    assert provider.calls == []

    manager = {
        **no_capability,
        "user_id": "admin-manager",
        "capabilities": {"admin_identity_manager": "granted"},
    }
    created = privileged_identity_service.provision_admin(
        actor=manager,
        command_id="command-1",
        target_email="new-admin@example.test",
        issuer="https://identity.test/primary",
        subject="new-admin-subject",
        reason="approved routine provision",
        provider=provider,
    )
    assert created["status"] == "active"
    assert profiles[created["targetId"]]["account_status"] == "active"
    assert len(bindings) == 1
    provider_call_count = len(provider.calls)
    replay = privileged_identity_service.provision_admin(
        actor=manager,
        command_id="command-1",
        target_email="new-admin@example.test",
        issuer="https://identity.test/primary",
        subject="new-admin-subject",
        reason="approved routine provision",
        provider=provider,
    )
    assert replay["idempotent"] is True
    assert len(provider.calls) == provider_call_count
    assert len(bindings) == 1

    provider.fail_defense = True
    suspended = privileged_identity_service.change_admin_status(
        actor=manager,
        command_id="command-2",
        target_id=created["targetId"],
        operation="suspend",
        reason="approved investigation",
        provider=provider,
        provider_username="new-admin-subject",
    )
    assert suspended["status"] == "suspended"
    assert suspended["providerDefenseComplete"] is False
    assert profiles[created["targetId"]]["account_status"] == "suspended"
    assert "provider payload canary" not in repr(audits)


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
