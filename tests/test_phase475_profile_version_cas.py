"""Real shared-profile writer versus privacy-scrub CAS proof for Plan 475-08."""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo, user_repo


class _ProfileRaceTable:
    def __init__(self, *, first: str = "scrub") -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {
            ("USER#parent-1", "PROFILE"): {
                "PK": "USER#parent-1",
                "SK": "PROFILE",
                "entity_type": "user_profile",
                "user_id": "parent-1",
                "role": "parent",
                "account_status": "active",
                "version": 7,
                "preferred_locale": "de",
                "preferredLocale": "de",
                "language": "de",
                "preferences": {"digest": b"\x00weekly\xff"},
                "child_summaries": [
                    {"student_id": "student-1", "name": "private"},
                    {"student_id": "student-2", "name": "sibling"},
                ],
            },
            ("USER#parent-1", "ACCOUNT_FENCE"): {
                "PK": "USER#parent-1",
                "SK": "ACCOUNT_FENCE",
                "status": "active",
                "generation": 9,
            },
            ("USER#student-1", "ACCOUNT_FENCE"): {
                "PK": "USER#student-1",
                "SK": "ACCOUNT_FENCE",
                "status": "deletion_pending",
                "generation": 7,
            },
        }
        self.first = first
        self.barrier = Barrier(2)
        self.first_committed = Event()
        self.lock = Lock()
        self.attempts = {"writer": 0, "scrub": 0}
        self.operations: list[list[dict[str, Any]]] = []

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool = False):  # noqa: N803
        assert ConsistentRead is True
        with self.lock:
            item = self.items.get((Key["PK"], Key["SK"]))
            return {"Item": deepcopy(item)} if item is not None else {}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        copied = deepcopy(operations)
        kind = "scrub" if len(copied) == 3 else "writer"
        with self.lock:
            self.attempts[kind] += 1
            attempt = self.attempts[kind]
            self.operations.append(copied)
        if attempt == 1:
            self.barrier.wait(timeout=3)
            if kind != self.first:
                assert self.first_committed.wait(timeout=3)

        try:
            with self.lock:
                self._apply(copied, kind)
        finally:
            if attempt == 1 and kind == self.first:
                self.first_committed.set()

    def _apply(self, operations: list[dict[str, Any]], kind: str) -> None:
        profile = self.items[("USER#parent-1", "PROFILE")]
        update = operations[-1]["Update"]
        values = update["ExpressionAttributeValues"]
        expected = values.get(":expected_profile_version", values.get(":expected_version"))
        if expected is None:
            matches = "version" not in profile
        else:
            matches = profile.get("version") == expected
        if not matches:
            raise account_deletion_repo.AccountDeletionConflict("profile CAS lost")

        if kind == "writer":
            if ":locale" in values:
                for field in ("preferred_locale", "preferredLocale", "language"):
                    profile[field] = values[":locale"]
                profile["locale_updated_at"] = values[":updated_at"]
                profile["updated_at"] = values[":updated_at"]
            if ":children" in values:
                profile["child_summaries"] = deepcopy(values[":children"])
            profile["version"] = values[":next_profile_version"]
            return

        names = update["ExpressionAttributeNames"]
        for alias, field in names.items():
            if alias.startswith("#scrub_remove_"):
                profile.pop(field, None)
            elif alias.startswith("#scrub_set_"):
                index = alias.removeprefix("#scrub_set_")
                profile[field] = deepcopy(values[f":scrub_set_{index}"])
        profile["version"] = values[":next_version"]


def _race(table: _ProfileRaceTable, writer) -> tuple[Any, None]:
    scanned = table.get_item(
        Key={"PK": "USER#parent-1", "SK": "PROFILE"}, ConsistentRead=True
    )["Item"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer_future = pool.submit(writer)
        scrub_future = pool.submit(
            account_deletion_repo.scrub_parent_profile_child,
            scanned,
            child_user_id="student-1",
            generation=7,
            table=table,
        )
        return writer_future.result(timeout=5), scrub_future.result(timeout=5)


def test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _ProfileRaceTable(first="scrub")
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    updated, _ = _race(
        table,
        lambda: user_repo.update_locale_preference(
            "parent-1", "en", "2026-07-21T23:59:00+00:00"
        ),
    )

    current = table.items[("USER#parent-1", "PROFILE")]
    assert updated == current
    assert table.attempts == {"writer": 2, "scrub": 1}
    assert current["version"] == 9
    assert current["preferred_locale"] == "en"
    assert current["preferences"]["digest"] == b"\x00weekly\xff"
    assert current["child_summaries"] == [
        {"student_id": "student-2", "name": "sibling"}
    ]


@pytest.mark.parametrize("first", ["scrub", "writer"])
def test_same_sensitive_field_race_always_leaves_scrubbed_linkage_absent(
    monkeypatch: pytest.MonkeyPatch, first: str
) -> None:
    table = _ProfileRaceTable(first=first)
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    result, _ = _race(
        table,
        lambda: user_repo.update_profile_fields_versioned(
            "parent-1",
            update_expression="SET child_summaries = :children",
            expression_attribute_values={
                ":children": [{"student_id": "student-1", "name": "stale"}]
            },
        ),
    )

    current = table.items[("USER#parent-1", "PROFILE")]
    assert all(row.get("student_id") != "student-1" for row in current["child_summaries"])
    if first == "scrub":
        assert result.disposition is user_repo.ProfileWriteDisposition.RETRYABLE
        assert result.attempts == 1
    else:
        assert result.disposition is user_repo.ProfileWriteDisposition.UPDATED
        assert table.attempts["scrub"] == 2


def test_profile_operation_is_narrow_version_cas_with_exactly_one_increment() -> None:
    operation = user_repo.profile_update_operation(
        "parent-1",
        update_expression="SET preferred_locale=:locale",
        expression_attribute_values={":locale": "en"},
        expected_version=11,
    )["Update"]

    assert operation["Key"] == {"PK": "USER#parent-1", "SK": "PROFILE"}
    assert "version=:expected_profile_version" in operation["ConditionExpression"]
    assert operation["ExpressionAttributeValues"][":expected_profile_version"] == 11
    assert operation["ExpressionAttributeValues"][":next_profile_version"] == 12
    assert operation["UpdateExpression"].count(":next_profile_version") == 1

    legacy = user_repo.profile_update_operation(
        "parent-1",
        update_expression="SET preferred_locale=:locale",
        expression_attribute_values={":locale": "en"},
        expected_version=None,
    )["Update"]
    assert "attribute_not_exists(version)" in legacy["ConditionExpression"]
    assert legacy["ExpressionAttributeValues"][":next_profile_version"] == 1


def test_unrelated_profile_cas_loss_is_bounded_and_typed_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _AlwaysContended:
        def __init__(self) -> None:
            self.attempts = 0
            self.operations: list[list[dict[str, Any]]] = []

        def get_item(self, *, Key: dict[str, str], ConsistentRead: bool = False):  # noqa: N803
            assert ConsistentRead is True
            if Key["SK"] == "ACCOUNT_FENCE":
                return {
                    "Item": {
                        **Key,
                        "status": "active",
                        "generation": 2,
                    }
                }
            return {
                "Item": {
                    **Key,
                    "user_id": "parent-1",
                    "role": "parent",
                    "version": 4,
                }
            }

        def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
            self.attempts += 1
            self.operations.append(deepcopy(operations))
            raise account_deletion_repo.AccountDeletionConflict("injected CAS loss")

    table = _AlwaysContended()
    monkeypatch.setattr(user_repo, "get_table", lambda: table)

    result = user_repo.update_profile_fields_versioned(
        "parent-1",
        update_expression="SET preferred_locale=:locale",
        expression_attribute_values={":locale": "en"},
    )

    assert result == user_repo.ProfileWriteResult(
        user_repo.ProfileWriteDisposition.RETRYABLE,
        attempts=user_repo.PROFILE_WRITE_MAX_ATTEMPTS,
    )
    assert table.attempts == user_repo.PROFILE_WRITE_MAX_ATTEMPTS
    assert all("Put" not in operation for batch in table.operations for operation in batch)


def _source_profile_mutations() -> frozenset[str]:
    root = Path(__file__).resolve().parents[1]
    found: set[str] = set()
    for path in (root / "src" / "stoa").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            direct = node.name in {
                "_parent_profile_scrub_operation",
                "materialize_profile_with_fence",
            }
            for member in ast.walk(node):
                if isinstance(member, ast.Dict):
                    for key, value in zip(member.keys, member.values, strict=True):
                        if isinstance(key, ast.Constant) and key.value in {"Update", "Put"}:
                            value_source = ast.get_source_segment(text, value) or ""
                            direct = direct or '"SK": "PROFILE"' in value_source
                elif isinstance(member, ast.Call) and isinstance(member.func, ast.Attribute):
                    if member.func.attr == "update_item":
                        call_source = ast.get_source_segment(text, member) or ""
                        direct = direct or '"SK": "PROFILE"' in call_source
            if direct:
                found.add(f"{path.relative_to(root)}:{node.name}")
    return frozenset(found)


def test_profile_writer_registry_is_closed_against_direct_source_mutations() -> None:
    assert _source_profile_mutations() == user_repo.PROFILE_WRITER_REGISTRY
    root = Path(__file__).resolve().parents[1]
    for location in user_repo.PROFILE_WRITER_REGISTRY:
        path_text, function_name = location.split(":", 1)
        tree = ast.parse((root / path_text).read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        )
        source = ast.get_source_segment(
            (root / path_text).read_text(encoding="utf-8"), function
        )
        assert source is not None and "version" in source
