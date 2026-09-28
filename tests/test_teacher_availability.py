import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import conversations, teachers
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import teacher_dispatch_service
from actor_helpers import install_actor_overrides


def _client(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
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
                "account_status": "active",
                "version": 1,
                "account_fence_generation": 1,
                "subjects": ["math"],
                "dispatch_availability": "online",
                "active_session_count": 0,
                "max_active_sessions": 2,
            },
            {
                "user_id": "teacher-busy",
                "role": "teacher",
                "account_status": "active",
                "version": 1,
                "account_fence_generation": 1,
                "subjects": ["math"],
                "dispatch_availability": "available",
                "active_session_count": 2,
                "max_active_sessions": 2,
            },
            {
                "user_id": "teacher-no-subjects",
                "role": "teacher",
                "account_status": "active",
                "version": 1,
                "account_fence_generation": 1,
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
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "teacher",
            "subjects": ["Mathematics"],
            "weekly_availability": [
                {"dayOfWeek": "monday", "startTime": "16:00", "endTime": "18:00"}
            ],
        },
    )
    monkeypatch.setattr(teachers, "_now", lambda: "2026-07-09T12:00:00+00:00")

    def update_availability(user_id, *, subjects, weekly_availability, updated_at, status):
        updates.append(
            {
                "user_id": user_id,
                "subjects": subjects,
                "weekly_availability": weekly_availability,
                "updated_at": updated_at,
                "status": status,
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
            "status": None,
        }
    ]


def test_teacher_router_exposes_no_legacy_route():
    client = _client(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})

    assert all(not route.path.startswith("/tutors") for route in client.app.routes)
    assert client.get("/tutors/me/availability").status_code == 404


def test_assistance_summary_requires_current_teacher_and_uses_authorized_question(monkeypatch):
    stored = []
    question = {
        "question_id": "question-1",
        "student_id": "student-1",
        "status": "teacher_active",
        "teacher_id": "teacher-1",
        "subject": "math",
        "content": "Explain fractions",
        "private_profile": "must-not-leak",
    }
    monkeypatch.setattr(teachers.question_repo, "get_question", lambda _id: question)
    monkeypatch.setattr(
        teachers.teacher_assistance_service.notification_repo,
        "put_summary_seed",
        lambda item: stored.append(item),
    )

    current = _client(
        teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}
    ).get("/teachers/questions/question-1/assistance-summary")
    other = _client(
        teachers.router, "/teachers", {"sub": "teacher-2", "role": "teacher"}
    ).get("/teachers/questions/question-1/assistance-summary")

    assert current.status_code == 200
    assert other.status_code == 404
    assert "must-not-leak" not in str(current.json())
    assert len(stored) == 1


def test_help_request_list_and_stats_include_only_current_assignment(monkeypatch):
    conversations = [
        {
            "conversation_id": "conv-mine",
            "student_id": "student-1",
            "escalated": True,
            "escalation_request_id": "help-mine",
            "escalation_status": "pending",
            "teacher_id": "teacher-1",
            "subject": "math",
            "escalated_at": "2026-07-15T08:00:00+00:00",
        },
        {
            "conversation_id": "conv-other",
            "student_id": "student-2",
            "escalated": True,
            "escalation_request_id": "help-other",
            "escalation_status": "pending",
            "teacher_id": "teacher-2",
            "subject": "physics",
            "escalated_at": "2026-07-15T09:00:00+00:00",
            "request_message": "private-other",
        },
    ]
    monkeypatch.setattr(teachers, "_get_escalated_conversations", lambda: conversations)
    monkeypatch.setattr(teachers, "_get_student_name", lambda _id: "Current Student")
    client = _client(
        teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}
    )

    listed = client.get("/teachers/me/help-requests")
    stats = client.get("/teachers/me/stats")

    assert listed.status_code == 200
    assert [item["requestId"] for item in listed.json()["items"]] == ["help-mine"]
    assert "private-other" not in str(listed.json())
    assert stats.status_code == 200
    assert stats.json()["pendingRequests"] == 1


def test_cross_teacher_help_request_update_is_hidden_before_mutation(monkeypatch):
    conv = {
        "PK": "CONV#conv-1",
        "SK": "CONV",
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "escalated": True,
        "escalation_request_id": "help-1",
        "teacher_id": "teacher-1",
        "escalation_status": "in_progress",
    }
    table = FakeTable()
    table.seed(conv)
    monkeypatch.setattr(teachers, "_get_conversation", lambda _id: dict(table.rows[("CONV#conv-1", "CONV")]))
    monkeypatch.setattr(teachers, "_get_student_name", lambda _id: "Student")
    for module in (teachers, teacher_dispatch_service, account_deletion_repo):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)

    other = _client(
        teachers.router, "/teachers", {"sub": "teacher-2", "role": "teacher"}
    ).patch("/teachers/me/help-requests/help-1", json={"status": "resolved"})

    assert other.status_code == 404
    assert table.rows[("CONV#conv-1", "CONV")] == conv

    current = _client(
        teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}
    ).patch("/teachers/me/help-requests/help-1", json={"status": "resolved"})

    assert current.status_code == 200
    assert table.rows[("CONV#conv-1", "CONV")]["escalation_status"] == "resolved"


def test_help_request_authorization_outage_returns_503_before_mutation(monkeypatch):
    updates = []
    monkeypatch.setattr(
        teachers,
        "_get_conversation",
        lambda _id: {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "escalated": True,
            "teacher_id": "teacher-1",
        },
    )

    class Table:
        def update_item(self, **kwargs):
            updates.append(kwargs)

    class Outage:
        async def facts_for(self, *_args, **_kwargs):
            raise RuntimeError("authorization store unavailable")

    monkeypatch.setattr(teachers, "get_table", lambda: Table())
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": "teacher-1", "role": "teacher"})
    app.dependency_overrides[get_authorization_fact_repository] = Outage
    response = TestClient(app).patch(
        "/teachers/me/help-requests/help-1", json={"status": "resolved"}
    )

    assert response.status_code == 503
    assert updates == []


# --- A teacher can go off dispatch and come back (stoasystem/stoa-backend#67) ---
#
# These run the real route and the real `user_repo` against the shared table
# double, then ask the real dispatch planner what it now thinks of the teacher.
# Stubbing the repository is how "every save writes `available`" went unseen.

from fakes.dynamodb import FakeTable  # noqa: E402

from stoa.db.repositories import account_deletion_repo, user_repo  # noqa: E402

_TEACHER = "teacher-67"
_QUESTION = {"question_id": "q-67", "subject": "physics", "status": "escalated"}


def _availability_table(monkeypatch, **profile_fields) -> FakeTable:
    table = FakeTable()
    table.seed(
        {
            "PK": f"USER#{_TEACHER}",
            "SK": "PROFILE",
            "user_id": _TEACHER,
            "role": "teacher",
            "account_status": "active",
            "version": 1,
            **profile_fields,
        },
        {
            "PK": f"USER#{_TEACHER}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": 1,
        },
    )
    for module in (user_repo, account_deletion_repo, teacher_dispatch_service):
        monkeypatch.setattr(module, "get_table", lambda table=table: table)
    return table


def _teacher_client() -> TestClient:
    return _client(teachers.router, "/teachers", {"sub": _TEACHER, "role": "teacher"})


def _save(client: TestClient, **extra):
    body = {
        "subjects": ["physics"],
        "weeklyAvailability": [
            {"dayOfWeek": "monday", "startTime": "16:00", "endTime": "18:00"}
        ],
        **extra,
    }
    return client.patch("/teachers/me/availability", json=body)


def _planner_verdict() -> str:
    plan = teacher_dispatch_service.plan_dispatch(dict(_QUESTION))
    if plan["selected"]:
        return "selected"
    return plan["refused"][0]["refusalCode"]


def test_first_save_without_status_still_puts_a_new_teacher_on_dispatch(monkeypatch):
    # The deployed editor sends no status; saving must keep working as it did.
    _availability_table(monkeypatch)
    client = _teacher_client()
    assert client.get("/teachers/me/availability").json()["status"] is None

    response = _save(client)

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert _planner_verdict() == "selected"


def test_paused_teacher_is_refused_by_dispatch_and_can_come_back(monkeypatch):
    table = _availability_table(monkeypatch)
    client = _teacher_client()
    assert _save(client).json()["status"] == "available"

    paused = _save(client, status="paused")

    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    stored = table.rows[(f"USER#{_TEACHER}", "PROFILE")]
    assert stored["dispatch_availability"] == "paused"
    assert stored["availability_status"] == "paused"
    assert _planner_verdict() == "not_available"
    assert teacher_dispatch_service.teacher_availability_summary()["online"] is False

    back = _save(client, status="available")

    assert back.json()["status"] == "available"
    assert _planner_verdict() == "selected"


def test_editing_the_schedule_without_status_keeps_a_paused_teacher_paused(monkeypatch):
    _availability_table(monkeypatch)
    client = _teacher_client()
    _save(client, status="paused")

    edited = client.patch(
        "/teachers/me/availability",
        json={"subjects": ["physics", "chemistry"], "weeklyAvailability": []},
    )

    assert edited.status_code == 200
    assert edited.json()["status"] == "paused"
    assert edited.json()["subjects"] == ["physics", "chemistry"]
    assert _planner_verdict() == "not_available"


def test_availability_status_accepts_only_available_or_paused(monkeypatch):
    table = _availability_table(monkeypatch)
    before = dict(table.rows[(f"USER#{_TEACHER}", "PROFILE")])

    response = _save(_teacher_client(), status="busy")

    assert response.status_code == 422
    assert table.rows[(f"USER#{_TEACHER}", "PROFILE")] == before


@pytest.mark.parametrize(
    "legacy",
    [{"availability_status": "paused"}, {"teacher_status": "offline"}],
    ids=["availability_status", "teacher_status"],
)
def test_a_pause_stored_only_in_an_older_field_survives_a_schedule_save(monkeypatch, legacy):
    # The planner falls back through three fields; keeping only the first one
    # let an older profile's pause be overwritten with `available`.
    table = _availability_table(monkeypatch, subjects=["physics"], **legacy)
    client = _teacher_client()
    assert client.get("/teachers/me/availability").json()["status"] == "paused"
    assert _planner_verdict() == "not_available"

    saved = _save(client)

    assert saved.status_code == 200
    assert saved.json()["status"] == "paused"
    assert _planner_verdict() == "not_available"
    stored = table.rows[(f"USER#{_TEACHER}", "PROFILE")]
    assert stored["dispatch_availability"] == stored["availability_status"]


def test_switching_status_alone_keeps_subjects_and_hours(monkeypatch):
    _availability_table(monkeypatch)
    client = _teacher_client()
    _save(client)

    paused = client.patch("/teachers/me/availability", json={"status": "paused"})

    assert paused.status_code == 200
    assert paused.json()["subjects"] == ["physics"]
    assert paused.json()["weeklyAvailability"] == [
        {"dayOfWeek": "monday", "startTime": "16:00", "endTime": "18:00"}
    ]

    back = client.patch("/teachers/me/availability", json={"status": "available"})

    assert back.json()["subjects"] == ["physics"]
    assert _planner_verdict() == "selected"


def test_a_pause_that_lands_between_read_and_write_is_kept(monkeypatch):
    # The kept status must come from the read the version check is made against.
    # Another writer pauses the teacher after the first read; that attempt loses
    # the version race, and the retry must see the pause rather than undo it.
    _availability_table(monkeypatch, subjects=["physics"], dispatch_availability="available")
    key = (f"USER#{_TEACHER}", "PROFILE")
    real_transact = account_deletion_repo.transact
    raced = []

    def transact_after_a_concurrent_pause(operations, *, table=None):
        if not raced:
            raced.append(True)
            row = table.rows[key]
            row["dispatch_availability"] = "paused"
            row["version"] = row["version"] + 1
        return real_transact(operations, table=table)

    monkeypatch.setattr(account_deletion_repo, "transact", transact_after_a_concurrent_pause)

    saved = _save(_teacher_client())

    assert raced
    assert saved.status_code == 200
    assert saved.json()["status"] == "paused"
    assert _planner_verdict() == "not_available"


# --- Dispatch reads a teacher's subjects one way, through the alias rule (#68) ---


def _verdict_for(subject: str) -> str:
    plan = teacher_dispatch_service.plan_dispatch({**_QUESTION, "subject": subject})
    if plan["selected"]:
        return "selected"
    return plan["refused"][0]["refusalCode"]


@pytest.mark.parametrize(
    ("teacher_subject", "question_subject", "verdict"),
    [
        ("math", "mathematics", "selected"),
        ("mathematics", "math", "selected"),
        (" Math ", "Mathematics", "selected"),
        ("physics", "mathematics", "subject_mismatch"),
        ("math", "physics", "subject_mismatch"),
    ],
)
def test_dispatch_compares_subjects_through_the_alias_rule(
    monkeypatch, teacher_subject, question_subject, verdict
):
    # `math` is canonical and stored content still says `mathematics`
    # (stoasystem/stoa-backend#62); a teacher who picks either must match both.
    _availability_table(monkeypatch)
    _save(_teacher_client(), subjects=[teacher_subject])

    assert _verdict_for(question_subject) == verdict


def test_clearing_subjects_also_clears_an_older_subject_ids_list(monkeypatch):
    # Reading falls back through four fields; an explicit `[]` saved to the
    # newer three used to leave `subject_ids` answering for the teacher.
    _availability_table(
        monkeypatch, subject_ids=["physics"], dispatch_availability="available"
    )
    client = _teacher_client()
    assert client.get("/teachers/me/availability").json()["subjects"] == ["physics"]
    assert _verdict_for("physics") == "selected"

    cleared = client.patch("/teachers/me/availability", json={"subjects": []})

    assert cleared.status_code == 200
    assert cleared.json()["subjects"] == []
    assert client.get("/teachers/me/availability").json()["subjects"] == []
    assert _verdict_for("physics") == "missing_subject_capability"
