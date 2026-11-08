"""Reading page by page through the table gateway, and the page token (#298).

`stoa.db.table.pages` is the one place a read goes on past the table's page and
the one place a continuation key is checked; `page_token` / `read_page_token` the
one form a position leaves the service in. Five token cases come first, because
an API listing lives or dies by them: a read across several pages, an empty one,
a forged token, a token made for somebody else's listing, and a token in the
format from before this gateway.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from itertools import islice
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import table as db_table

PARTITION = "REPORT#r-1"


def _timeline(table: FakeTable, count: int, partition: str = PARTITION) -> None:
    for index in range(count):
        table.seed({"PK": partition, "SK": f"AUDIT#{index:03d}", "entity_type": "audit"})


def _query(partition: str = PARTITION) -> dict[str, Any]:
    return {
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :audit)",
        "ExpressionAttributeValues": {":pk": partition, ":audit": "AUDIT#"},
    }


def _in(partition: str):
    return lambda key: key["PK"] == partition


# -- the five token cases ---------------------------------------------------------------


def test_a_listing_continues_page_after_page_until_the_last(fake_table: FakeTable) -> None:
    _timeline(fake_table, 7)
    scope = f"report_audit:{PARTITION}"
    seen: list[str] = []
    token = None
    for _ in range(10):
        page = next(
            db_table.pages(
                "query", scope=scope, token=token, within=_in(PARTITION), Limit=3, **_query()
            )
        )
        seen.extend(item["SK"] for item in page.items)
        token = page.next_token
        if token is None:
            break

    assert seen == [f"AUDIT#{index:03d}" for index in range(7)]


def test_an_empty_listing_is_one_page_with_nothing_after_it(fake_table: FakeTable) -> None:
    walk = db_table.pages("query", scope="report_audit:REPORT#none", **_query("REPORT#none"))

    page = next(walk)

    assert page.items == []
    assert page.last_key is None
    assert page.next_token is None
    assert list(walk) == []


@pytest.mark.parametrize(
    "forged",
    [
        "",
        "2.",
        "2.not base64!",
        "2." + base64.urlsafe_b64encode(b"not json").decode().rstrip("="),
        "2." + base64.urlsafe_b64encode(json.dumps(["a list"]).encode()).decode().rstrip("="),
        "2." + base64.urlsafe_b64encode(
            json.dumps({"s": "report_audit:REPORT#r-1", "p": {"PK": {"S": "x"}}}).encode()
        ).decode().rstrip("="),
        "2." + base64.urlsafe_b64encode(
            json.dumps({"s": "report_audit:REPORT#r-1", "p": {}, "extra": 1}).encode()
        ).decode().rstrip("="),
        "2." + "A" * 4096,
    ],
)
def test_a_forged_token_is_refused_before_the_table_is_asked(forged: str) -> None:
    class _Untouchable:
        def query(self, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("a forged token reached the table")

    with pytest.raises(db_table.PageTokenInvalid):
        db_table.pages(
            "query",
            scope=f"report_audit:{PARTITION}",
            token=forged,
            within=_in(PARTITION),
            table=_Untouchable(),
            **_query(),
        )


def test_a_token_made_for_somebody_elses_listing_is_refused(fake_table: FakeTable) -> None:
    _timeline(fake_table, 4, "REPORT#theirs")
    theirs = next(
        db_table.pages("query", scope="report_audit:REPORT#theirs", Limit=2, **_query("REPORT#theirs"))
    ).next_token
    assert theirs is not None

    with pytest.raises(db_table.PageTokenInvalid):
        db_table.pages(
            "query", scope=f"report_audit:{PARTITION}", token=theirs, within=_in(PARTITION), **_query()
        )
    # A hand-made token naming this listing but pointing into another partition
    # is caught by the listing's own rule, not by the table refusing the request.
    hand_made = db_table.page_token(f"report_audit:{PARTITION}", {"PK": "REPORT#theirs", "SK": "AUDIT#001"})
    with pytest.raises(db_table.PageTokenInvalid):
        db_table.pages(
            "query", scope=f"report_audit:{PARTITION}", token=hand_made, within=_in(PARTITION), **_query()
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"PK": PARTITION, "SK": "AUDIT#001"},
        {"scope": "report_audit", "key": {"PK": PARTITION, "SK": "AUDIT#001"}},
    ],
)
def test_a_token_in_the_format_from_before_the_gateway_is_refused(payload: dict[str, Any]) -> None:
    # What `report_repo.encode_*_page_token` used to hand out. The listing starts
    # over from its first page rather than guess what an old token meant.
    legacy = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode()

    with pytest.raises(db_table.PageTokenInvalid):
        db_table.read_page_token(legacy, f"report_audit:{PARTITION}")


# -- the token itself -------------------------------------------------------------------


def test_a_token_carries_strings_and_numbers_back_as_they_were() -> None:
    position = {"PK": "P", "SK": "S", "created_at": "2026-11-08", "score": Decimal("12")}

    token = db_table.page_token("listing", position)

    assert token.startswith("2.")
    assert "=" not in token and "/" not in token and "+" not in token
    assert db_table.read_page_token(token, "listing") == position
    assert isinstance(db_table.read_page_token(token, "listing")["score"], Decimal)


def test_a_token_is_held_to_the_key_its_read_continues_from() -> None:
    token = db_table.page_token("listing", {"PK": "P", "SK": "S", "extra": "x"})

    with pytest.raises(db_table.PageTokenInvalid):
        db_table.read_page_token(token, "listing", key=db_table.BASE_KEY)


def test_a_position_that_is_not_strings_and_numbers_makes_no_token() -> None:
    for position in ({"PK": None}, {"PK": True}, {"PK": ["a"]}, {}):
        with pytest.raises(ValueError):
            db_table.page_token("listing", position)


def test_a_page_read_without_a_scope_hands_out_no_token(fake_table: FakeTable) -> None:
    _timeline(fake_table, 3)

    page = next(db_table.pages("query", Limit=1, **_query()))

    assert page.last_key == {"PK": PARTITION, "SK": "AUDIT#000"}
    with pytest.raises(ValueError):
        page.next_token


# -- a sweep's stored place -------------------------------------------------------------


def test_a_sweep_continues_from_the_key_it_kept(fake_table: FakeTable) -> None:
    _timeline(fake_table, 5)
    first = next(db_table.pages("scan", Limit=2))

    rest = [
        item["SK"]
        for page in db_table.pages("scan", start=first.last_key, Limit=2)
        for item in page.items
    ]

    assert [item["SK"] for item in first.items] + rest == [f"AUDIT#{index:03d}" for index in range(5)]


@pytest.mark.parametrize(
    "start",
    [
        {"PK": "P"},
        {"PK": "P", "SK": ""},
        {"PK": "P", "SK": "S", "extra": "x"},
        {"PK": "P", "SK": None},
        {"PK": "P", "SK": True},
        ["PK", "SK"],
    ],
)
def test_a_kept_key_that_is_not_a_key_is_refused(start: object) -> None:
    with pytest.raises(db_table.PageTokenInvalid):
        db_table.pages("scan", start=start, table=FakeTable())


def test_a_page_whose_key_is_malformed_is_not_followed() -> None:
    class _Broken:
        def scan(self, **_kwargs: object) -> dict[str, object]:
            return {"Items": [], "LastEvaluatedKey": {"PK": "P"}}

    with pytest.raises(db_table.TableUnavailable) as unavailable:
        next(db_table.pages("scan", table=_Broken()))
    assert unavailable.value.code == "malformed_page_key"


@pytest.mark.parametrize("response", [None, {"Items": "rows"}, {"Items": ["row"]}])
def test_a_response_that_is_not_a_page_is_unavailable(response: object) -> None:
    class _Broken:
        def scan(self, **_kwargs: object) -> object:
            return response

    with pytest.raises(db_table.TableUnavailable) as unavailable:
        next(db_table.pages("scan", table=_Broken()))
    assert unavailable.value.code == "malformed_page"


def test_a_table_that_cannot_read_is_unavailable() -> None:
    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.pages("query", table=object())
    assert unavailable.value.code == "no_query_entry"


def test_a_start_key_is_named_with_start_not_exclusive_start_key() -> None:
    with pytest.raises(ValueError):
        db_table.pages("scan", table=FakeTable(), ExclusiveStartKey={"PK": "P", "SK": "S"})


def test_the_caller_decides_how_many_pages_to_read(fake_table: FakeTable) -> None:
    _timeline(fake_table, 9)
    asked: list[dict[str, Any]] = []
    real_scan = fake_table.scan

    def scan(**kwargs: Any) -> dict[str, Any]:
        asked.append(kwargs)
        return real_scan(**kwargs)

    fake_table.scan = scan  # type: ignore[method-assign]

    taken = list(islice(db_table.pages("scan", Limit=2), 2))

    assert len(taken) == 2
    assert len(asked) == 2


# -- every row --------------------------------------------------------------------------


def test_rows_reads_every_page_and_stops_at_what_was_wanted(fake_table: FakeTable) -> None:
    _timeline(fake_table, 6)
    fake_table.page_item_cap = 2

    assert len(db_table.rows("scan")) == 6
    assert len(db_table.rows("scan", want=3)) == 3


def test_rows_refuses_a_table_that_does_not_move_forward() -> None:
    class _Stuck:
        def scan(self, **_kwargs: object) -> dict[str, object]:
            return {"Items": [], "LastEvaluatedKey": {"PK": "P", "SK": "S"}}

    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.rows("scan", table=_Stuck())
    assert unavailable.value.code == "page_did_not_advance"


def test_rows_says_so_when_the_budget_runs_out(fake_table: FakeTable) -> None:
    _timeline(fake_table, 5)
    fake_table.page_item_cap = 1

    with pytest.raises(db_table.TableUnavailable) as unavailable:
        db_table.rows("scan", page_budget=3)
    assert unavailable.value.code == "page_budget_spent"


# -- the installation point -------------------------------------------------------------


def test_every_test_starts_with_an_empty_table_installed() -> None:
    installed = db_table.table()

    assert isinstance(installed, FakeTable)
    assert installed.rows == {}


def test_fake_table_is_the_table_the_gateway_reads(fake_table: FakeTable) -> None:
    fake_table.seed({"PK": "P", "SK": "S"})

    assert db_table.table() is fake_table
    assert db_table.rows("scan") == [{"PK": "P", "SK": "S"}]
