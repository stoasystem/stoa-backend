"""Offline public identity lifecycle and partial-failure security proofs."""

from __future__ import annotations

from botocore.exceptions import ClientError
import pytest

from stoa.db.repositories import identity_repo, public_identity_repo
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import resolve_actor
from stoa.security.tokens import VerifiedAccessToken


class MemoryTable:
    def __init__(self):
        self.items = {}

    def put_item(self, *, Item, ConditionExpression=None):
        key = (Item["PK"], Item["SK"])
        if ConditionExpression and key in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
            )
        self.items[key] = dict(Item)

    def get_item(self, *, Key, ConsistentRead=True):
        return {"Item": self.items.get((Key["PK"], Key["SK"]))}

    def update_item(
        self,
        *,
        Key,
        UpdateExpression,
        ConditionExpression,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
        ReturnValues,
    ):
        key = (Key["PK"], Key["SK"])
        item = self.items.get(key)
        expected = ExpressionAttributeValues[":expected_version"]
        if item is None or item.get("version") != expected:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
            )
        for alias, field in ExpressionAttributeNames.items():
            if alias.startswith("#step") and item.get(field, False) is not False:
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
                )
        item["version"] = ExpressionAttributeValues[":next_version"]
        item["updated_at"] = ExpressionAttributeValues[":updated_at"]
        for alias, field in ExpressionAttributeNames.items():
            if alias.startswith("#step"):
                item[field] = True
        return {"Attributes": dict(item)}


def test_public_identity_command_is_immutable_and_idempotent(monkeypatch):
    table = MemoryTable()
    monkeypatch.setattr(public_identity_repo, "get_table", lambda: table)
    command = dict(
        email="Student@Example.test",
        issuer="https://identity.test/primary/",
        subject="subject-1",
        user_id="student-1",
        role="student",
        created_at="2026-07-15T12:00:00Z",
    )

    first = public_identity_repo.create_or_get_public_identity_command(**command)
    replay = public_identity_repo.create_or_get_public_identity_command(**command)

    assert replay == first
    assert first.email == "student@example.test"
    assert len(table.items) == 1
    for field, value in (("subject", "subject-2"), ("user_id", "student-2"), ("role", "parent")):
        changed = {**command, field: value}
        with pytest.raises(public_identity_repo.PublicIdentityCommandConflict):
            public_identity_repo.create_or_get_public_identity_command(**changed)
    assert len(table.items) == 1


def test_interrupted_binding_repairs_only_matching_reverse_inventory(monkeypatch):
    class FailingInventoryTable(MemoryTable):
        fail_inventory_once = True

        def put_item(self, *, Item, ConditionExpression=None):
            if Item.get("entity_type") == "user_identity_inventory" and self.fail_inventory_once:
                self.fail_inventory_once = False
                raise TimeoutError("injected reverse inventory interruption")
            return super().put_item(Item=Item, ConditionExpression=ConditionExpression)

    table = FailingInventoryTable()
    monkeypatch.setattr(identity_repo, "get_table", lambda: table)
    kwargs = dict(
        issuer="https://identity.test/primary",
        subject="subject-1",
        user_id="student-1",
        created_at="2026-07-15T12:00:00Z",
        created_by="public_self_service",
    )
    with pytest.raises(TimeoutError):
        identity_repo.create_identity_binding(**kwargs)

    repaired = identity_repo.create_identity_binding(**kwargs)
    assert repaired["user_id"] == "student-1"
    assert len(table.items) == 2
    with pytest.raises(identity_repo.IdentityBindingConflict):
        identity_repo.create_identity_binding(**{**kwargs, "user_id": "attacker-1"})


@pytest.mark.asyncio
async def test_pending_public_profile_cannot_construct_actor():
    class Repository:
        async def get_binding(self, issuer, subject):
            return {"status": "active", "user_id": "student-1"}

        async def get_account(self, user_id):
            return {"role": "student", "account_status": "pending_verification"}

        async def get_current_grants(self, user_id):
            return []

    token = VerifiedAccessToken(
        issuer="https://identity.test/primary",
        subject="subject-1",
        client_id="student-client",
        groups=("students",),
    )
    with pytest.raises(SecurityDecisionError) as denied:
        await resolve_actor(token, Repository())
    assert denied.value.code is SecurityErrorCode.IDENTITY_CONFLICT


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["student", "parent"])
async def test_register_confirm_converges_one_subject_bound_actor(monkeypatch, role):
    from stoa.services import public_identity_service

    table = MemoryTable()
    profiles = {}
    groups = set()
    monkeypatch.setattr(public_identity_repo, "get_table", lambda: table)
    monkeypatch.setattr(identity_repo, "get_table", lambda: table)
    monkeypatch.setattr(
        public_identity_service.user_repo,
        "get_user",
        lambda user_id: dict(profiles[user_id]) if user_id in profiles else None,
    )
    monkeypatch.setattr(
        public_identity_service.user_repo,
        "put_user",
        lambda item: profiles.__setitem__(item["user_id"], dict(item)),
    )
    monkeypatch.setattr(
        public_identity_service.user_repo,
        "update_email_verification_state",
        lambda user_id, fields: profiles.__setitem__(
            user_id, {**profiles[user_id], **fields}
        )
        or dict(profiles[user_id]),
    )

    class Provider:
        fail_group_once = True

        def admin_add_user_to_group(self, **kwargs):
            if self.fail_group_once:
                self.fail_group_once = False
                raise TimeoutError("injected provider interruption")
            groups.add((kwargs["Username"], kwargs["GroupName"]))

    provider = Provider()
    email = f"{role}@example.test"
    subject = f"subject-{role}"
    profile = {
        "user_id": subject,
        "email": email,
        "role": role,
        "registration_command": "public_self_service",
        "registration_role": role,
        "email_verification_status": "pending_verification",
        "email_verification_required": True,
    }
    registration = dict(
        email=email,
        issuer="https://identity.test/primary",
        subject=subject,
        user_id=subject,
        role=role,
        profile=profile,
        provider=provider,
        user_pool_id="pool-id",
    )
    with pytest.raises(public_identity_service.PublicIdentityDependencyError):
        public_identity_service.start_or_resume_public_registration(**registration)
    assert profiles[subject]["account_status"] == "pending_verification"

    command, _ = public_identity_service.start_or_resume_public_registration(**registration)
    assert command.binding_complete is True
    assert command.canonical_group_complete is True
    assert groups == {(email, f"{role}s")}

    command, active = public_identity_service.confirm_and_reconcile_public_identity(
        email=email,
        issuer="https://identity.test/primary",
        provider_subject=subject,
        provider_status="CONFIRMED",
        provider_email=email,
        provider_email_verified=True,
        provider_enabled=True,
        provider=provider,
        user_pool_id="pool-id",
    )
    assert command.activation_complete is True
    assert active["account_status"] == "active"

    class Repository:
        async def get_binding(self, issuer, provider_subject):
            return identity_repo.get_identity_binding(issuer, provider_subject)

        async def get_account(self, user_id):
            return profiles.get(user_id)

        async def get_current_grants(self, user_id):
            return []

    actor = await resolve_actor(
        VerifiedAccessToken(
            issuer="https://identity.test/primary",
            subject=subject,
            client_id="student-client",
            groups=(f"{role}s",),
            verified_email=email,
        ),
        Repository(),
    )
    assert actor.user_id == subject
    assert actor.role.value == role


def test_confirmation_rejects_provider_subject_mismatch_before_activation(monkeypatch):
    from stoa.services import public_identity_service

    table = MemoryTable()
    monkeypatch.setattr(public_identity_repo, "get_table", lambda: table)
    public_identity_repo.create_or_get_public_identity_command(
        email="student@example.test",
        issuer="https://identity.test/primary",
        subject="subject-1",
        user_id="student-1",
        role="student",
        created_at="2026-07-15T12:00:00Z",
    )
    with pytest.raises(public_identity_repo.PublicIdentityCommandConflict):
        public_identity_service.confirm_and_reconcile_public_identity(
            email="student@example.test",
            issuer="https://identity.test/primary",
            provider_subject="attacker-subject",
            provider_status="CONFIRMED",
            provider_email="student@example.test",
            provider_email_verified=True,
            provider_enabled=True,
            provider=object(),
            user_pool_id="pool-id",
        )
    command = public_identity_repo.get_public_identity_command("student@example.test")
    assert command.activation_complete is False
