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
            ("USER#parent-1", "PROFILE"): {
                "PK": "USER#parent-1",
                "SK": "PROFILE",
                "user_id": "parent-1",
                "role": "parent",
                "account_status": "active",
                "version": 2,
            },
            ("USER#parent-1", "ACCOUNT_FENCE"): {
                "PK": "USER#parent-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 7,
            },
            ("USER#student-1", "PROFILE"): {
                "PK": "USER#student-1",
                "SK": "PROFILE",
                "user_id": "student-1",
                "role": "student",
                "account_status": "active",
                "preferred_locale": "de",
                "version": 5,
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
        for operation in copied:
            condition_check = operation.get("ConditionCheck")
            if condition_check is None:
                continue
            key = (condition_check["Key"]["PK"], condition_check["Key"]["SK"])
            item = staged.get(key)
            values = condition_check["ExpressionAttributeValues"]
            if key[1] == "ACCOUNT_FENCE":
                if (
                    item is None
                    or item.get("status") != "active"
                    or item.get("generation") != values[":generation"]
                ):
                    raise account_deletion_repo.AccountDeletionConflict("fence")
                continue
            if (
                item is None
                or item.get("user_id") != values[":user_id"]
                or item.get("role") != values[":role"]
                or item.get("account_status") != values[":active"]
                or item.get("version") != values[":profile_version"]
            ):
                raise account_deletion_repo.AccountDeletionConflict("profile observation")

        for operation in copied:
            if "Update" not in operation or operation["Update"]["Key"]["SK"] == "PROFILE":
                continue
            update = operation["Update"]
            key = (update["Key"]["PK"], update["Key"]["SK"])
            values = update["ExpressionAttributeValues"]
            existing = staged.get(key)
            if ":expected_status" in values:
                if (
                    existing is None
                    or existing.get("parent_id") != values[":parent_id"]
                    or existing.get("student_id") != values[":student_id"]
                    or existing.get("relationship") != values[":relationship"]
                    or existing.get("status") != values[":expected_status"]
                    or existing.get("version") != values[":expected_version"]
                ):
                    raise account_deletion_repo.AccountDeletionConflict("binding status")
                existing.update(
                    {
                        "status": values[":next_status"],
                        "version": values[":next_version"],
                        "source": values[":source"],
                        "actor": values[":actor"],
                        "updated_at": values[":updated_at"],
                    }
                )
                continue
            compared_fields = ["parent_id", "student_id", "relationship", "version"]
            if "#status = :status" in update["ConditionExpression"]:
                compared_fields.append("status")
            if existing is not None and any(
                existing.get(field) != values[f":{field}"] for field in compared_fields
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

        profile_update = next(
            operation["Update"]
            for operation in copied
            if "Update" in operation and operation["Update"]["Key"]["SK"] == "PROFILE"
        )
        profile_key = (
            profile_update["Key"]["PK"],
            profile_update["Key"]["SK"],
        )
        profile = staged.get(profile_key)
        profile_values = profile_update["ExpressionAttributeValues"]
        if ":expected_binding_status" in profile_values:
            if (
                profile is None
                or profile.get("user_id") != profile_values[":student_id"]
                or profile.get("parent_id") != profile_values[":parent_id"]
                or profile.get("relationship") != profile_values[":relationship"]
                or profile.get("parent_binding_status")
                != profile_values[":expected_binding_status"]
                or profile.get("version")
                != profile_values[":expected_profile_version"]
            ):
                raise account_deletion_repo.AccountDeletionConflict("profile status")
            profile.update(
                {
                    "version": profile_values[":next_profile_version"],
                    "parent_binding_status": profile_values[":next_status"],
                }
            )
            self.items = staged
            return
        if (
            profile is None
            or profile.get("user_id") != profile_values[":student_id"]
            or profile.get("role") != "student"
            or profile.get("account_status") != "active"
            or profile.get("version") != profile_values[":expected_profile_version"]
            or profile.get("parent_id") not in (None, "", profile_values[":parent_id"])
            or profile.get("relationship")
            not in (None, "", profile_values[":relationship"])
        ):
            raise account_deletion_repo.AccountDeletionConflict("profile")
        profile.update(
            {
                "version": profile_values[":next_profile_version"],
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


def test_transaction_shape_contains_dual_fences_dual_profiles_and_relationship_writes() -> None:
    operations = user_repo.build_parent_binding_transaction(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        status="active",
        source="admin_repair",
        actor="admin-1",
        created_at="2026-07-21T20:00:00+00:00",
        version=4,
        expected_parent_generation=7,
        expected_student_generation=3,
        expected_parent_profile_version=2,
        expected_student_profile_version=5,
    )

    assert len(operations) == 6
    assert operations[0]["ConditionCheck"]["Key"] == {
        "PK": "USER#parent-1",
        "SK": "ACCOUNT_FENCE",
    }
    assert operations[1]["ConditionCheck"]["Key"] == {
        "PK": "USER#student-1",
        "SK": "ACCOUNT_FENCE",
    }
    parent_profile = operations[2]["ConditionCheck"]
    assert parent_profile["Key"] == {"PK": "USER#parent-1", "SK": "PROFILE"}
    assert parent_profile["ExpressionAttributeValues"] == {
        ":user_id": "parent-1",
        ":role": "parent",
        ":active": "active",
        ":profile_version": 2,
    }
    assert [operation["Update"]["Key"] for operation in operations[3:5]] == [
        {"PK": "USER#parent-1", "SK": "CHILD#student-1"},
        {"PK": "USER#student-1", "SK": "PARENT#parent-1"},
    ]
    for operation in operations[3:5]:
        condition = operation["Update"]["ConditionExpression"]
        assert "attribute_not_exists(PK)" in condition
        assert "#version = :version" in condition
        assert "#relationship = :relationship" in condition
    profile = operations[5]["Update"]
    assert profile["Key"] == {"PK": "USER#student-1", "SK": "PROFILE"}
    assert set(profile["ExpressionAttributeNames"].values()) == {
        "parent_id",
        "relationship",
        "parent_binding_status",
        "user_id",
        "role",
        "account_status",
    }
    assert profile["ExpressionAttributeValues"][":student_role"] == "student"
    assert profile["ExpressionAttributeValues"][":active"] == "active"


@pytest.mark.parametrize("fail_at", range(6))
def test_failure_at_every_operation_leaves_all_relationship_projections_unchanged(
    monkeypatch, fail_at
) -> None:
    table = _AtomicRelationshipTable(fail_at=fail_at)
    before = deepcopy(table.items)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    result = _write_relationship()

    assert result.disposition is user_repo.ParentBindingDisposition.RETRYABLE
    assert table.items == before


@pytest.mark.parametrize(
    ("participant", "coordinate", "field", "value"),
    [
        ("parent", "PROFILE", "account_status", "suspended"),
        ("parent", "ACCOUNT_FENCE", "status", "deletion_pending"),
        ("parent", "PROFILE", "role", "guardian"),
        ("parent", "PROFILE", "version", 3),
        ("student", "PROFILE", "account_status", "suspended"),
        ("student", "ACCOUNT_FENCE", "status", "deletion_pending"),
        ("student", "PROFILE", "role", "child"),
        ("student", "PROFILE", "version", 6),
    ],
)
def test_participant_lifecycle_or_version_race_rolls_back_every_binding_write(
    monkeypatch, participant, coordinate, field, value
) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    def race_authorization_observation() -> None:
        table.items[(f"USER#{participant}-1", coordinate)][field] = value

    table.before_transaction = race_authorization_observation
    result = _write_relationship()

    assert result.disposition is not user_repo.ParentBindingDisposition.CREATED
    assert ("USER#parent-1", "CHILD#student-1") not in table.items
    assert ("USER#student-1", "PARENT#parent-1") not in table.items
    student = table.items[("USER#student-1", "PROFILE")]
    assert "parent_id" not in student
    assert "parent_binding_status" not in student


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


@pytest.mark.parametrize("terminal_status", ["revoked", "inactive"])
def test_non_active_relationship_retry_is_conflict_and_never_revives(
    monkeypatch, terminal_status
) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    assert _write_relationship().disposition is user_repo.ParentBindingDisposition.CREATED
    for key in (
        ("USER#parent-1", "CHILD#student-1"),
        ("USER#student-1", "PARENT#parent-1"),
    ):
        table.items[key]["status"] = terminal_status
    table.items[("USER#student-1", "PROFILE")]["parent_binding_status"] = terminal_status
    before = deepcopy(table.items)

    result = _write_relationship(created_at="2026-07-22T02:00:00+00:00")

    assert result.disposition is user_repo.ParentBindingDisposition.CONFLICT
    assert result.binding is None
    assert table.items == before
    assert len(table.transactions) == 1


def test_relationship_create_condition_includes_status_and_never_assigns_it_to_history() -> None:
    operations = user_repo.build_parent_binding_transaction(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        status="active",
        source="admin_repair",
        actor="admin-1",
        created_at="2026-07-21T20:00:00+00:00",
        version=4,
        expected_parent_generation=7,
        expected_student_generation=3,
        expected_parent_profile_version=2,
        expected_student_profile_version=5,
    )

    for operation in operations[3:5]:
        update = operation["Update"]
        assert "#status = :status" in update["ConditionExpression"]
        assert "#status = if_not_exists(#status, :status)" in update["UpdateExpression"]
        assert "#status = :status" not in update["UpdateExpression"]


def test_admin_status_transition_is_expected_status_and_version_cas(monkeypatch) -> None:
    table = _AtomicRelationshipTable()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    assert _write_relationship().disposition is user_repo.ParentBindingDisposition.CREATED

    transitioned = user_repo.transition_parent_student_relationship_status(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        expected_status="active",
        expected_version=4,
        status="revoked",
        source="admin_lifecycle",
        actor="admin-1",
        updated_at="2026-07-22T03:00:00+00:00",
    )
    after_first = deepcopy(table.items)
    stale = user_repo.transition_parent_student_relationship_status(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        expected_status="active",
        expected_version=4,
        status="inactive",
        source="admin_lifecycle",
        actor="admin-1",
        updated_at="2026-07-22T03:01:00+00:00",
    )

    assert transitioned.disposition is user_repo.ParentBindingStatusDisposition.TRANSITIONED
    assert transitioned.status == "revoked"
    assert transitioned.version == 5
    assert stale.disposition is user_repo.ParentBindingStatusDisposition.CONFLICT
    assert stale.status is None
    assert stale.version is None
    assert table.items == after_first
    assert {
        table.items[("USER#parent-1", "CHILD#student-1")]["status"],
        table.items[("USER#student-1", "PARENT#parent-1")]["status"],
        table.items[("USER#student-1", "PROFILE")]["parent_binding_status"],
    } == {"revoked"}


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
