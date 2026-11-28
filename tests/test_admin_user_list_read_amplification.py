"""Card 002 #7: what one page of GET /admin/users costs in DynamoDB round trips.

The endpoint used to answer from a table scan and then resolve every listed
account's parent/child links one account at a time, five reads per link, so its
cost was the page size times the links behind it: 3207 round trips for a full
page, against the 29 seconds API Gateway allows. Card 133 cut that on purpose:
the accounts are now one query of GSI-Listing, and the links one link query per
account plus one batched read (`BatchGetItem`, a hundred keys a call) of every
link row and profile the relationship judge needs. A full page is now 221.

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
from stoa.db.repositories import account_deletion_repo, parent_link_repo
from stoa.routers import admin
from stoa.services import account_listing

PARENTS = 200
CHILDREN_PER_PARENT = 3


CountingTable = FakeTable
"""The shared double counts its own round trips, which is all this file needed.

What it does *not* do is hand back rows in the order they were planted. A real
index reads in key order: newest `listed_at` first here, so the fixture dates
the parents after the students to put the parents on the first page.
"""


def _profile(row: dict[str, object]) -> dict[str, object]:
    return {**row, **account_deletion_repo.account_listing_fields(row)}


def _seed(table: CountingTable) -> None:
    """Parent profiles first, so a full page is parents and nothing else.

    That is the expensive shape and therefore the one worth holding. A parent row
    and a student row cost the same: a link query, and every pair's two link rows
    and two profiles go into the page's batched read, the counterpart's account
    number with them.
    """
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        table.seed(_profile({
            "PK": f"USER#{parent_id}",
            "SK": "PROFILE",
            "user_id": parent_id,
            "role": "parent",
            "account_status": "active",
            "email": f"{parent_id}@stoa.test",
            "name": parent_id,
            "account_number": f"P26-{index:04d}",
            "created_at": "2026-02-01T00:00:00+00:00",
        }))
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        for child in range(CHILDREN_PER_PARENT):
            student_id = f"student-{index}-{child}"
            table.seed(_profile({
                "PK": f"USER#{student_id}",
                "SK": "PROFILE",
                "user_id": student_id,
                "role": "student",
                "account_status": "active",
                "email": f"{student_id}@stoa.test",
                "name": student_id,
                "account_number": f"S26-{index:04d}{child}",
                "created_at": "2026-01-01T00:00:00+00:00",
            }))
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
    db_table.install(counting)
    return counting


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin", "accountStatus": "active"})
    return TestClient(app)


# One query of GSI-Listing reads a whole page of profiles, whatever else the
# table holds. It used to take seven scans to get past the link rows.
LISTING_QUERIES = 1


def test_一页两百个家长账号只打两百二十一次数据库(table: CountingTable) -> None:
    """The measured cost of the largest page this route accepts.

    One listing query + one link query per parent + the batched read: 200 parents
    x 3 links x 2 link rows, plus 800 profiles, is 2000 keys, 20 `BatchGetItem`
    calls. It was 3207 (7 scans + 200 queries + 3000 `GetItem`) before card 133.
    """
    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == PARENTS
    assert {item["role"] for item in body["items"]} == {"parent"}
    assert all(len(item["linkedAccounts"]) == CHILDREN_PER_PARENT for item in body["items"])
    assert body["items"][0]["linkedAccounts"][0]["accountNumber"].startswith("S26-")
    assert dict(table.calls) == {
        "query": LISTING_QUERIES + PARENTS,
        "batch_get_item": 20,
    }
    assert sum(table.calls.values()) == 221


def test_不取关联时同一页只剩一次索引查询(
    table: CountingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the count above is the link resolution, not the harness."""
    monkeypatch.setattr(
        account_listing, "_linked_counterparts", lambda profile, relationships: []
    )
    monkeypatch.setattr(
        account_listing.current_relationship,
        "current_relationships_of",
        lambda **kwargs: account_listing.current_relationship.CurrentRelationships({}, {}, {}),
    )

    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == PARENTS
    assert dict(table.calls) == {"query": LISTING_QUERIES}


def test_默认页大小的代价是满页的四分之一(table: CountingTable) -> None:
    """The default page is what production actually serves, so hold it separately.

    50 parents: 50 link queries, and 50 x 3 x 2 link rows + 200 profiles = 500 keys
    in 5 batches. It was 807 round trips before card 133.
    """
    response = _client().get("/admin/users")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 50
    assert dict(table.calls) == {
        "query": LISTING_QUERIES + 50,
        "batch_get_item": 5,
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
        table.seed(_profile({
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "email": f"{user_id}@stoa.test",
            "name": user_id,
            "account_number": f"S26-{index:04d}",
            "created_at": "2026-01-01T00:00:00+00:00",
        }))


def test_账号藏在扫描页之后也照样答200(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route over a table whose other rows fill the first scan pages.

    What the page holds and where the next one starts is pinned at the repository
    (tests/test_user_repo_account_list.py); here only that the route answers.
    """
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=500)
    db_table.install(counting)

    assert _client().get("/admin/users").status_code == 200


def test_读不懂的游标答422(table: CountingTable) -> None:
    assert _client().get("/admin/users?cursor=not-a-cursor").status_code == 422
