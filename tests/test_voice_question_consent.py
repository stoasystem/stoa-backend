"""#476: a child's "voice questions allowed" switch, set by a linked parent.

Off by default. Any parent currently in a relationship with the child may read
and change it, the last change wins, and every change is recorded (who, when,
the new value) as the consent. The student reads their own state; with no
linked parent it is off.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import transaction_canceled
from stoa.db import table as db_table
from stoa.db.repositories import user_repo, voice_question_consent_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import parents, students
from stoa.security.authorization import CurrentAuthorizationFactRepository
from stoa.security.declared_authorization import get_authorization_fact_repository
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import current_relationship, parent_link_service, voice_questions

from test_parent_student_links import FakeLinkTable


NOW = "2026-11-16T10:00:00+00:00"
CHILD = "student-b"
PATH = f"/parents/me/children/{CHILD}/voice-questions"
STUDENT_PATH = "/students/me/voice-questions"


def _profile(user_id: str, role: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        "date_of_birth": "2000-01-01",
    }


ACCOUNTS = {
    "parent-a": _profile("parent-a", "parent"),
    "parent-b": _profile("parent-b", "parent"),
    "parent-x": _profile("parent-x", "parent"),
    CHILD: _profile(CHILD, "student"),
    "student-c": _profile("student-c", "student"),
    "teacher-1": _profile("teacher-1", "teacher"),
    "admin-1": _profile("admin-1", "admin"),
}


class ConsentTable(FakeLinkTable):
    """The link table, also holding a link check to the stamp it names.

    The base double only asks that a checked row exist; a change made on a
    relationship that was closed in between has to be refused by its stamp.
    """

    def _check_condition(self, check, staged) -> None:
        super()._check_condition(check, staged)
        values = check.get("ExpressionAttributeValues") or {}
        if ":expected_link_updated_at" in values:
            item = staged[(check["Key"]["PK"], check["Key"]["SK"])]
            if (
                item.get("status") != values[":expected_status"]
                or item.get("link_updated_at") != values[":expected_link_updated_at"]
            ):
                raise transaction_canceled([])


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> ConsentTable:
    fake = ConsentTable()
    for user_id in ACCOUNTS:
        fake.seed_account_fence(user_id)
    db_table.install(fake)
    monkeypatch.setattr(
        user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(ACCOUNTS.get(user_id))
    )
    return fake


def _link(parent_id: str, student_id: str = CHILD) -> None:
    parent_link_service.assign_link(
        parent_id=parent_id, student_id=student_id, actor_id="admin-1", now=NOW
    )


def _client(user_id: str, role: CanonicalRole) -> TestClient:
    actor = Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = (
        CurrentAuthorizationFactRepository
    )
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _parent(user_id: str = "parent-a") -> TestClient:
    return _client(user_id, CanonicalRole.PARENT)


def _student(user_id: str = CHILD) -> TestClient:
    return _client(user_id, CanonicalRole.STUDENT)


def _changes(table: ConsentTable, student_id: str = CHILD) -> list[dict[str, Any]]:
    return [
        item
        for (pk, sk), item in sorted(table.items.items())
        if pk == f"STUDENT#{student_id}"
        and sk.startswith(voice_question_consent_repo.CHANGE_SK_PREFIX)
    ]


# --- A linked parent -------------------------------------------------------------


def test_a_linked_parent_reads_off_before_anyone_changed_it(table: ConsentTable) -> None:
    _link("parent-a")

    response = _parent().get(PATH)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "studentId": CHILD,
        "allowed": False,
        "changedAt": None,
        "changedByMe": None,
    }


def test_a_linked_parent_turns_it_on_and_reads_it_back(table: ConsentTable) -> None:
    _link("parent-a")
    client = _parent()

    written = client.put(PATH, json={"allowed": True})
    read = client.get(PATH)

    assert written.status_code == 200, written.text
    assert written.json()["allowed"] is True
    assert written.json()["changedByMe"] is True
    assert written.json()["changedAt"]
    assert read.json() == written.json()


def test_either_parent_may_change_it_and_the_last_change_wins(table: ConsentTable) -> None:
    _link("parent-a")
    _link("parent-b")

    assert _parent("parent-a").put(PATH, json={"allowed": True}).status_code == 200
    assert _parent("parent-b").put(PATH, json={"allowed": False}).status_code == 200

    seen_by_a = _parent("parent-a").get(PATH).json()
    seen_by_b = _parent("parent-b").get(PATH).json()
    assert seen_by_a["allowed"] is False
    assert seen_by_a["changedByMe"] is False
    assert seen_by_b["allowed"] is False
    assert seen_by_b["changedByMe"] is True
    assert seen_by_a["changedAt"] == seen_by_b["changedAt"]


def test_the_body_takes_only_a_boolean(table: ConsentTable) -> None:
    _link("parent-a")
    client = _parent()

    for body in ({"allowed": "yes"}, {"allowed": 1}, {}, {"allowed": True, "extra": 1}):
        assert client.put(PATH, json=body).status_code == 422, body
    assert _changes(table) == []


# --- The consent record ----------------------------------------------------------


def test_every_change_is_recorded_with_who_when_and_the_new_value(table: ConsentTable) -> None:
    _link("parent-a")
    _link("parent-b")
    relationship_a = current_relationship.judge("parent-a", CHILD)
    relationship_b = current_relationship.judge("parent-b", CHILD)

    voice_questions.set_by_parent(relationship_a, True, now="2026-11-16T10:00:00+00:00")
    voice_questions.set_by_parent(relationship_b, False, now="2026-11-16T11:00:00+00:00")
    voice_questions.set_by_parent(relationship_a, True, now="2026-11-16T12:00:00+00:00")

    changes = voice_question_consent_repo.list_changes(CHILD)
    assert [(c["changed_by"], c["changed_at"], c["allowed"]) for c in changes] == [
        ("parent-a", "2026-11-16T10:00:00+00:00", True),
        ("parent-b", "2026-11-16T11:00:00+00:00", False),
        ("parent-a", "2026-11-16T12:00:00+00:00", True),
    ]
    assert all(c["student_id"] == CHILD for c in changes)
    # Nothing on these rows may pull them into the index of a student's questions.
    assert all("created_at" not in c for c in changes)

    state = voice_questions.for_parent(CHILD)
    assert (state.allowed, state.changed_by, state.changed_at) == (
        True,
        "parent-a",
        "2026-11-16T12:00:00+00:00",
    )


def test_a_change_through_the_route_is_recorded(table: ConsentTable) -> None:
    _link("parent-a")

    _parent().put(PATH, json={"allowed": True})

    [change] = _changes(table)
    assert change["changed_by"] == "parent-a"
    assert change["allowed"] is True
    assert change["changed_at"]


def test_a_relationship_closed_after_authorization_refuses_the_change(
    table: ConsentTable,
) -> None:
    _link("parent-a")
    authorized_on = current_relationship.judge("parent-a", CHILD)
    current_relationship.revoke("parent-a", CHILD, actor_id="admin-1")

    with pytest.raises(voice_questions.RelationshipNotCurrent):
        voice_questions.set_by_parent(authorized_on, True)

    assert _changes(table) == []
    assert voice_question_consent_repo.get_state(CHILD) is None


def test_a_parent_whose_account_is_being_deleted_cannot_change_it(
    table: ConsentTable,
) -> None:
    _link("parent-a")
    relationship = current_relationship.judge("parent-a", CHILD)
    table.seed_account_fence("parent-a", status="deleting")

    with pytest.raises(voice_questions.RelationshipNotCurrent):
        voice_questions.set_by_parent(relationship, True)

    assert _changes(table) == []


# --- Refused: unlinked parents and every other role --------------------------------


def test_an_unlinked_parent_can_neither_read_nor_change_it(table: ConsentTable) -> None:
    _link("parent-a")
    stranger = _parent("parent-x")

    read = stranger.get(PATH)
    written = stranger.put(PATH, json={"allowed": True})

    assert read.status_code in {403, 404}
    assert written.status_code in {403, 404}
    assert _changes(table) == []


def test_a_parent_whose_link_was_revoked_is_refused(table: ConsentTable) -> None:
    _link("parent-a")
    _parent().put(PATH, json={"allowed": True})
    current_relationship.revoke("parent-a", CHILD, actor_id="admin-1")

    assert _parent().get(PATH).status_code == 403
    assert _parent().put(PATH, json={"allowed": False}).status_code == 403
    assert len(_changes(table)) == 1


def test_a_pending_link_grants_nothing(table: ConsentTable) -> None:
    parent_link_service.request_link(requester_id="parent-a", counterpart_id=CHILD, now=NOW)

    assert _parent().get(PATH).status_code == 403
    assert _parent().put(PATH, json={"allowed": True}).status_code == 403
    assert _changes(table) == []


@pytest.mark.parametrize(
    ("user_id", "role"),
    [
        (CHILD, CanonicalRole.STUDENT),
        ("student-c", CanonicalRole.STUDENT),
        ("teacher-1", CanonicalRole.TEACHER),
        ("admin-1", CanonicalRole.ADMIN),
    ],
)
def test_other_roles_cannot_use_the_parent_routes(
    table: ConsentTable, user_id: str, role: CanonicalRole
) -> None:
    _link("parent-a")
    client = _client(user_id, role)

    assert client.get(PATH).status_code in {403, 404}
    assert client.put(PATH, json={"allowed": True}).status_code in {403, 404}
    assert _changes(table) == []


# --- The student's own read --------------------------------------------------------


def test_a_student_reads_off_until_a_parent_allows_it(table: ConsentTable) -> None:
    _link("parent-a")

    assert _student().get(STUDENT_PATH).json() == {"allowed": False}
    _parent().put(PATH, json={"allowed": True})
    assert _student().get(STUDENT_PATH).json() == {"allowed": True}
    _parent().put(PATH, json={"allowed": False})
    assert _student().get(STUDENT_PATH).json() == {"allowed": False}


def test_a_student_with_no_linked_parent_reads_off(table: ConsentTable) -> None:
    response = _student("student-c").get(STUDENT_PATH)

    assert response.status_code == 200, response.text
    assert response.json() == {"allowed": False}


def test_a_switch_left_on_reads_off_once_no_parent_is_linked(table: ConsentTable) -> None:
    _link("parent-a")
    _parent().put(PATH, json={"allowed": True})
    current_relationship.revoke("parent-a", CHILD, actor_id="admin-1")

    assert _student().get(STUDENT_PATH).json() == {"allowed": False}


def test_a_student_reads_only_their_own_switch(table: ConsentTable) -> None:
    _link("parent-a")
    _link("parent-a", "student-c")
    _parent().put(PATH, json={"allowed": True})

    assert _student("student-c").get(STUDENT_PATH).json() == {"allowed": False}
    assert _student(CHILD).get(STUDENT_PATH).json() == {"allowed": True}


@pytest.mark.parametrize(
    ("user_id", "role"),
    [("parent-a", CanonicalRole.PARENT), ("teacher-1", CanonicalRole.TEACHER)],
)
def test_other_roles_cannot_use_the_student_read(
    table: ConsentTable, user_id: str, role: CanonicalRole
) -> None:
    _link("parent-a")

    assert _client(user_id, role).get(STUDENT_PATH).status_code in {403, 404}
