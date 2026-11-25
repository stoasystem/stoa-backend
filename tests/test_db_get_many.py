"""`db_table.get_many`: one round trip per hundred keys, nothing silently dropped."""

from __future__ import annotations

from typing import Any

import pytest
from fakes.dynamodb import FakeTable

from stoa.db import table as db_table


def _row(index: int) -> dict[str, Any]:
    return {"PK": f"USER#u{index}", "SK": "PROFILE", "user_id": f"u{index}"}


def test_reads_found_rows_in_one_round_trip_and_leaves_missing_ones_out() -> None:
    table = FakeTable()
    table.seed(_row(1), _row(2))
    found = db_table.get_many(
        [{"PK": "USER#u1", "SK": "PROFILE"}, {"PK": "USER#u2", "SK": "PROFILE"},
         {"PK": "USER#missing", "SK": "PROFILE"}, {"PK": "USER#u1", "SK": "PROFILE"}],
        table=table,
    )
    assert set(found) == {("USER#u1", "PROFILE"), ("USER#u2", "PROFILE")}
    assert found[("USER#u1", "PROFILE")]["user_id"] == "u1"
    assert table.calls["batch_get_item"] == 1
    assert table.calls["get_item"] == 0


def test_splits_requests_at_one_hundred_keys() -> None:
    table = FakeTable()
    table.seed(*(_row(index) for index in range(250)))
    found = db_table.get_many(
        ({"PK": f"USER#u{index}", "SK": "PROFILE"} for index in range(250)), table=table
    )
    assert len(found) == 250
    assert table.calls["batch_get_item"] == 3


def test_no_keys_reads_nothing() -> None:
    table = FakeTable()
    assert db_table.get_many([], table=table) == {}
    assert sum(table.calls.values()) == 0


class _Stubborn(FakeTable):
    def batch_get_item(self, **kwargs: Any) -> dict[str, Any]:
        super().batch_get_item(**kwargs)
        name, request = next(iter(kwargs["RequestItems"].items()))
        return {"Responses": {name: []}, "UnprocessedKeys": {name: {"Keys": request["Keys"]}}}


def test_keys_still_unprocessed_after_retries_raise_instead_of_answering_short() -> None:
    table = _Stubborn()
    table.seed(_row(1))
    with pytest.raises(db_table.TableUnavailable):
        db_table.get_many([{"PK": "USER#u1", "SK": "PROFILE"}], table=table)
    assert table.calls["batch_get_item"] == db_table.BATCH_GET_ATTEMPTS


class _NoBatch:
    def __init__(self, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.rows = rows
        self.gets = 0

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.gets += 1
        item = self.rows.get((kwargs["Key"]["PK"], kwargs["Key"]["SK"]))
        return {"Item": item} if item else {}


def test_a_double_without_batch_reads_key_by_key() -> None:
    double = _NoBatch({("USER#u1", "PROFILE"): _row(1)})
    found = db_table.get_many(
        [{"PK": "USER#u1", "SK": "PROFILE"}, {"PK": "USER#u2", "SK": "PROFILE"}], table=double
    )
    assert list(found) == [("USER#u1", "PROFILE")]
    assert double.gets == 2


class _BotoLikeTable:
    """What `boto3.resource(...).Table(name)` offers: get_item and meta, no batch."""

    name = "stoa-main"

    class meta:  # noqa: N801
        client = object()

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("a real table must be read in batches, not key by key")


class _Resource:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def batch_get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        keys = kwargs["RequestItems"]["stoa-main"]["Keys"]
        return {"Responses": {"stoa-main": [dict(key, found=True) for key in keys]}}


def test_a_real_table_passed_explicitly_is_read_through_its_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audit's finding: callers pass `db_table.table()`, a boto3 Table."""
    resource = _Resource()
    monkeypatch.setattr(db_table, "_resource", lambda: resource)
    found = db_table.get_many(
        [{"PK": "USER#u1", "SK": "PROFILE"}, {"PK": "USER#u2", "SK": "PROFILE"}],
        table=_BotoLikeTable(),
        consistent=True,
    )
    assert len(found) == 2
    assert len(resource.requests) == 1
    assert resource.requests[0]["RequestItems"]["stoa-main"]["ConsistentRead"] is True
