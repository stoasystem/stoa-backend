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
