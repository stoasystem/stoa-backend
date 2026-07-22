"""Atomic parent binding/profile projection proof for Phase 475 Plan 06."""

from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.routers import admin, auth
from stoa.security.authorization import ParentAuthorizationFacts


class _AtomicRelationshipTable:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {
            ("USER#student-1", "PROFILE"): {
                "PK": "USER#student-1",
                "SK": "PROFILE",
                "user_id": "student-1",
                "role": "student",
                "account_status": "active",
                "preferred_locale": "de",
            },
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 3,
            },
        }
        self.fail_at = fail_at
        self.transactions: list[list[dict[str, object]]] = []
        self.before_transaction = None

    def get_item(self, *, Key, ConsistentRead=False):  # noqa: N803
        assert ConsistentRead is True
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": deepcopy(item)} if item is not None else {}

    def query(self, **kwargs):
        assert kwargs.get("ConsistentRead") is True
        return {
            "Items": [
                deepcopy(item)
                for (pk, sk), item in self.items.items()
                if pk == "USER#student-1" and sk.startswith("PARENT#")
            ]
        }

    def transact_account_deletion(self, operations):
        copied = deepcopy(operations)
        self.transactions.append(copied)
        if self.before_transaction is not None:
            callback = self.before_transaction
            self.before_transaction = None
            callback()
        if self.fail_at is not None:
            assert 0 <= self.fail_at < len(copied)
            raise account_deletion_repo.AccountDeletionConflict("injected")

        staged = deepcopy(self.items)
        fence = copied[0]["ConditionCheck"]
        fence_item = staged.get((fence["Key"]["PK"], fence["Key"]["SK"]))
        if (
            fence_item is None
            or fence_item.get("status") != "active"
            or fence_item.get("generation")
            != fence["ExpressionAttributeValues"][":generation"]
        ):
            raise account_deletion_repo.AccountDeletionConflict("fence")

        for operation in copied[1:3]:
            update = operation["Update"]
            key = (update["Key"]["PK"], update["Key"]["SK"])
            values = update["ExpressionAttributeValues"]
            existing = staged.get(key)
            if existing is not None and any(
                existing.get(field) != values[f":{field}"]
                for field in ("parent_id", "student_id", "relationship", "version")
            ):
                raise account_deletion_repo.AccountDeletionConflict("binding")
            row = dict(existing or {"PK": key[0], "SK": key[1]})
            for field in (
                "entity_type",
                "parent_id",
                "student_id",
                "relationship",
                "version",
                "created_at",
            ):
                row.setdefault(field, values[f":{field}"])
            for field in ("status", "source", "actor", "updated_at"):
                row[field] = values[f":{field}"]
            staged[key] = row

        profile_update = copied[3]["Update"]
        profile_key = (
            profile_update["Key"]["PK"],
            profile_update["Key"]["SK"],
        )
        profile = staged.get(profile_key)
        profile_values = profile_update["ExpressionAttributeValues"]
        if (
            profile is None
            or profile.get("user_id") != profile_values[":student_id"]
            or profile.get("role") != "student"
            or profile.get("parent_id") not in (None, "", profile_values[":parent_id"])
            or profile.get("relationship")
            not in (None, "", profile_values[":relationship"])
        ):
            raise account_deletion_repo.AccountDeletionConflict("profile")
        profile.update(
            {
                "parent_id": profile_values[":parent_id"],
                "relationship": profile_values[":relationship"],
                "parent_binding_status": profile_values[":status"],
            }
        )
        self.items = staged


def _write_relationship(**overrides):
    values = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "status": "active",
        "source": "admin_repair",
        "actor": "admin-1",
        "created_at": "2026-07-21T20:00:00+00:00",
        "version": 4,
    }
    values.update(overrides)
    return user_repo.put_parent_student_relationship(**values)


def test_transaction_shape_contains_fence_two_rows_and_narrow_profile_update() -> None:
    operations = user_repo.build_parent_binding_transaction(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        status="active",
        source="admin_repair",
        actor="admin-1",
        created_at="2026-07-21T20:00:00+00:00",
        version=4,
        expected_generation=3,
    )

    assert len(operations) == 4
    assert operations[0]["ConditionCheck"]["Key"] == {
        "PK": "USER#student-1",
        "SK": "ACCOUNT_FENCE",
    }
    assert [operation["Update"]["Key"] for operation in operations[1:3]] == [
        {"PK": "USER#parent-1", "SK": "CHILD#student-1"},
        {"PK": "USER#student-1", "SK": "PARENT#parent-1"},
    ]
    for operation in operations[1:3]:
        condition = operation["Update"]["ConditionExpression"]
        assert "attribute_not_exists(PK)" in condition
        assert "#version = :version" in condition
        assert "#relationship = :relationship" in condition
    profile = operations[3]["Update"]
    assert profile["Key"] == {"PK": "USER#student-1", "SK": "PROFILE"}
    assert set(profile["ExpressionAttributeNames"].values()) == {
        "parent_id",
        "relationship",
        "parent_binding_status",
        "user_id",
        "role",
    }


@pytest.mark.parametrize("fail_at", range(4))
def test_failure_at_every_operation_leaves_all_relationship_projections_unchanged(
    monkeypatch, fail_at
) -> None:
    table = _AtomicRelationshipTable(fail_at=fail_at)
    before = deepcopy(table.items)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    result = _write_relationship()

    assert result.disposition is user_repo.ParentBindingDisposition.RETRYABLE
    assert table.items == before


def test_identical_replay_returns_original_without_another_transaction(monkeypatch) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    created = _write_relationship()
    original = deepcopy(created.binding)
    replayed = _write_relationship(created_at="2026-07-21T21:00:00+00:00")

    assert created.disposition is user_repo.ParentBindingDisposition.CREATED
    assert replayed.disposition is user_repo.ParentBindingDisposition.REPLAYED
    assert replayed.binding == original
    assert replayed.binding["version"] == 4
    assert replayed.binding["created_at"] == "2026-07-21T20:00:00+00:00"
    assert len(table.transactions) == 1


def test_conflicting_parent_is_preserved_and_authorization_remains_denied(monkeypatch) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    assert _write_relationship().disposition is user_repo.ParentBindingDisposition.CREATED
    before = deepcopy(table.items)

    conflict = _write_relationship(parent_id="parent-2")

    assert conflict.disposition is user_repo.ParentBindingDisposition.CONFLICT
    assert table.items == before
    assert len(table.transactions) == 1
    assert not ParentAuthorizationFacts(
        forward=None,
        reverse=None,
        parent_account={
            "user_id": "parent-2",
            "role": "parent",
            "account_status": "active",
        },
        student_account=table.items[("USER#student-1", "PROFILE")],
    ).matches("parent-2", "student-1")


def test_concurrent_conflicting_profile_wins_before_requested_transaction(monkeypatch) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    def install_conflict() -> None:
        table.items[("USER#student-1", "PROFILE")].update(
            {"parent_id": "parent-2", "relationship": "child"}
        )

    table.before_transaction = install_conflict
    result = _write_relationship()

    assert result.disposition is user_repo.ParentBindingDisposition.CONFLICT
    assert ("USER#parent-1", "CHILD#student-1") not in table.items
    assert ("USER#student-1", "PARENT#parent-1") not in table.items
    assert table.items[("USER#student-1", "PROFILE")]["parent_id"] == "parent-2"


def test_registration_and_admin_repair_have_one_logical_relationship_writer() -> None:
    auth_source = inspect.getsource(auth)
    admin_source = inspect.getsource(admin.repair_parent_binding)

    assert "put_parent_student_relationship" in auth_source
    assert "put_parent_student_binding(" not in auth_source
    assert "update_student_parent_link(" not in auth_source
    assert "apply_parent_binding_repair" in admin_source
    assert "put_parent_student_binding(" not in admin_source
    assert "update_student_parent_link(" not in admin_source
