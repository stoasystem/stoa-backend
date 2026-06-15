from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import admin, teachers
from stoa.services import teacher_dispatch_service


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


QUESTION = {
    "question_id": "question-1",
    "student_id": "student-1",
    "subject": "math",
    "status": "escalated",
    "teacher_requested_at": "2026-06-15T10:00:00+00:00",
    "queue_visible_at": "2026-06-15T10:00:00+00:00",
}


TEACHERS = [
    {
        "user_id": "teacher-low-load",
        "role": "teacher",
        "subjects": ["math"],
        "dispatch_availability": "available",
        "active_session_count": 0,
        "max_active_sessions": 2,
        "recent_sla_bucket": "within_target",
        "last_dispatched_at": "2026-06-15T08:00:00+00:00",
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
        "user_id": "teacher-german",
        "role": "teacher",
        "subjects": ["german"],
        "dispatch_availability": "available",
        "active_session_count": 0,
        "max_active_sessions": 2,
    },
    {
        "user_id": "teacher-paused",
        "role": "teacher",
        "subjects": ["math"],
        "dispatch_availability": "paused",
    },
]


def test_dispatch_planner_ranks_eligible_and_explains_refusals():
    plan = teacher_dispatch_service.plan_dispatch(
        QUESTION,
        TEACHERS,
        now="2026-06-15T10:05:00+00:00",
    )

    assert plan["status"] == "ready"
    assert plan["selected"][0]["teacherId"] == "teacher-low-load"
    refusals = {item["teacherId"]: item["refusalCode"] for item in plan["refused"]}
    assert refusals["teacher-busy"] == "max_active_sessions"
    assert refusals["teacher-german"] == "subject_mismatch"
    assert refusals["teacher-paused"] == "not_available"


def test_dispatch_question_conditionally_claims_best_teacher(monkeypatch):
    updates = []
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", lambda question_id: dict(QUESTION))
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "update_status_conditionally",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)) or True,
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "dispatched"
    assert result["teacherId"] == "teacher-low-load"
    assert updates[0][2]["dispatch_status"] == "dispatched"
    assert updates[0][2]["dispatched_teacher_id"] == "teacher-low-load"
    assert updates[0][2]["dispatch_attempt_count"] == 1


def test_dispatch_question_uses_fresh_escalation_snapshot(monkeypatch):
    updates = []
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "get_question",
        lambda question_id: {**QUESTION, "status": "ai_answered"},
    )
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "update_status_conditionally",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)) or True,
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        question=dict(QUESTION),
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "dispatched"
    assert updates[0][2]["dispatched_teacher_id"] == "teacher-low-load"


def test_dispatch_question_reports_claim_conflict(monkeypatch):
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", lambda question_id: dict(QUESTION))
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "update_status_conditionally",
        lambda question_id, status, **attrs: False,
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "claim_conflict"


def test_reassign_timed_out_dispatch_excludes_previous_teacher(monkeypatch):
    stale_question = {
        **QUESTION,
        "dispatch_status": "dispatched",
        "dispatched_teacher_id": "teacher-low-load",
        "dispatch_deadline_at": "2026-06-15T10:10:00+00:00",
        "dispatch_attempt_count": 1,
    }
    updates = []
    questions = {
        "question-1": dict(stale_question),
    }

    def get_question(question_id):
        return questions[question_id]

    def update_status(question_id, status, **attrs):
        updates.append((question_id, status, attrs))
        questions[question_id] = {**questions[question_id], "status": status, **attrs}

    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: TEACHERS[:2])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", get_question)
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "update_status", update_status)
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "update_status_conditionally",
        lambda question_id, status, **attrs: update_status(question_id, status, **attrs) or True,
    )

    result = teacher_dispatch_service.reassign_timed_out_dispatches(
        [stale_question],
        now="2026-06-15T10:15:00+00:00",
    )

    assert result["processed"] == 1
    assert updates[0][2]["dispatch_status"] == "timed_out"
    assert updates[0][2]["previous_dispatch_teacher_ids"] == ["teacher-low-load"]
    assert result["results"][0]["status"] == "no_candidate"
    assert result["results"][0]["plan"]["summary"]["noCandidateReason"] == "max_active_sessions"


def test_teacher_queue_filters_dispatches_owned_by_other_teachers(monkeypatch):
    items = [
        {**QUESTION, "question_id": "mine", "dispatch_status": "dispatched", "dispatched_teacher_id": "teacher-1"},
        {**QUESTION, "question_id": "other", "dispatch_status": "dispatched", "dispatched_teacher_id": "teacher-2"},
        {**QUESTION, "question_id": "manual", "dispatch_status": "unassigned"},
    ]
    monkeypatch.setattr(teachers, "_list_escalated_questions", lambda: items)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-15T10:05:00+00:00")

    response = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}).get("/teachers/queue")

    assert response.status_code == 200
    ids = {item["question_id"] for item in response.json()["items"]}
    assert ids == {"mine", "manual"}
    mine = next(item for item in response.json()["items"] if item["question_id"] == "mine")
    assert mine["dispatch"]["assignedToMe"] is True


def test_takeover_accepts_current_dispatch_and_rejects_other_teacher(monkeypatch):
    updates = []
    table_items = []
    item = {
        **QUESTION,
        "dispatch_status": "dispatched",
        "dispatched_teacher_id": "teacher-1",
        "dispatch_deadline_at": "2026-06-15T10:15:00+00:00",
    }

    class FakeTable:
        def put_item(self, Item):
            table_items.append(Item)

    monkeypatch.setattr(teachers, "get_table", lambda: FakeTable())
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-15T10:05:00+00:00")
    monkeypatch.setattr(teachers.question_repo, "get_question", lambda question_id: item)
    monkeypatch.setattr(
        teachers.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )

    other = _app(teachers.router, "/teachers", {"sub": "teacher-2", "role": "teacher"}).post(
        "/teachers/questions/question-1/takeover"
    )
    assert other.status_code == 409

    mine = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/takeover"
    )
    assert mine.status_code == 200
    assert updates[0][2]["dispatch_status"] == "accepted"
    assert updates[0][2]["dispatch_accepted_at"] == "2026-06-15T10:05:00+00:00"
    assert table_items[0]["teacher_id"] == "teacher-1"


def test_admin_dispatch_dashboard_is_aggregate_and_content_safe(monkeypatch):
    questions = [
        {
            **QUESTION,
            "question_id": "question-old",
            "content": "private student content",
            "dispatch_status": "dispatched",
            "dispatched_teacher_id": "teacher-low-load",
            "dispatch_deadline_at": "2026-06-15T10:10:00+00:00",
            "dispatch_attempt_count": 2,
        },
        {
            **QUESTION,
            "question_id": "question-no-candidate",
            "dispatch_status": "unassigned",
            "dispatch_no_candidate_reason": "subject_mismatch",
        },
    ]
    monkeypatch.setattr(admin.teacher_dispatch_service, "list_teacher_dispatch_questions", lambda: questions)
    monkeypatch.setattr(admin.teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(admin.teacher_dispatch_service, "_now", lambda: "2026-06-15T10:15:00+00:00")

    response = _app(admin.router, "/admin", {"sub": "admin-1", "role": "admin"}).get(
        "/admin/teacher-dispatch/dashboard"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["queue"]["count"] == 2
    assert body["queue"]["timeoutCount"] == 1
    assert body["queue"]["reassignmentCount"] == 1
    assert body["queue"]["noCandidateReasons"] == {"subject_mismatch": 1}
    serialized = str(body)
    assert "private student content" not in serialized
