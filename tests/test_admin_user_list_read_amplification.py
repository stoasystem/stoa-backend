"""Card 002 #7: what one page of GET /admin/users costs in DynamoDB round trips.

The endpoint answers from one scan and then resolves every listed account's
parent/child links one account at a time, so its cost is not the page size but
the page size times the links behind it. API Gateway cuts the request off at 29
seconds, which makes that multiplier a correctness property rather than a
performance note - past some page this route stops answering at all.

So the multiplier is measured here against a counting table and pinned exactly.
It is pinned in both directions on purpose: a drop is as much a change to this
route as a rise, and either one should be somebody's decision rather than a
surprise found in production.
"""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable

from stoa.db import table as db_table
from stoa.db.repositories import parent_link_repo, user_repo
from stoa.routers import admin

PARENTS = 200
CHILDREN_PER_PARENT = 3


CountingTable = FakeTable
"""The shared double counts its own round trips, which is all this file needed.

What it does *not* do is hand back rows in the order they were planted. A real
table reads in key order, so a layout that puts profiles behind other rows costs
more than one scan however the fixture was written - see the scan counts below.
"""


def _seed(table: CountingTable) -> None:
    """Parent profiles first, so a full page is parents and nothing else.

    That is the expensive shape and therefore the one worth holding. Both sides
    now ask the relationship judge, so a parent row and a student row cost the
    same: a link query, then per counterpart the two link rows, the two profiles
    and the counterpart's account number. (A student row used to skip the judge
    and cost one read per parent; no student reaches the pages pinned here.)
    """
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        table.seed({
            "PK": f"USER#{parent_id}",
            "SK": "PROFILE",
            "user_id": parent_id,
            "role": "parent",
            "account_status": "active",
            "email": f"{parent_id}@stoa.test",
            "name": parent_id,
            "account_number": f"P26-{index:04d}",
            "created_at": "2026-01-01T00:00:00+00:00",
        })
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        for child in range(CHILDREN_PER_PARENT):
            student_id = f"student-{index}-{child}"
            table.seed({
                "PK": f"USER#{student_id}",
                "SK": "PROFILE",
                "user_id": student_id,
                "role": "student",
                "account_status": "active",
                "email": f"{student_id}@stoa.test",
                "name": student_id,
                "account_number": f"S26-{index:04d}{child}",
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            # A current link as the link writer stores it: both sides active and
            # agreeing on the relationship and the write that last touched them.
            link = {
                "entity_type": parent_link_repo.ENTITY_TYPE,
                "parent_id": parent_id,
                "student_id": student_id,
                "relationship": "child",
                "status": parent_link_repo.STATUS_ACTIVE,
                "link_updated_at": "2026-01-01T00:00:00+00:00",
            }
            table.seed({
                "PK": f"PARENT#{parent_id}",
                "SK": f"CHILD#{student_id}",
                **link,
            })
            table.seed({
                "PK": f"STUDENT#{student_id}",
                "SK": f"PARENT#{parent_id}",
                **link,
            })


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> CountingTable:
    counting = CountingTable()
    _seed(counting)
    for module in (parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)
    db_table.install(counting)
    return counting


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin", "accountStatus": "active"})
    return TestClient(app)


# Six pages of link rows sort ahead of the first profile, so the scan reaches the
# profiles on its seventh. The count used to be pinned at 1 because the double read
# rows in the order the fixture planted them; a real table reads in key order, and
# `PARENT#`/`STUDENT#` sort before `USER#`.
SCANS_TO_REACH_THE_PROFILES = 7


def test_一页两百个家长账号要打三千两百次数据库(table: CountingTable) -> None:
    """The measured cost of the largest page this route accepts.

    Seven scans + one link query per row + five reads per link: the two link rows,
    the two profiles the relationship judge checks, and the counterpart profile read
    a second time for its account number. The parent's own profile is read once per
    child although the scan already returned it. 200 parents x 3 links x 5 = 3000.
    """
    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == PARENTS
    assert dict(table.calls) == {
        "scan": SCANS_TO_REACH_THE_PROFILES,
        "query": PARENTS,
        "get_item": 3000,
    }
    assert sum(table.calls.values()) == 3207


def test_不取关联时同一页只剩扫描(
    table: CountingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the count above is the link resolution, not the harness.

    Without it the same page is the walk to the profiles and nothing else, which is
    also what the numbers above have to beat if this route is ever made to batch its
    reads.
    """
    monkeypatch.setattr(admin, "_linked_counterparts", lambda profile: [])

    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == PARENTS
    assert dict(table.calls) == {"scan": SCANS_TO_REACH_THE_PROFILES}


def test_默认页大小的代价是满页的四分之一(table: CountingTable) -> None:
    """The default page is what production actually serves, so hold it separately.

    The scan count does not fall with the page size: the walk to the first profile
    costs the same whether 50 or 200 of them are wanted.
    """
    response = _client().get("/admin/users")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 50
    assert dict(table.calls) == {
        "scan": SCANS_TO_REACH_THE_PROFILES,
        "query": 50,
        "get_item": 750,
    }


def _seed_noise_first(table: CountingTable, *, noise_rows: int) -> None:
    """The production layout: curriculum and practice rows before any profile.

    `stoa-main` holds one row per lesson, challenge and attempt against a few
    dozen accounts, so the profiles sit far behind rows this route filters out.
    """
    for index in range(noise_rows):
        table.seed({
            "PK": "PRACTICE",
            "SK": f"CHALLENGE#lesson-{index}",
            "entity_type": "challenge",
        })
    for index in range(4):
        user_id = f"student-{index}"
        table.seed({
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "email": f"{user_id}@stoa.test",
            "name": user_id,
            "account_number": f"S26-{index:04d}",
            "created_at": "2026-01-01T00:00:00+00:00",
        })


def test_账号藏在扫描页之后也照样答200(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route over a table whose other rows fill the first scan pages.

    What the page holds and where the next one starts is pinned at the repository
    (tests/test_user_repo_account_list.py); here only that the route answers.
    """
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=500)
    for module in (parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)
    db_table.install(counting)

    assert _client().get("/admin/users").status_code == 200


def test_读不懂的游标答422(table: CountingTable) -> None:
    assert _client().get("/admin/users?cursor=not-a-cursor").status_code == 422


def test_平台统计要读完整张表(monkeypatch: pytest.MonkeyPatch) -> None:
    """`/admin/stats` counted from one scan, which on any real table is a sample.

    `stoa-main` passed a megabyte long ago, so the dashboard was reporting a
    fraction of its accounts as the total and saying nothing about it.
    """
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=500)
    for module in (parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)
    db_table.install(counting)

    response = _client().get("/admin/stats")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_users"] == 4
    assert body["total_students"] == 4
    assert body["counts_complete"] is True


def test_统计走不完时说明数字是下限(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: a census cut short must not pass itself off as a total.

    `/admin/stats` sends no `Limit`, so what ends its pages is the response cap, not
    a row count. The cap is shrunk here for the same reason the budget exists: 50
    real pages is 50 MB of rows, which is not a fixture. The old double invented a
    `Limit` of 50 when none was sent, which is a row count no real scan applies.
    """
    counting = CountingTable(page_size_bytes=512)
    _seed_noise_first(counting, noise_rows=800)
    for module in (parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)
    db_table.install(counting)

    response = _client().get("/admin/stats")

    assert response.status_code == 200, response.text
    assert response.json()["counts_complete"] is False
