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
from boto3.dynamodb.conditions import Attr
from fakes.dynamodb import FakeTable

from stoa.db import table as db_table
from stoa.db.repositories import (
    curriculum_ops_repo,
    moderation_repo,
    notification_repo,
    websocket_repo,
)

FILLER_PAGES = 4
PAGE = 3


@pytest.fixture
def table(fake_table) -> FakeTable:
    return fake_table


def _bury(table: FakeTable) -> None:
    """Rows that sort first, and pages small enough that the wanted row is not on one."""
    for index in range(FILLER_PAGES * PAGE):
        table.seed({"PK": f"AAA#filler-{index:02d}", "SK": "ROW", "entity_type": "filler"})
    table.page_item_cap = PAGE


def test_a_push_token_is_found_on_whichever_page_of_its_person_it_falls(table) -> None:
    # The worst of these: nothing is sent, and nothing says so. It is read from
    # its person's bucket now (#624), every page of it.
    for index in range(FILLER_PAGES * PAGE + 1):
        row = {
            "PK": notification_repo.push_token_pk("u-1", f"tok-{index:02d}"),
            "SK": "META",
            "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
            "user_id": "u-1",
            "token_reference": f"tok-{index:02d}",
            "token_hash": f"hash-{index:02d}",
            "status": "active" if index == FILLER_PAGES * PAGE else "revoked",
            "created_at": f"2026-11-25T10:{index:02d}:00Z",
        }
        table.seed({**row, **notification_repo.push_token_index_fields(row)})
    _bury(table)

    tokens = notification_repo.list_user_push_tokens("u-1", status="active")

    assert [item["token_reference"] for item in tokens] == [f"tok-{FILLER_PAGES * PAGE:02d}"]


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

    # The administrators' list of the whole site still scans (#613).
    assert [item["notification_id"] for item in notification_repo.list_all_events()] == ["n-1"]


def test_a_connection_is_found_on_whichever_page_of_its_role_it_falls(table) -> None:
    # `delete_stale_connections` sweeps what the role lists return (#624): a
    # connection it never reads is one it never cleans up.
    for index in range(FILLER_PAGES * PAGE + 1):
        row = {
            "PK": websocket_repo.connection_pk(f"c-{index:02d}"),
            "SK": "META",
            "entity_type": websocket_repo.CONNECTION_ENTITY,
            "connection_id": f"c-{index:02d}",
            "user_id": f"u-{index:02d}",
            "role": "student",
            "connected_at": f"2026-11-25T10:{index:02d}:00Z",
            "expires_at": 10 if index == FILLER_PAGES * PAGE else 30,
        }
        table.seed({**row, **websocket_repo.index_fields(row)})
    _bury(table)

    assert len(websocket_repo.list_site_connections()) == FILLER_PAGES * PAGE + 1
    assert websocket_repo.delete_stale_connections(now_epoch=20) == [f"c-{FILLER_PAGES * PAGE:02d}"]


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

    assert [item["PK"] for item in curriculum_ops_repo.list_worklist().versions] == ["CURRICULUM#c-1"]


def test_a_lesson_pointer_is_found_wherever_its_row_falls(table) -> None:
    # The worklist names each lesson's live version from these rows (#111).
    table.seed(
        {
            "PK": "CURRICULUM_POINTER#l-1",
            "SK": "META",
            "entity_type": curriculum_ops_repo.POINTER_ENTITY,
            "public_id": "l-1",
            "published_version_id": "v-2",
        }
    )
    _bury(table)

    rows = curriculum_ops_repo.list_worklist()

    assert rows.published_version_ids == {"l-1": "v-2"}
    assert rows.versions == []


def test_a_cap_on_matches_is_a_cap_on_matches(table) -> None:
    # `want` is what the old `Limit=` meant. Without it, reading every page
    # turns "at most N" into "all of them".
    for index in range(5):
        table.seed({"PK": f"MODERATION#m-{index}", "SK": "META", "entity_type": "moderation_case"})
    table.page_item_cap = PAGE

    found = db_table.rows(
        "scan", want=2, FilterExpression=Attr("entity_type").eq("moderation_case")
    )

    assert len(found) == 2


def test_no_row_limit_reaches_the_table() -> None:
    # A `Limit` would make every page a few rows wide and spend the page budget
    # crossing a table this walks in a handful of reads; `want` is what is meant.
    with pytest.raises(ValueError, match="want"):
        db_table.rows("scan", table=FakeTable(), want=10, Limit=25, FilterExpression="x")


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
