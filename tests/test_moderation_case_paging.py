"""The moderation queue pages through every case (#110).

The list used to take only `limit`: the 51st case was never shown, and `count`
was the length of the page. Here the queue is read through the route from a
table whose scan pages are three rows long and mostly hold rows that are not
cases, so most scan pages leave a filter nothing to keep.
"""

from __future__ import annotations

import pytest
from fakes.dynamodb import FakeTable
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.db.repositories import moderation_repo
from stoa.routers import admin

SCAN_PAGE = 3


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = FakeTable(page_item_cap=SCAN_PAGE)
    monkeypatch.setattr(moderation_repo, "get_table", lambda: built)
    return built


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin"})
    return TestClient(app)


def _seed_case(table: FakeTable, case_id: str, minute: int, **overrides) -> None:
    created = f"2026-06-08T10:{minute:02d}:00+00:00"
    row = {
        "PK": f"MODERATION#{case_id}",
        "SK": "SUMMARY",
        "entity_type": "moderation_case",
        "case_id": case_id,
        "status": "open",
        "reason": "unsafe_content",
        "severity": "high",
        "surface": "ai_answer",
        "question_id": f"question-{case_id}",
        "student_id": "student-1",
        "privacy_generation": 1,
        "reporter_id": "student-1",
        "reporter_role": "student",
        "created_at": created,
        "updated_at": created,
    }
    row.update(overrides)
    table.seed(row)
    # A case's own history row sits beside it and is not a case.
    table.seed(
        {
            "PK": f"MODERATION#{case_id}",
            "SK": "EVENT#0001",
            "entity_type": "moderation_event",
            "case_id": case_id,
            "created_at": created,
        }
    )


def _seed_filler(table: FakeTable, count: int) -> None:
    for index in range(count):
        table.seed({"PK": f"AAA#filler-{index:02d}", "SK": "ROW", "entity_type": "filler"})


def _walk(client: TestClient, query: str) -> list[dict]:
    """Every page of the list, following `nextCursor` until it is null."""
    pages = []
    cursor = None
    for _ in range(20):
        url = f"/admin/moderation/cases?{query}"
        if cursor:
            url += f"&cursor={cursor}"
        response = client.get(url)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append(body)
        cursor = body["nextCursor"]
        if cursor is None:
            return pages
    raise AssertionError("the cursor never ran out")


def _ids(pages: list[dict]) -> list[list[str]]:
    return [[item["case_id"] for item in page["items"]] for page in pages]


def test_every_case_is_reached_page_by_page_newest_first(table, client) -> None:
    for minute in range(8):
        _seed_case(table, f"mod-{minute}", minute)
    _seed_filler(table, 12)

    pages = _walk(client, "limit=3")

    assert _ids(pages) == [
        ["mod-7", "mod-6", "mod-5"],
        ["mod-4", "mod-3", "mod-2"],
        ["mod-1", "mod-0"],
    ]
    # The whole queue, on every page: not how many this page holds.
    assert [page["count"] for page in pages] == [8, 8, 8]


def test_the_queue_is_whole_past_a_hundred_cases(table, client) -> None:
    # The old list read at most a hundred cases before it filtered and sorted,
    # so the newest ones could be the ones it never saw.
    table.page_item_cap = 25
    for index in range(120):
        _seed_case(table, f"mod-{index:03d}", index % 60)

    pages = _walk(client, "limit=50")

    assert [len(ids) for ids in _ids(pages)] == [50, 50, 20]
    seen = [case_id for ids in _ids(pages) for case_id in ids]
    assert sorted(seen) == [f"mod-{index:03d}" for index in range(120)]
    assert [page["count"] for page in pages] == [120, 120, 120]


def test_a_filter_pages_through_scan_pages_it_leaves_empty(table, client) -> None:
    # Open cases only at the two ends of the queue; the closed ones between them
    # and the filler fill whole scan pages that the filter keeps nothing from.
    for minute in range(10):
        status = "open" if minute in (0, 1, 8, 9) else "closed"
        _seed_case(table, f"mod-{minute}", minute, status=status)
    _seed_case(table, "mod-gone", 5, privacy_deleted=True)
    _seed_filler(table, 9)

    pages = _walk(client, "limit=2&status=open")

    assert _ids(pages) == [["mod-9", "mod-8"], ["mod-1", "mod-0"]]
    assert [page["count"] for page in pages] == [4, 4]


def test_a_filter_with_no_match_is_one_empty_last_page(table, client) -> None:
    for minute in range(4):
        _seed_case(table, f"mod-{minute}", minute, status="closed")
    _seed_filler(table, 6)

    pages = _walk(client, "limit=2&status=open")

    assert pages == [
        {"items": [], "count": 0, "access_pattern": "bounded_scan", "nextCursor": None}
    ]


def test_a_full_last_page_says_it_is_the_last(table, client) -> None:
    for minute in range(4):
        _seed_case(table, f"mod-{minute}", minute)

    pages = _walk(client, "limit=2")

    assert _ids(pages) == [["mod-3", "mod-2"], ["mod-1", "mod-0"]]


def test_cases_reported_in_the_same_instant_are_neither_repeated_nor_skipped(
    table, client
) -> None:
    for case_id in ("mod-a", "mod-b", "mod-c", "mod-d", "mod-e"):
        _seed_case(table, case_id, 30)

    pages = _walk(client, "limit=2")

    assert _ids(pages) == [["mod-e", "mod-d"], ["mod-c", "mod-b"], ["mod-a"]]


def test_a_case_reported_while_paging_does_not_push_a_seen_one_onto_the_next_page(
    table, client
) -> None:
    for minute in range(5):
        _seed_case(table, f"mod-{minute}", minute)

    first = client.get("/admin/moderation/cases?limit=2").json()
    _seed_case(table, "mod-new", 59)
    second = client.get(
        f"/admin/moderation/cases?limit=2&cursor={first['nextCursor']}"
    ).json()

    assert [item["case_id"] for item in first["items"]] == ["mod-4", "mod-3"]
    assert [item["case_id"] for item in second["items"]] == ["mod-2", "mod-1"]
    assert second["count"] == 6


@pytest.mark.parametrize("cursor", ["not-base64!", "e30=", "WyJhIl0=", "WzEsMl0="])
def test_a_cursor_the_list_did_not_hand_out_is_refused(table, client, cursor) -> None:
    _seed_case(table, "mod-0", 0)

    response = client.get(f"/admin/moderation/cases?cursor={cursor}")

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "cursor_invalid"}
