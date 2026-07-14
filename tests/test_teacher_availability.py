from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_actor, get_current_user
from stoa.routers import conversations, teachers
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import teacher_dispatch_service


def _client(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: user
    role = CanonicalRole(user["role"])
    app.dependency_overrides[get_actor] = lambda: Actor(
        user["sub"], "https://identity.test", f"{user['sub']}-subject", role,
        AccountStatus.ACTIVE, role.value,
    )
    return TestClient(app)


def test_teacher_help_availability_reports_online_teacher_to_student(monkeypatch):
    monkeypatch.setattr(
        conversations.teacher_dispatch_service,
        "teacher_availability_summary",
        lambda: {
            "online": True,
            "availableTeachers": 1,
            "responseTime": "Teacher support is available now.",
        },
    )

    response = _client(
        conversations.teacher_help_router,
        "/teacher-help",
        {"sub": "student-1", "role": "student"},
    ).get("/teacher-help/availability")

    assert response.status_code == 200
    assert response.json() == {
        "online": True,
        "availableTeachers": 1,
        "nextWindow": None,
        "responseTime": "Teacher support is available now.",
    }


def test_teacher_availability_summary_counts_dispatchable_profiles_only():
    summary = teacher_dispatch_service.teacher_availability_summary(
        [
            {
                "user_id": "teacher-online",
                "role": "teacher",
                "subjects": ["math"],
                "dispatch_availability": "online",
                "active_session_count": 0,
                "max_active_sessions": 2,
            },
            {
                "user_id": "teacher-busy",
                "role": "teacher",
                "subjects": ["math"],
                "dispatch_availability": "available",
                "active_session_count": 2,
                "max_active_sessions": 2,
            },
            {
                "user_id": "teacher-no-subjects",
                "role": "teacher",
                "dispatch_availability": "available",
            },
        ]
    )

    assert summary["online"] is True
    assert summary["availableTeachers"] == 1


def test_teacher_availability_get_and_patch_persist_profile_fields(monkeypatch):
    updates = []

    monkeypatch.setattr(
        teachers.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "teacher",
            "subjects": ["Mathematics"],
            "weekly_availability": [
                {"dayOfWeek": "monday", "startTime": "16:00", "endTime": "18:00"}
            ],
        },
    )
    monkeypatch.setattr(teachers, "_now", lambda: "2026-07-09T12:00:00+00:00")

    def update_availability(user_id, *, subjects, weekly_availability, updated_at):
        updates.append(
            {
                "user_id": user_id,
                "subjects": subjects,
                "weekly_availability": weekly_availability,
                "updated_at": updated_at,
            }
        )
        return {
            "user_id": user_id,
            "role": "teacher",
            "subjects": subjects,
            "weekly_availability": weekly_availability,
            "dispatch_availability": "available",
        }

    monkeypatch.setattr(teachers.user_repo, "update_teacher_availability", update_availability)
    client = _client(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})

    get_response = client.get("/teachers/me/availability")
    assert get_response.status_code == 200
    assert get_response.json()["subjects"] == ["Mathematics"]

    patch_response = client.patch(
        "/teachers/me/availability",
        json={
            "subjects": ["Physics"],
            "weeklyAvailability": [
                {"dayOfWeek": "tuesday", "startTime": "17:00", "endTime": "19:00"}
            ],
        },
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["subjects"] == ["Physics"]
    assert updates == [
        {
            "user_id": "teacher-1",
            "subjects": ["Physics"],
            "weekly_availability": [
                {"dayOfWeek": "tuesday", "startTime": "17:00", "endTime": "19:00"}
            ],
            "updated_at": "2026-07-09T12:00:00+00:00",
        }
    ]


def test_teacher_router_exposes_no_legacy_route():
    client = _client(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})

    assert all(not route.path.startswith("/tutors") for route in client.app.routes)
    assert client.get("/tutors/me/availability").status_code == 404
