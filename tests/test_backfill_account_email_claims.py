"""What the email-claim backfill may and may not do to the table.

Card 009 guards (email, role) with a claim row written beside the profile.
Accounts opened before it have none, so until this script runs those addresses
are back to being protected by a read of an eventually consistent index. The
script therefore writes to production data, which is the one kind of change
this repository does not let anyone eyeball: `--apply` is a red line.

These pin the three things that would be expensive to get wrong -- writing
without being asked, writing over a guard that already exists, and quietly
picking a winner when two accounts already share an address.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_account_email_claims.py"
    spec = importlib.util.spec_from_file_location("backfill_account_email_claims", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


backfill = _load()


class FakeTable:
    """Enough of a table to answer scan/get/put, and to refuse a taken claim."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = {(row["PK"], row["SK"]): dict(row) for row in items}
        self.puts: list[dict[str, Any]] = []

    def scan(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        return {
            "Items": [
                dict(row)
                for (pk, sk), row in self.items.items()
                if sk == values[":sk"] and pk.startswith(values[":pk"])
            ]
        }

    def get_item(self, *, Key, ConsistentRead=False):  # noqa: N803
        row = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(row)} if row is not None else {}

    def put_item(self, *, Item, ConditionExpression=None, **kwargs):  # noqa: N803
        key = (Item["PK"], Item["SK"])
        if ConditionExpression and "attribute_not_exists" in ConditionExpression:
            if key in self.items:
                from botocore.exceptions import ClientError

                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
                )
        self.items[key] = dict(Item)
        self.puts.append(dict(Item))


def _profile(user_id: str, email: str, role: str) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "email": email,
        "role": role,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _run(table: FakeTable, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(
        backfill.boto3, "resource", lambda *a, **k: type("R", (), {"Table": lambda _s, _n: table})()
    )
    monkeypatch.setattr("sys.argv", ["backfill", *argv])
    return backfill.main()


def test_一次报告不写任何东西(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default has to be inert: this reads production and reports on it."""
    table = FakeTable([_profile("student_1", "a@example.ch", "student")])

    assert _run(table, monkeypatch) == 0
    assert table.puts == []


def test_apply_给缺占位行的账号补上(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable([_profile("student_1", "A@Example.CH", "student")])

    assert _run(table, monkeypatch, "--apply") == 0

    assert len(table.puts) == 1
    written = table.puts[0]
    assert written["PK"] == "EMAIL#a@example.ch#student"
    assert written["claimed_email"] == "a@example.ch"
    assert written["account_id"] == "student_1"


def test_已经有占位行的账号不会被重写(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rerunning is how anyone checks the first run worked.

    The placeholder here stands in a third account's name over a pair this profile
    carries, so the run also has something to say: it leaves the row exactly where it
    is and exits nonzero rather than reporting a table it did not put right.
    """
    table = FakeTable(
        [
            _profile("student_1", "a@example.ch", "student"),
            {
                "PK": "EMAIL#a@example.ch#student",
                "SK": "EMAIL_CLAIM",
                "account_id": "someone_else",
            },
        ]
    )

    assert _run(table, monkeypatch, "--apply") == 1
    assert table.puts == []
    assert table.items[("EMAIL#a@example.ch#student", "EMAIL_CLAIM")]["account_id"] == "someone_else"


def test_同一地址不同角色各得一个占位行(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pair is the key: a teacher who is also a parent holds two accounts."""
    table = FakeTable(
        [
            _profile("teacher_1", "t@example.ch", "teacher"),
            _profile("parent_1", "t@example.ch", "parent"),
        ]
    )

    assert _run(table, monkeypatch, "--apply") == 0

    assert sorted(row["PK"] for row in table.puts) == [
        "EMAIL#t@example.ch#parent",
        "EMAIL#t@example.ch#teacher",
    ]


def test_两个账号已经共用一对时不挑赢家(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only one can hold the claim, and which one is a question about two people.

    Writing either would settle it silently, and the row that lost would keep
    working until something else noticed. Reporting and refusing is the answer
    a backfill is allowed to give.
    """
    table = FakeTable(
        [
            _profile("student_1", "dup@example.ch", "student"),
            _profile("student_2", "dup@example.ch", "student"),
        ]
    )

    assert _run(table, monkeypatch, "--apply") == 1
    assert table.puts == []


def test_半途失败停放的账号不占地址(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its address was rewritten to a value with no "@" precisely to free it."""
    table = FakeTable([_profile("student_1", "provisioning_failed:student_1", "student")])

    assert _run(table, monkeypatch, "--apply") == 0
    assert table.puts == []


def test_verify_在还有账号缺占位行时失败(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable([_profile("student_1", "a@example.ch", "student")])

    assert _run(table, monkeypatch, "--verify") == 1


def test_verify_在全部补齐之后通过(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable(
        [
            _profile("student_1", "a@example.ch", "student"),
            {"PK": "EMAIL#a@example.ch#student", "SK": "EMAIL_CLAIM", "account_id": "student_1"},
        ]
    )

    assert _run(table, monkeypatch, "--verify") == 0


def test_运行途中被人抢走的占位行不会被覆盖(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live claim is doing its job; this script must not take it away."""
    table = FakeTable([_profile("student_1", "a@example.ch", "student")])
    real_put = table.put_item

    def racing_put(*, Item, ConditionExpression=None, **kwargs):  # noqa: N803
        table.items[("EMAIL#a@example.ch#student", "EMAIL_CLAIM")] = {
            "PK": "EMAIL#a@example.ch#student",
            "SK": "EMAIL_CLAIM",
            "account_id": "opened_while_this_ran",
        }
        table.put_item = real_put
        return real_put(Item=Item, ConditionExpression=ConditionExpression, **kwargs)

    table.put_item = racing_put

    assert _run(table, monkeypatch, "--apply") == 0
    assert table.items[("EMAIL#a@example.ch#student", "EMAIL_CLAIM")]["account_id"] == (
        "opened_while_this_ran"
    )


def test_占位行的键与仓储层逐字一致() -> None:
    """Two spellings of this key means the guard and the backfill guard nothing."""
    from stoa.db.repositories import account_email_claim_repo

    assert backfill.claim_key("A@Example.CH", "student") == account_email_claim_repo.claim_key(
        email="A@Example.CH", role="student"
    )
    assert backfill.CLAIM_CONDITION == account_email_claim_repo.CLAIM_CONDITION


def test_verify_报出没有活账号站在后面的占位行(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other direction: a deleted account's placeholder outliving it.

    The tombstone carries no address, so nothing in the table names the pair any
    more. Only a sweep from the placeholder side can see it.
    """
    table = FakeTable(
        [
            {
                "PK": "USER#gone_1",
                "SK": "PROFILE",
                "entity_type": "user_profile_deletion_tombstone",
                "status": "deleted",
            },
            {
                "PK": "EMAIL#gone@example.ch#student",
                "SK": "EMAIL_CLAIM",
                "account_id": "gone_1",
            },
        ]
    )

    assert _run(table, monkeypatch, "--verify") == 1
    assert table.puts == []


def test_verify_不会把活账号自己的占位行当成孤儿(monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative control for the sweep above: the ordinary table must read clean."""
    table = FakeTable(
        [
            _profile("student_1", "A@Example.CH", "student"),
            {
                "PK": "EMAIL#a@example.ch#student",
                "SK": "EMAIL_CLAIM",
                "account_id": "student_1",
            },
        ]
    )

    assert _run(table, monkeypatch, "--verify") == 0
