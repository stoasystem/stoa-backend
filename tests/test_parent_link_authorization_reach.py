"""Card 002-D / audit A3: a many-to-many link must be visible to every parent route.

The first version of the link table was only consulted by a wrapper living inside
`routers/parents.py`, so a link created purely through the new admin endpoint was
invisible to the ~40 other routes that authorize a parent.  These tests therefore
never touch `/parents`: they drive one route per authorization dependency factory,
with the production fact repository wired in and no local wrapper anywhere.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db import table as db_table
from stoa.routers.conversations import ConversationListPage
from stoa.db.repositories import parent_link_repo, question_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import adaptive, students
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import parent_link_service

from test_parent_student_links import FakeLinkTable


NOW = "2026-09-19T10:00:00+00:00"

PARENT = "parent-a"
STUDENT = "student-b"
STRANGER = "student-c"


def _profile(user_id: str, role: str, status: str = "active") -> dict[str, Any]:
    return {
        "user_id": user_id,
        "role": role,
        "account_status": status,
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        # Card 008: an account with no birthday reads as a minor and is refused
        # the self-service path, which is not what these routes are probing.
        "date_of_birth": "2000-01-01",
    }


@pytest.fixture
def accounts() -> dict[str, dict[str, Any]]:
    return {
        PARENT: _profile(PARENT, "parent"),
        STUDENT: _profile(STUDENT, "student"),
        STRANGER: _profile(STRANGER, "student"),
    }


@pytest.fixture
def table(
    monkeypatch: pytest.MonkeyPatch, accounts: dict[str, dict[str, Any]]
) -> FakeLinkTable:
    """Link table only: the relationship judge reads nothing else."""
    fake = FakeLinkTable()
    for user_id in accounts:
        fake.seed_account_fence(user_id)
    db_table.install(fake)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(accounts.get(user_id)))
    monkeypatch.setattr(question_repo, "list_by_student", lambda *_a, **_k: {"Items": []})
    # The student summary also counts resolved chat help requests (#77).
    monkeypatch.setattr(
        "stoa.routers.conversations._list_conversations",
        lambda *_a, **_k: ConversationListPage([], False),
    )
    monkeypatch.setattr(
        adaptive.adaptive_learning_service,
        "parent_progress_signal",
        lambda student_id, _user: {"studentId": student_id, "weakAreas": []},
    )
    return fake


def _client(parent_id: str = PARENT) -> TestClient:
    """Every router of interest, with the production fact repository left in place."""
    actor = Actor(
        parent_id,
        "https://identity.test",
        f"{parent_id}-subject",
        CanonicalRole.PARENT,
        AccountStatus.ACTIVE,
        "parent",
    )
    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


# The routes below each come from a different authorization dependency
# factory, which is what A3 was actually about: the old patch covered one router.
# The question read route was the third until #148 retired it.
ADAPTIVE_PROGRESS = f"/adaptive/parents/me/children/{STUDENT}/progress"
STUDENT_SUMMARY = f"/students/{STUDENT}/summary"

CROSS_ROUTER_ROUTES = (
    pytest.param(ADAPTIVE_PROGRESS, id="adaptive-parent-progress"),
    pytest.param(STUDENT_SUMMARY, id="students-summary"),
)


def _assign(table: FakeLinkTable) -> None:
    """Exactly what POST /admin/users/parent-links does, and nothing else."""
    parent_link_service.assign_link(
        parent_id=PARENT, student_id=STUDENT, actor_id="admin-1", now=NOW
    )


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_admin_assigned_link_alone_grants_every_parent_route(
    table: FakeLinkTable, path: str
) -> None:
    assert not [key for key in table.items if key[1] != "ACCOUNT_FENCE"]
    _assign(table)

    response = _client().get(path)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_without_any_link_the_same_routes_hide_the_student(
    table: FakeLinkTable, path: str
) -> None:
    """Negative control for the positive case above: no link, no reach."""
    response = _client().get(path)

    assert response.status_code == 404, response.text


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_rejected_link_never_reaches_any_parent_route(
    table: FakeLinkTable, path: str
) -> None:
    parent_link_service.request_link(
        requester_id=STUDENT, counterpart_id=PARENT, now=NOW
    )
    parent_link_service.reject_link(
        parent_id=PARENT, student_id=STUDENT, actor_id=PARENT, now=NOW
    )

    response = _client().get(path)

    assert response.status_code in {403, 404}, response.text


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_pending_link_never_reaches_any_parent_route(
    table: FakeLinkTable, path: str
) -> None:
    parent_link_service.request_link(
        requester_id=PARENT, counterpart_id=STUDENT, now=NOW
    )

    response = _client().get(path)

    assert response.status_code in {403, 404}, response.text


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_archived_student_revokes_an_active_link(
    table: FakeLinkTable, accounts: dict[str, dict[str, Any]], path: str
) -> None:
    _assign(table)
    assert _client().get(path).status_code == 200

    accounts[STUDENT]["account_status"] = "archived"

    response = _client().get(path)

    assert response.status_code in {403, 404}, response.text


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_archived_parent_revokes_an_active_link(
    table: FakeLinkTable, accounts: dict[str, dict[str, Any]], path: str
) -> None:
    _assign(table)
    assert _client().get(path).status_code == 200

    accounts[PARENT]["account_status"] = "archived"

    response = _client().get(path)

    assert response.status_code in {403, 404}, response.text


def test_half_a_link_grants_nothing_on_a_non_parents_route(table: FakeLinkTable) -> None:
    """Both stored directions must be active; one surviving row is not a grant."""
    _assign(table)
    del table.items[(f"STUDENT#{STUDENT}", f"PARENT#{PARENT}")]

    assert _client().get(ADAPTIVE_PROGRESS).status_code != 200


def test_a_second_parent_reaches_the_same_child(
    table: FakeLinkTable, accounts: dict[str, dict[str, Any]]
) -> None:
    """The legacy binding holds one parent per student; this is why A3 mattered."""
    accounts["parent-b"] = _profile("parent-b", "parent")
    table.seed_account_fence("parent-b")
    _assign(table)
    parent_link_service.assign_link(
        parent_id="parent-b", student_id=STUDENT, actor_id="admin-1", now=NOW
    )

    assert _client(PARENT).get(ADAPTIVE_PROGRESS).status_code == 200
    assert _client("parent-b").get(ADAPTIVE_PROGRESS).status_code == 200


def test_链接表读不出来时不会被当成没有链接(monkeypatch: pytest.MonkeyPatch) -> None:
    """裁判读不出链接行时抛错，而不是答「不认识这一对」。

    旧的兜底在旧绑定没匹配上之后才走到，所以吞掉错误等于拒绝；现在链接表是
    唯一的来源，把读不出来报成「没有链接」会把故障伪装成事实，
    所以这里必须让错误冒出来，由路由授权把它变成 503（见下一条）。
    """
    from stoa.services import current_relationship

    def 炸(*_args, **_kwargs):
        raise RuntimeError("parent link table is unreachable")

    monkeypatch.setattr(parent_link_repo, "get_parent_side_link", 炸)

    with pytest.raises(RuntimeError):
        current_relationship.judge("parent-a", "student-b")


@pytest.mark.parametrize("path", CROSS_ROUTER_ROUTES)
def test_链接表连不上时受影响的路由回503而不是500(
    table: FakeLinkTable, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """CI 里这些路由曾因新表读不出来而出错，本地有凭据所以没复现。

    桩打在表网关的取表点 `db_table.table` 上 —— 链接表和其余各表都从那里取（#327）。
    读不出来是授权暂时不可用：既不放行，也不是 500。
    """
    from stoa.services import current_relationship

    _assign(table)

    def 炸():
        raise RuntimeError("no credentials for the parent link table")

    monkeypatch.setattr(db_table, "table", 炸)

    response = _client().get(path)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"

    with pytest.raises(RuntimeError):
        current_relationship.children_of("parent-a")


def test_传进来的表才是它读的那张表(monkeypatch):
    """The injection has to be used, not merely accepted.

    `parent_link_repo` once bound `get_table` at module level, so a stub
    installed anywhere else could not reach it. That is how `pytest` came to
    send reads to the live table: nothing a test did could stop this function,
    and the only fix available was a fixture that replaced the binding by name.
    A table passed in is now the table every read here uses, and the ambient
    one - the gateway's, since #327 - is not touched at all.
    """
    from stoa.db.dynamodb import get_table as ambient_get_table
    from stoa.services import current_relationship

    reads: list[tuple[str, str]] = []
    rows = {
        ("PARENT#p1", "CHILD#s1"): {
            "PK": "PARENT#p1", "SK": "CHILD#s1", "parent_id": "p1",
            "student_id": "s1", "status": "active", "relationship": "child",
            "link_updated_at": "2026-09-19T10:00:00+00:00",
        },
        ("STUDENT#s1", "PARENT#p1"): {
            "PK": "STUDENT#s1", "SK": "PARENT#p1", "parent_id": "p1",
            "student_id": "s1", "status": "active", "relationship": "child",
            "link_updated_at": "2026-09-19T10:00:00+00:00",
        },
        ("USER#p1", "PROFILE"): {
            "user_id": "p1", "role": "parent", "account_status": "active",
        },
        ("USER#s1", "PROFILE"): {
            "user_id": "s1", "role": "student", "account_status": "active",
        },
    }

    class _Injected:
        def get_item(self, *, Key, **_kwargs):
            reads.append((Key["PK"], Key["SK"]))
            row = rows.get((Key["PK"], Key["SK"]))
            return {"Item": dict(row)} if row else {}

    def _refuse(*_args, **_kwargs):
        raise AssertionError("the ambient table was reached")

    monkeypatch.setattr(db_table, "table", _refuse)

    verdict = current_relationship.judge("p1", "s1", table=_Injected())

    assert verdict.is_current
    assert ("USER#p1", "PROFILE") in reads and ("USER#s1", "PROFILE") in reads
    assert ("PARENT#p1", "CHILD#s1") in reads
    assert callable(ambient_get_table)
