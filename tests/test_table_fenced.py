"""A write behind an account's fence: one entry, `db_table.fenced` (#297, #210).

Every private write used to read the owner's fence, build the fence condition,
put it in front of its own operations and judge the refusal - four steps each
caller assembled by hand. These tests pin the one place that does it now, against
the in-memory table, which evaluates conditions and gives one cancellation reason
per operation the way DynamoDB does.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import EndpointConnectionError

from fakes.dynamodb import FakeTable, transaction_canceled
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo

OWNER = "student-1"
PARENT = "parent-1"
ROW = {"PK": "THING#1", "SK": "META"}


def _fence(user_id: str, *, status: str = "active", generation: int = 3) -> dict:
    return {
        **account_deletion_repo.account_fence_key(user_id),
        "entity_type": "account_fence",
        "user_id": user_id,
        "status": status,
        "generation": generation,
    }


def _create(item: dict | None = None) -> dict:
    return {
        "Put": {
            "Item": {**ROW, "value": "v", **(item or {})},
            "ConditionExpression": "attribute_not_exists(PK)",
        }
    }


@pytest.fixture
def table() -> FakeTable:
    double = FakeTable()
    double.seed(_fence(OWNER), _fence(PARENT, generation=7))
    return double


def _sent(table: FakeTable) -> list[dict]:
    ((_, request),) = [entry for entry in table.requests if entry[0] == "transact_write_items"]
    return request["operations"]


# -- success --------------------------------------------------------------------------


def test_a_write_behind_an_active_fence_commits_with_the_fence_condition_first(table):
    db_table.fenced(OWNER, [_create()], table=table)

    assert table.rows[("THING#1", "META")]["value"] == "v"
    sent = _sent(table)
    assert sent[0] == account_deletion_repo.active_fence_condition(OWNER, 3)
    assert sent[1:] == [_create()]


def test_operations_built_from_the_generation_carry_the_one_that_was_read(table):
    db_table.fenced(
        OWNER, lambda generation: [_create({"account_fence_generation": generation})], table=table
    )

    assert table.rows[("THING#1", "META")]["account_fence_generation"] == 3


def test_a_generation_the_caller_holds_is_checked_without_reading_the_fence_again(table):
    db_table.fenced(OWNER, [_create()], generation=3, table=table)

    assert table.calls["get_item"] == 0
    assert _sent(table)[0] == account_deletion_repo.active_fence_condition(OWNER, 3)


def test_a_write_under_any_generation_asks_only_that_the_fence_be_active(table):
    db_table.fenced(OWNER, [_create()], any_generation=True, table=table)

    assert table.calls["get_item"] == 0
    assert _sent(table)[0] == account_deletion_repo.active_fence_condition(OWNER)
    assert ("THING#1", "META") in table.rows


def test_a_write_under_any_generation_is_still_refused_by_a_closing_fence(table):
    table.seed(_fence(OWNER, status="deletion_pending"))

    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(OWNER, [_create()], any_generation=True, table=table)

    assert ("THING#1", "META") not in table.rows


def test_further_accounts_are_fenced_in_the_same_transaction(table):
    db_table.fenced(OWNER, [_create()], also={PARENT: None}, table=table)

    sent = _sent(table)
    assert sent[:2] == [
        account_deletion_repo.active_fence_condition(OWNER, 3),
        account_deletion_repo.active_fence_condition(PARENT, 7),
    ]


def test_one_account_cannot_be_fenced_twice_in_one_transaction(table):
    with pytest.raises(ValueError):
        db_table.fenced(OWNER, [_create()], also={OWNER: 3}, table=table)


# -- the fence is missing ---------------------------------------------------------------


def test_a_missing_fence_refuses_before_anything_is_sent(table):
    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced("nobody", [_create()], table=table)

    assert table.calls["transact_write_items"] == 0
    assert ("THING#1", "META") not in table.rows


def test_a_missing_fence_under_a_held_generation_is_refused_by_the_transaction(table):
    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced("nobody", [_create()], generation=1, table=table)

    assert ("THING#1", "META") not in table.rows


# -- the fence is not active ----------------------------------------------------------


@pytest.mark.parametrize("status", ["deletion_pending", "deleted"])
def test_a_fence_that_is_not_active_refuses_the_write(table, status):
    table.seed(_fence(OWNER, status=status))

    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(OWNER, [_create()], table=table)

    assert ("THING#1", "META") not in table.rows


def test_a_fence_that_moves_after_it_was_read_refuses_the_write(table):
    """The race the condition is there for: deletion starts between read and write."""

    def built(generation: int) -> list[dict]:
        table.seed(_fence(OWNER, status="deletion_pending", generation=generation))
        return [_create()]

    with pytest.raises(account_deletion_repo.AccountNotWritable) as raised:
        db_table.fenced(OWNER, built, table=table)

    assert isinstance(raised.value, account_deletion_repo.AccountDeletionConflict)
    assert ("THING#1", "META") not in table.rows


def test_a_generation_that_is_no_longer_the_fence_refuses_the_write(table):
    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(OWNER, [_create()], generation=2, table=table)


def test_a_further_account_that_is_not_writable_refuses_the_write(table):
    table.seed(_fence(PARENT, status="deletion_pending", generation=7))

    with pytest.raises(account_deletion_repo.AccountNotWritable):
        db_table.fenced(OWNER, [_create()], also={PARENT: 7}, table=table)

    assert ("THING#1", "META") not in table.rows


# -- the caller's own condition fails --------------------------------------------------


def test_the_callers_own_refusal_names_its_own_operations_only(table):
    table.seed({**ROW, "value": "already"})
    check = {
        "ConditionCheck": {
            "Key": {"PK": "OTHER#1", "SK": "META"},
            "ConditionExpression": "attribute_not_exists(PK)",
        }
    }

    with pytest.raises(db_table.WriteRefused) as raised:
        db_table.fenced(OWNER, [check, _create()], table=table)

    refused = raised.value
    assert not isinstance(refused, account_deletion_repo.AccountDeletionConflict)
    assert refused.code == "TransactionCanceledException"
    assert refused.failed_conditions == (1,)
    assert len(refused.reasons) == 2
    assert table.rows[("THING#1", "META")]["value"] == "already"


class _Refusing(FakeTable):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__()
        self.seed(_fence(OWNER))
        self.reasons = reasons

    def transact_write_items(self, **kwargs):
        raise transaction_canceled(self.reasons)


def test_a_busy_fence_row_does_not_pass_for_the_callers_operations_succeeding():
    with pytest.raises(db_table.WriteRefused) as raised:
        db_table.fenced(OWNER, [_create()], table=_Refusing(["TransactionConflict", "None"]))

    assert not isinstance(raised.value, account_deletion_repo.AccountDeletionConflict)
    assert raised.value.reasons == ()


def test_an_unavailable_table_is_reported_as_such():
    class _Down(FakeTable):
        def transact_write_items(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://dynamodb")

    down = _Down()
    down.seed(_fence(OWNER))

    with pytest.raises(db_table.TableUnavailable):
        db_table.fenced(OWNER, [_create()], table=down)
