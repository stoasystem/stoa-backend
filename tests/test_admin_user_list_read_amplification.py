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

from collections import Counter
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides

from stoa.db.repositories import parent_link_repo, user_repo
from stoa.routers import admin

PARENTS = 200
CHILDREN_PER_PARENT = 3


class CountingTable:
    """Enough of a single table to serve this route, counting every round trip."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: Counter[str] = Counter()

    def get_item(self, *, Key: dict[str, str], ConsistentRead: bool = False) -> dict[str, Any]:  # noqa: N803
        del ConsistentRead
        self.calls["get_item"] += 1
        item = self.rows.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item is not None else {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["query"] += 1
        condition = kwargs["KeyConditionExpression"].get_expression()["values"]
        partition = condition[0].get_expression()["values"][1]
        prefix = condition[1].get_expression()["values"][1]
        return {
            "Items": [
                dict(row)
                for (pk, sk), row in self.rows.items()
                if pk == partition and sk.startswith(prefix)
            ]
        }

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["scan"] += 1
        limit = int(kwargs.get("Limit", 50))
        profiles = [dict(row) for (_, sk), row in self.rows.items() if sk == "PROFILE"]
        return {"Items": profiles[:limit]}


def _seed(table: CountingTable) -> None:
    """Parent profiles first, so a full page is parents and nothing else.

    That is the expensive shape and therefore the one worth holding: a parent row
    costs a link query plus a read per child, a student row costs a link query
    plus a read per parent.
    """
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        table.rows[(f"USER#{parent_id}", "PROFILE")] = {
            "PK": f"USER#{parent_id}",
            "SK": "PROFILE",
            "user_id": parent_id,
            "role": "parent",
            "account_status": "active",
            "email": f"{parent_id}@stoa.test",
            "name": parent_id,
            "account_number": f"P26-{index:04d}",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    for index in range(PARENTS):
        parent_id = f"parent-{index}"
        for child in range(CHILDREN_PER_PARENT):
            student_id = f"student-{index}-{child}"
            table.rows[(f"USER#{student_id}", "PROFILE")] = {
                "PK": f"USER#{student_id}",
                "SK": "PROFILE",
                "user_id": student_id,
                "role": "student",
                "account_status": "active",
                "email": f"{student_id}@stoa.test",
                "name": student_id,
                "account_number": f"S26-{index:04d}{child}",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
            link = {
                "entity_type": "parent_student_binding",
                "parent_id": parent_id,
                "student_id": student_id,
                "relationship": "parent",
                "status": parent_link_repo.STATUS_ACTIVE,
            }
            table.rows[(f"PARENT#{parent_id}", f"CHILD#{student_id}")] = {
                "PK": f"PARENT#{parent_id}",
                "SK": f"CHILD#{student_id}",
                **link,
            }
            table.rows[(f"STUDENT#{student_id}", f"PARENT#{parent_id}")] = {
                "PK": f"STUDENT#{student_id}",
                "SK": f"PARENT#{parent_id}",
                **link,
            }


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> CountingTable:
    counting = CountingTable()
    _seed(counting)
    for module in (admin, parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)
    return counting


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin", "accountStatus": "active"})
    return TestClient(app)


def test_一页两百个家长账号要打三千两百次数据库(table: CountingTable) -> None:
    """The measured cost of the largest page this route accepts.

    1 scan + one link query per row + five reads per link: the two link rows, the
    two profiles `active_link` checks, and the counterpart profile read a second
    time for its account number. The parent's own profile is read once per child
    although the scan already returned it.
    """
    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == PARENTS
    assert dict(table.calls) == {"scan": 1, "query": PARENTS, "get_item": 3000}
    assert sum(table.calls.values()) == 3201


def test_不取关联时同一页只要一次扫描(
    table: CountingTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the count above is the link resolution, not the harness.

    Without it the same page is one scan and nothing else, which is also what the
    numbers above have to beat if this route is ever made to batch its reads.
    """
    monkeypatch.setattr(admin, "_linked_counterparts", lambda profile: [])

    response = _client().get("/admin/users?limit=200")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == PARENTS
    assert dict(table.calls) == {"scan": 1}


def test_默认页大小的代价是满页的四分之一(table: CountingTable) -> None:
    """The default page is what production actually serves, so hold it separately."""
    response = _client().get("/admin/users")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 50
    assert dict(table.calls) == {"scan": 1, "query": 50, "get_item": 750}
