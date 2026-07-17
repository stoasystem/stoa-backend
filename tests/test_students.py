from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import students
from stoa.security import route_authorization
from stoa.security.identity import AccountStatus, Actor, CanonicalRole, CapabilityGrant
from audit_helpers import MemoryAuthorizationAuditSink


def _actor(role, user_id, grants=()):
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        tuple(grants),
    )


def _client(actor):
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _profiles(monkeypatch):
    profiles = {
        "student-1": {
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "name": "Student One",
            "grade": "Sek1",
            "primary_subjects": ["math"],
            "created_at": "2026-07-15T00:00:00Z",
            "updated_at": "2026-07-15T00:00:00Z",
        },
        "student-2": {
            "user_id": "student-2",
            "role": "student",
            "account_status": "active",
        },
        "parent-1": {
            "user_id": "parent-1",
            "role": "parent",
            "account_status": "active",
        },
        "teacher-1": {
            "user_id": "teacher-1",
            "role": "teacher",
            "account_status": "active",
        },
    }
    monkeypatch.setattr(
        route_authorization.user_repo, "get_user", lambda user_id: profiles.get(user_id)
    )
    monkeypatch.setattr(
        students.question_repo, "list_by_student", lambda *_args, **_kwargs: {"Items": []}
    )
    return profiles


def test_student_profile_uses_canonical_actor_user_id_without_email_fallback(monkeypatch):
    _profiles(monkeypatch)
    response = _client(_actor(CanonicalRole.STUDENT, "student-1")).get(
        "/students/me/profile"
    )
    assert response.status_code == 200
    assert response.json()["userId"] == "student-1"


def test_sec_002_other_student_and_unrelated_parent_are_hidden(monkeypatch):
    _profiles(monkeypatch)
    monkeypatch.setattr(route_authorization.user_repo, "get_parent_student_binding", lambda *_: None)
    monkeypatch.setattr(route_authorization.user_repo, "get_student_parent_binding", lambda *_: None)
    other = _client(_actor(CanonicalRole.STUDENT, "student-2")).get(
        "/students/student-1/summary"
    )
    parent = _client(_actor(CanonicalRole.PARENT, "parent-1")).get(
        "/students/student-1/summary"
    )
    assert other.status_code == parent.status_code == 404
    assert other.json()["detail"]["code"] == parent.json()["detail"]["code"] == "resource_not_found"


def test_active_bidirectional_parent_can_read_summary(monkeypatch):
    _profiles(monkeypatch)
    row = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "version": 2,
        "status": "active",
    }
    monkeypatch.setattr(route_authorization.user_repo, "get_parent_student_binding", lambda *_: row)
    monkeypatch.setattr(route_authorization.user_repo, "get_student_parent_binding", lambda *_: dict(row))
    response = _client(_actor(CanonicalRole.PARENT, "parent-1")).get(
        "/students/student-1/summary"
    )
    assert response.status_code == 200
    assert response.json()["student_id"] == "student-1"


def test_scoped_teacher_and_exact_admin_content_capability_positive_controls(monkeypatch):
    _profiles(monkeypatch)
    monkeypatch.setattr(students.question_repo, "get_question", lambda *_: None)
    monkeypatch.setattr(students.question_repo, "get_teacher_session", lambda *_: None)
    monkeypatch.setattr(
        students.question_repo,
        "get_teacher_assignment",
        lambda *_: {
            "teacher_id": "teacher-1",
            "student_id": "student-1",
            "status": "active",
            "scope": "student:student-1",
        },
    )
    teacher = _client(_actor(CanonicalRole.TEACHER, "teacher-1")).get(
        "/students/student-1/questions"
    )
    grant = CapabilityGrant("student_content_review", "student:student-1", 1)
    admin = _client(_actor(CanonicalRole.ADMIN, "admin-1", (grant,))).get(
        "/students/student-1/summary"
    )
    assert teacher.status_code == admin.status_code == 200


def test_admin_role_only_is_known_403_and_outage_precedes_profile_mutation(monkeypatch):
    _profiles(monkeypatch)
    denied = _client(_actor(CanonicalRole.ADMIN, "admin-1")).get(
        "/students/student-1/summary"
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "action_not_allowed"

    writes = []
    monkeypatch.setattr(
        route_authorization.user_repo,
        "get_user",
        lambda _user_id: (_ for _ in ()).throw(TimeoutError("store canary")),
    )
    monkeypatch.setattr(
        students.user_repo,
        "update_profile_fields",
        lambda *_args, **_kwargs: writes.append("profile"),
    )
    outage = _client(_actor(CanonicalRole.STUDENT, "student-1")).patch(
        "/students/me/profile", json={"grade": "Sek2"}
    )
    assert outage.status_code == 503
    assert outage.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert writes == []
