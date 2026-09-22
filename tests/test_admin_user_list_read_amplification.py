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
        """Scan the way the service does: `Limit` counts rows read, not rows kept.

        The double used to filter first and cut to `Limit` afterwards, which hands
        back a full page of profiles however the table is laid out. No real table
        behaves that way, and the difference is the whole bug this file failed to
        see: on a table where other rows outnumber profiles, a page can be spent
        entirely on rows the filter drops.
        """
        self.calls["scan"] += 1
        limit = int(kwargs.get("Limit", 50))
        keys = list(self.rows)
        start = 0
        resume = kwargs.get("ExclusiveStartKey")
        if resume:
            start = keys.index((resume["PK"], resume["SK"])) + 1
        window = keys[start : start + limit]
        items = [dict(self.rows[key]) for key in window if _filter_admits(self.rows[key], kwargs)]
        response: dict[str, Any] = {"Items": items}
        if start + limit < len(keys) and window:
            response["LastEvaluatedKey"] = {"PK": window[-1][0], "SK": window[-1][1]}
        return response


def _filter_admits(row: dict[str, Any], kwargs: dict[str, Any]) -> bool:
    """Evaluate the conjunction of `#name = :value` terms this route builds."""
    expression = kwargs.get("FilterExpression")
    if not expression:
        return True
    names = kwargs.get("ExpressionAttributeNames", {})
    values = kwargs.get("ExpressionAttributeValues", {})
    for term in str(expression).split(" AND "):
        left, right = (part.strip() for part in term.split("="))
        if row.get(names.get(left, left)) != values[right]:
            return False
    return True


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


def _seed_noise_first(table: CountingTable, *, noise_rows: int) -> None:
    """The production layout: curriculum and practice rows before any profile.

    `stoa-main` holds one row per lesson, challenge and attempt against a few
    dozen accounts, so the profiles sit far behind rows this route filters out.
    """
    for index in range(noise_rows):
        table.rows[("PRACTICE", f"CHALLENGE#lesson-{index}")] = {
            "PK": "PRACTICE",
            "SK": f"CHALLENGE#lesson-{index}",
            "entity_type": "challenge",
        }
    for index in range(4):
        user_id = f"student-{index}"
        table.rows[(f"USER#{user_id}", "PROFILE")] = {
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "email": f"{user_id}@stoa.test",
            "name": user_id,
            "account_number": f"S26-{index:04d}",
            "created_at": "2026-01-01T00:00:00+00:00",
        }


def test_账号藏在扫描页之后也要列出来(monkeypatch: pytest.MonkeyPatch) -> None:
    """The accounts console on a table whose other rows fill the first pages.

    One scan of 50 rows reads nothing but challenges and answers with an empty
    list and a continuation key, which is what production returned: the console
    showed no accounts at all, so an account just created looked like a button
    that had done nothing.
    """
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=500)
    for module in (admin, parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)

    response = _client().get("/admin/users")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["email"] for item in body["items"]] == [
        f"student-{index}@stoa.test" for index in range(4)
    ]
    assert body["count"] == 4
    assert body["groups"] == {"student": 4}
    assert body["nextCursor"] is None


def test_扫描额度用尽时说明还有下一页(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: the walk is bounded, and a bounded walk says so.

    A table deeper than the budget must not become an unbounded scan, and the
    caller has to be able to tell "no more accounts" from "stopped looking".
    """
    counting = CountingTable()
    _seed_noise_first(
        counting,
        noise_rows=admin.ADMIN_USER_SCAN_PAGE_SIZE * admin.ADMIN_USER_SCAN_MAX_PAGES + 10,
    )
    for module in (admin, parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)

    response = _client().get("/admin/users")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["nextCursor"] is not None
    assert counting.calls["scan"] == admin.ADMIN_USER_SCAN_MAX_PAGES


def test_平台统计要读完整张表(monkeypatch: pytest.MonkeyPatch) -> None:
    """`/admin/stats` counted from one scan, which on any real table is a sample.

    `stoa-main` passed a megabyte long ago, so the dashboard was reporting a
    fraction of its accounts as the total and saying nothing about it.
    """
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=500)
    for module in (admin, parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)

    response = _client().get("/admin/stats")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_users"] == 4
    assert body["total_students"] == 4
    assert body["counts_complete"] is True


def test_统计走不完时说明数字是下限(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: a census cut short must not pass itself off as a total."""
    counting = CountingTable()
    _seed_noise_first(counting, noise_rows=admin.ADMIN_STATS_MAX_PAGES * 200 + 10)
    for module in (admin, parent_link_repo, user_repo):
        monkeypatch.setattr(module, "get_table", lambda counting=counting: counting)

    response = _client().get("/admin/stats")

    assert response.status_code == 200, response.text
    assert response.json()["counts_complete"] is False
