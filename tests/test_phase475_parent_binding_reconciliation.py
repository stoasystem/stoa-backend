"""Preview-bound historical parent relationship reconciliation proof."""

from __future__ import annotations

from copy import deepcopy

import pytest

from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.security.authorization import ParentAuthorizationFacts


class _RepairTable:
    def __init__(self) -> None:
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
                "version": 5,
                "preferred_locale": "de",
            },
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 3,
            },
        }
        self.transactions: list[list[dict[str, object]]] = []
        self.transaction_attempts = 0
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
                for (pk, sk), item in sorted(self.items.items())
                if pk == "USER#student-1" and sk.startswith("PARENT#")
            ]
        }

    def transact_account_deletion(self, operations):
        copied = deepcopy(operations)
        self.transaction_attempts += 1
        if self.before_transaction is not None:
            callback = self.before_transaction
            self.before_transaction = None
            callback()
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

        update = next(
            operation["Update"]
            for operation in copied
            if "Update" in operation and operation["Update"]["Key"]["SK"] == "PROFILE"
        )
        key = (update["Key"]["PK"], update["Key"]["SK"])
        values = update["ExpressionAttributeValues"]
        profile = staged.get(key)
        expected = values.get(":expected_profile_version")
        if (
            profile is None
            or profile.get("user_id") != values[":student_id"]
            or profile.get("role") != "student"
            or profile.get("account_status") != "active"
            or profile.get("version") != expected
            or profile.get("parent_id") not in (None, "", values[":parent_id"])
            or profile.get("relationship") not in (None, "", values[":relationship"])
        ):
            raise account_deletion_repo.AccountDeletionConflict("profile")
        profile.update(
            {
                "version": values[":next_profile_version"],
                "parent_id": values[":parent_id"],
                "relationship": values[":relationship"],
                "parent_binding_status": values[":status"],
            }
        )
        self.transactions.append(copied)
        self.items = staged


def _binding(parent_id: str = "parent-1", *, version: int = 4) -> dict[str, object]:
    return {
        "entity_type": "parent_student_binding",
        "parent_id": parent_id,
        "student_id": "student-1",
        "relationship": "child",
        "status": "active",
        "source": "legacy",
        "actor": "system",
        "version": version,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


def _install_forward(table: _RepairTable, parent_id: str = "parent-1") -> None:
    table.items[(f"USER#{parent_id}", "CHILD#student-1")] = {
        "PK": f"USER#{parent_id}",
        "SK": "CHILD#student-1",
        **_binding(parent_id),
    }


def _install_reverse(table: _RepairTable, parent_id: str = "parent-1") -> None:
    table.items[("USER#student-1", f"PARENT#{parent_id}")] = {
        "PK": "USER#student-1",
        "SK": f"PARENT#{parent_id}",
        **_binding(parent_id),
    }


def _install_projection(table: _RepairTable, parent_id: str = "parent-1") -> None:
    table.items[("USER#student-1", "PROFILE")].update(
        {
            "parent_id": parent_id,
            "relationship": "child",
            "parent_binding_status": "active",
        }
    )


def _preview(table: _RepairTable) -> user_repo.ParentBindingRepairPreview:
    return user_repo.preview_parent_binding_repair(
        parent_id="parent-1", student_id="student-1", relationship="child"
    )


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (
            lambda table: (_install_forward(table), _install_reverse(table), _install_projection(table)),
            user_repo.ParentBindingRepairClassification.CONSISTENT,
        ),
        (
            lambda table: (_install_reverse(table), _install_projection(table)),
            user_repo.ParentBindingRepairClassification.REPAIRABLE_MISSING_FORWARD,
        ),
        (
            lambda table: (_install_forward(table), _install_projection(table)),
            user_repo.ParentBindingRepairClassification.REPAIRABLE_MISSING_REVERSE,
        ),
        (
            lambda table: (_install_forward(table), _install_reverse(table)),
            user_repo.ParentBindingRepairClassification.REPAIRABLE_PROFILE_PROJECTION,
        ),
        (
            lambda table: (_install_reverse(table, "parent-2"), _install_projection(table, "parent-2")),
            user_repo.ParentBindingRepairClassification.CONFLICT,
        ),
        (
            lambda table: None,
            user_repo.ParentBindingRepairClassification.SKIPPED_INVALID,
        ),
    ],
)
def test_preview_classifies_every_fixture_and_writes_nothing(
    monkeypatch, setup, expected
) -> None:
    table = _RepairTable()
    setup(table)
    before = deepcopy(table.items)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    preview = _preview(table)

    assert preview.classification is expected
    assert len(preview.pair_id) == len(preview.preview_id) == 64
    assert {item.coordinate for item in preview.observations} >= {
        "parent_profile",
        "student_profile",
        "forward",
        "reverse_target",
    }
    assert table.items == before
    assert table.transactions == []


def test_one_sided_apply_is_atomic_and_replay_is_zero_write(monkeypatch) -> None:
    table = _RepairTable()
    _install_forward(table)
    _install_projection(table)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    preview = _preview(table)

    applied = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:00:00+00:00",
    )
    after_first = deepcopy(table.items)
    replay = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:01:00+00:00",
    )

    assert applied.disposition is user_repo.ParentBindingRepairApplyDisposition.REPAIRED
    assert applied.mutated is True
    assert applied.preview.classification is user_repo.ParentBindingRepairClassification.CONSISTENT
    assert replay.disposition is user_repo.ParentBindingRepairApplyDisposition.ALREADY_CONSISTENT
    assert replay.mutated is False
    assert len(table.transactions) == 1
    assert table.items == after_first


def test_changed_after_preview_is_skipped_and_new_data_is_preserved(monkeypatch) -> None:
    table = _RepairTable()
    _install_forward(table)
    _install_projection(table)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    preview = _preview(table)
    table.items[("USER#student-1", "PROFILE")].update(
        {"version": 6, "preferred_locale": "fr"}
    )

    result = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:00:00+00:00",
    )

    assert result.disposition is user_repo.ParentBindingRepairApplyDisposition.SKIPPED_CHANGED
    assert table.transactions == []
    assert table.items[("USER#student-1", "PROFILE")]["preferred_locale"] == "fr"


def test_change_racing_the_atomic_apply_is_not_overwritten(monkeypatch) -> None:
    table = _RepairTable()
    _install_forward(table)
    _install_projection(table)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    preview = _preview(table)

    def concurrent_profile_write() -> None:
        table.items[("USER#student-1", "PROFILE")].update(
            {"version": 6, "preferred_locale": "it"}
        )

    table.before_transaction = concurrent_profile_write
    result = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:00:00+00:00",
    )

    assert result.disposition is user_repo.ParentBindingRepairApplyDisposition.SKIPPED_CHANGED
    assert table.transaction_attempts == 1
    assert table.transactions == []
    assert table.items[("USER#student-1", "PROFILE")]["preferred_locale"] == "it"
    assert ("USER#student-1", "PARENT#parent-1") not in table.items


@pytest.mark.parametrize(
    ("coordinate", "field", "value"),
    [
        ("PROFILE", "account_status", "suspended"),
        ("PROFILE", "role", "guardian"),
        ("PROFILE", "version", 3),
        ("ACCOUNT_FENCE", "status", "deletion_pending"),
    ],
)
def test_parent_authorization_race_cannot_bypass_reconciliation_fence(
    monkeypatch, coordinate, field, value
) -> None:
    table = _RepairTable()
    _install_forward(table)
    _install_projection(table)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    preview = _preview(table)

    def race_parent_authorization() -> None:
        table.items[("USER#parent-1", coordinate)][field] = value

    table.before_transaction = race_parent_authorization
    result = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:00:00+00:00",
    )

    assert result.disposition not in {
        user_repo.ParentBindingRepairApplyDisposition.REPAIRED,
        user_repo.ParentBindingRepairApplyDisposition.ALREADY_CONSISTENT,
    }
    assert table.transactions == []
    assert ("USER#student-1", "PARENT#parent-1") not in table.items
    assert table.items[("USER#student-1", "PROFILE")]["parent_id"] == "parent-1"


def test_different_parent_conflict_is_report_only_and_remains_unauthorized(monkeypatch) -> None:
    table = _RepairTable()
    table.items[("USER#parent-2", "PROFILE")] = {
        "PK": "USER#parent-2",
        "SK": "PROFILE",
        "user_id": "parent-2",
        "role": "parent",
        "account_status": "active",
        "version": 1,
    }
    _install_reverse(table, "parent-2")
    _install_projection(table, "parent-2")
    monkeypatch.setattr(user_repo, "get_table", lambda: table)
    preview = _preview(table)
    before = deepcopy(table.items)

    result = user_repo.apply_parent_binding_repair(
        parent_id="parent-1",
        student_id="student-1",
        relationship="child",
        preview_id=preview.preview_id,
        actor="admin-1",
        created_at="2026-07-22T01:00:00+00:00",
    )

    assert result.disposition is user_repo.ParentBindingRepairApplyDisposition.CONFLICT
    assert table.items == before
    assert table.transactions == []
    assert not ParentAuthorizationFacts(
        forward=None,
        reverse=None,
        parent_account=table.items[("USER#parent-1", "PROFILE")],
        student_account=table.items[("USER#student-1", "PROFILE")],
    ).matches("parent-1", "student-1")
