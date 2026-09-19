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
from stoa.db.repositories import parent_link_repo, question_repo, user_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import adaptive, questions, students
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import parent_link_service

from test_parent_student_links import FakeLinkTable


NOW = "2026-09-19T10:00:00+00:00"

PARENT = "parent-a"
STUDENT = "student-b"
STRANGER = "student-c"
QUESTION_ID = "question-1"
STRANGER_QUESTION_ID = "question-9"


def _profile(user_id: str, role: str, status: str = "active") -> dict[str, Any]:
    return {
        "user_id": user_id,
        "role": role,
        "account_status": status,
        "email": f"{user_id}@stoa.test",
        "name": user_id,
    }


QUESTIONS = {
    QUESTION_ID: {
        "question_id": QUESTION_ID,
        "student_id": STUDENT,
        "subject": "math",
        "content": "1 + 1",
        "status": "ai_answered",
        "created_at": NOW,
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "student_feedback": None,
        "resolved_at": None,
    },
    STRANGER_QUESTION_ID: {
        "question_id": STRANGER_QUESTION_ID,
        "student_id": STRANGER,
        "subject": "math",
        "content": "2 + 2",
        "status": "ai_answered",
        "created_at": NOW,
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "student_feedback": None,
        "resolved_at": None,
    },
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
    """Link table only: the legacy binding key space stays deliberately empty."""
    fake = FakeLinkTable()
    monkeypatch.setattr(parent_link_repo, "get_table", lambda: fake)
    monkeypatch.setattr(user_repo, "get_user", lambda user_id: deepcopy(accounts.get(user_id)))
    monkeypatch.setattr(
        user_repo, "get_parent_student_binding", lambda _parent_id, _student_id: None
    )
    monkeypatch.setattr(
        user_repo, "get_student_parent_binding", lambda _student_id, _parent_id: None
    )
    monkeypatch.setattr(question_repo, "list_by_student", lambda *_a, **_k: {"Items": []})
    monkeypatch.setattr(
        question_repo, "get_question", lambda question_id: deepcopy(QUESTIONS.get(question_id))
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
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


# The three routes below each come from a different authorization dependency
# factory, which is what A3 was actually about: the old patch covered one router.
ADAPTIVE_PROGRESS = f"/adaptive/parents/me/children/{STUDENT}/progress"
STUDENT_SUMMARY = f"/students/{STUDENT}/summary"
QUESTION_READ = f"/questions/{QUESTION_ID}"

CROSS_ROUTER_ROUTES = (
    pytest.param(ADAPTIVE_PROGRESS, id="adaptive-parent-progress"),
    pytest.param(STUDENT_SUMMARY, id="students-summary"),
    pytest.param(QUESTION_READ, id="questions-read"),
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
    assert not table.items
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


def test_a_link_to_one_child_does_not_reach_another_students_question(
    table: FakeLinkTable,
) -> None:
    """The question route derives the student from the resource, not from the path."""
    _assign(table)

    response = _client().get(f"/questions/{STRANGER_QUESTION_ID}")

    assert response.status_code == 404, response.text


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
    _assign(table)
    parent_link_service.assign_link(
        parent_id="parent-b", student_id=STUDENT, actor_id="admin-1", now=NOW
    )

    assert _client(PARENT).get(ADAPTIVE_PROGRESS).status_code == 200
    assert _client("parent-b").get(ADAPTIVE_PROGRESS).status_code == 200
