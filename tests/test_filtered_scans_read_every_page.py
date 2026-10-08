"""Filtered scans that stopped at the first page of the table (#95, item 3).

`Limit` on a filtered scan bounds the rows *read*, not the rows matched. A
reader written as `_scan(table, FilterExpression=..., Limit=100)` therefore
returns whatever of the first hundred rows happened to match — which, once the
table holds more than a hundred rows of anything else, is nothing. It reads as
"at most a hundred of these", and it is silent when it finds none.

The teacher's help request was the one that was found in production: the first
page stopped after 1604 rows and the request was behind it. These are the rest
of the same shape. Each test puts the row being looked for behind a few pages
of rows that sort before it, which is where a new row is in a growing table.
"""

from __future__ import annotations

import pytest
from fakes.dynamodb import FakeTable

from stoa.db.dynamodb import scan_every_page
from stoa.db.repositories import (
    curriculum_ops_repo,
    moderation_repo,
    notification_repo,
    websocket_repo,
)

FILLER_PAGES = 4
PAGE = 3


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = FakeTable()
    for module in (curriculum_ops_repo, moderation_repo, notification_repo, websocket_repo):
        monkeypatch.setattr(module, "get_table", lambda built=built: built)
    return built


def _bury(table: FakeTable) -> None:
    """Rows that sort first, and pages small enough that the wanted row is not on one."""
    for index in range(FILLER_PAGES * PAGE):
        table.seed({"PK": f"AAA#filler-{index:02d}", "SK": "ROW", "entity_type": "filler"})
    table.page_item_cap = PAGE


def test_a_push_token_is_found_wherever_its_row_falls(table) -> None:
    # The worst of these: nothing is sent, and nothing says so.
    table.seed(
        {
            "PK": notification_repo.push_token_pk("u-1", "tok-1"),
            "SK": "META",
            "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
            "user_id": "u-1",
            "token_reference": "tok-1",
            "status": "active",
        }
    )
    _bury(table)

    tokens = notification_repo.list_push_tokens("u-1")

    assert [item["token_reference"] for item in tokens] == ["tok-1"]


def test_a_notification_event_is_found_wherever_its_row_falls(table) -> None:
    table.seed(
        {
            "PK": "NOTIFICATION#n-1",
            "SK": "META",
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "notification_id": "n-1",
            "user_id": "u-1",
        }
    )
    _bury(table)

    assert [item["notification_id"] for item in notification_repo.list_events()] == ["n-1"]


def test_a_connection_is_found_wherever_its_row_falls(table) -> None:
    # `delete_stale_connections` sweeps what this returns: a connection it
    # never reads is one that is never cleaned up.
    table.seed(
        {
            "PK": "WSCONN#c-1",
            "SK": "META",
            "entity_type": websocket_repo.CONNECTION_ENTITY,
            "connection_id": "c-1",
            "expires_at": 10,
        }
    )
    _bury(table)

    assert [item["connection_id"] for item in websocket_repo.list_connections()] == ["c-1"]
    assert websocket_repo.delete_stale_connections(now_epoch=20) == ["c-1"]


def test_a_moderation_case_is_found_wherever_its_row_falls(table) -> None:
    table.seed(
        {
            "PK": "MODERATION#m-1",
            "SK": "META",
            "entity_type": "moderation_case",
            "case_id": "m-1",
        }
    )
    _bury(table)

    assert [item["case_id"] for item in moderation_repo.list_cases()] == ["m-1"]


def test_an_active_assignment_is_found_wherever_its_row_falls(table) -> None:
    # This one answers "is anything still using this lesson?". Missing a row
    # here does not shorten a list; it turns a no into a yes.
    table.seed(
        {
            "PK": "ASSIGNMENT#a-1",
            "SK": "META",
            "entity_type": "learning_assignment",
            "lesson_id": "l-1",
            "status": "assigned",
        }
    )
    _bury(table)

    refs = curriculum_ops_repo.list_active_assignment_refs("l-1")

    assert [item["PK"] for item in refs] == ["ASSIGNMENT#a-1"]


def test_a_curriculum_version_is_found_wherever_its_row_falls(table) -> None:
    table.seed(
        {
            "PK": "CURRICULUM#c-1",
            "SK": "V1",
            "entity_type": curriculum_ops_repo.VERSION_ENTITY,
            "state": "draft",
            "updated_at": "2026-10-08T00:00:00Z",
        }
    )
    _bury(table)

    assert [item["PK"] for item in curriculum_ops_repo.list_worklist()] == ["CURRICULUM#c-1"]


def test_a_cap_on_matches_is_a_cap_on_matches(table) -> None:
    # `want` is what the old `Limit=` meant. Without it, reading every page
    # turns "at most N" into "all of them".
    for index in range(5):
        table.seed(
            {
                "PK": notification_repo.push_token_pk("u-1", f"tok-{index}"),
                "SK": "META",
                "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
                "user_id": "u-1",
                "token_reference": f"tok-{index}",
            }
        )
    table.page_item_cap = PAGE

    assert len(notification_repo.list_push_tokens("u-1", limit=2)) == 2


def test_no_row_limit_reaches_the_table(table) -> None:
    # A `Limit` left in the kwargs would make every page a few rows wide and
    # spend the page budget crossing a table this walks in a handful of reads.
    seen: list[object] = []

    def recording(_table: object, **kwargs: object) -> dict[str, object]:
        seen.append(kwargs.get("Limit"))
        return {"Items": []}

    scan_every_page(recording, object(), want=10, Limit=25, FilterExpression="x")

    assert seen == [None]


def test_the_limit_still_caps_what_comes_back(table) -> None:
    # Reading every page must not turn "at most N" into "all of them".
    for index in range(7):
        table.seed(
            {
                "PK": f"MODERATION#m-{index}",
                "SK": "META",
                "entity_type": "moderation_case",
                "case_id": f"m-{index}",
            }
        )
    table.page_item_cap = PAGE

    assert len(moderation_repo.list_cases(limit=4)) == 4
