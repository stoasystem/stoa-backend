from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import admin, questions, teachers
from stoa.security.route_authorization import get_authorization_fact_repository
from actor_helpers import install_actor_overrides


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
    return TestClient(app)


class FakeTeacherTable:
    def __init__(self):
        self.put_items = []
        self.update_calls = []

    def put_item(self, Item):
        self.put_items.append(Item)

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)


def test_request_teacher_records_request_and_queue_timestamps(monkeypatch):
    updates = []
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "status": "ai_answered",
        },
    )
    monkeypatch.setattr(
        questions.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )
    monkeypatch.setattr(questions.notify_service, "enqueue_teacher_request", lambda **kwargs: None)
    monkeypatch.setattr(questions.usage_ledger_service, "record_usage_event", lambda **kwargs: None)

    client = _app(questions.router, "/questions", {"sub": "student-1", "role": "student"})
    response = client.post("/questions/question-1/request-teacher")

    assert response.status_code == 202
    assert updates[0][1] == "escalated"
    attrs = updates[0][2]
    assert attrs["teacher_requested_at"]
    assert attrs["queue_visible_at"] == attrs["teacher_requested_at"]


def test_teacher_reply_accepts_formula_payload_and_records_sla(monkeypatch):
    updates = []
    table = FakeTeacherTable()
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-08T08:35:00+00:00")
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "teacher_active",
            "teacher_id": "teacher-1",
            "teacher_requested_at": "2026-06-08T08:00:00+00:00",
            "teacher_taken_over_at": "2026-06-08T08:10:00+00:00",
        },
    )
    monkeypatch.setattr(
        teachers.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post(
        "/teachers/questions/question-1/reply",
        json={
            "rich_content": {
                "version": 1,
                "blocks": [
                    {"type": "paragraph", "text": "Move 4 to the right side."},
                    {"type": "formula", "latex": "2x + 4 = 10"},
                ],
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["teacher_response"] == "Move 4 to the right side.\n2x + 4 = 10"
    assert body["teacher_response_rich"]["blocks"][1] == {"type": "formula", "latex": "2x + 4 = 10"}
    assert body["teacher_response_format"] == "stoa_teacher_reply_v1"
    assert body["teacher_first_reply_sla_bucket"] == "breached"
    attrs = updates[0][2]
    assert attrs["teacher_response_text"] == body["teacher_response"]
    assert attrs["teacher_first_replied_at"] == "2026-06-08T08:35:00+00:00"
    assert attrs["sla_request_to_first_reply_seconds"] == 2100
    assert attrs["sla_takeover_to_first_reply_seconds"] == 1500


def test_teacher_reply_refuses_private_markers_and_raw_html(monkeypatch):
    updates = []
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "teacher_active",
            "teacher_id": "teacher-1",
        },
    )
    monkeypatch.setattr(
        teachers.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post(
        "/teachers/questions/question-1/reply",
        json={"content": "<script>alert(1)</script> private/student-1/image.png"},
    )

    assert response.status_code == 422
    assert updates == []


def test_teacher_reply_requires_owner_and_active_state(monkeypatch):
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "resolved",
            "teacher_id": "teacher-1",
        },
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-2", "role": "teacher"})
    response = client.post("/teachers/questions/question-1/reply", json={"content": "Safe reply"})
    assert response.status_code == 404

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post("/teachers/questions/question-1/reply", json={"content": "Safe reply"})
    assert response.status_code == 409


def test_teacher_reply_authorization_outage_returns_503_before_mutation(monkeypatch):
    updates = []
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "teacher_active",
            "teacher_id": "teacher-1",
        },
    )
    monkeypatch.setattr(
        teachers.question_repo,
        "update_status",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    class Outage:
        async def facts_for(self, *_args, **_kwargs):
            raise RuntimeError("repository unavailable")

    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(app, {"sub": "teacher-1", "role": "teacher"})
    app.dependency_overrides[get_authorization_fact_repository] = Outage
    response = TestClient(app).post(
        "/teachers/questions/question-1/reply", json={"content": "Safe reply"}
    )

    assert response.status_code == 503
    assert updates == []


def test_teacher_takeover_records_takeover_sla(monkeypatch):
    updates = []
    table = FakeTeacherTable()
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-08T08:12:00+00:00")
    monkeypatch.setattr(
        teachers.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "status": "escalated",
            "teacher_requested_at": "2026-06-08T08:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        teachers.question_repo,
        "update_status",
        lambda question_id, status, **attrs: updates.append((question_id, status, attrs)),
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post("/teachers/questions/question-1/takeover")

    assert response.status_code == 200
    assert updates[0][1] == "teacher_active"
    assert updates[0][2]["teacher_taken_over_at"] == "2026-06-08T08:12:00+00:00"
    assert updates[0][2]["sla_request_to_takeover_seconds"] == 720
    assert table.put_items[0]["student_id"] == "student-1"


class FakeAdminTable:
    def scan(self, **kwargs):
        projection = kwargs.get("ProjectionExpression", "")
        if projection == "#role":
            return {
                "Items": [
                    {"role": "student"},
                    {"role": "teacher"},
                    {"role": "parent"},
                ]
            }
        return {
            "Items": [
                {
                    "status": "resolved",
                    "teacher_requested_at": "2026-06-08T08:00:00+00:00",
                    "teacher_first_replied_at": "2026-06-08T08:10:00+00:00",
                    "sla_request_to_takeover_seconds": 300,
                    "sla_request_to_first_reply_seconds": 600,
                    "sla_request_to_resolved_seconds": 1200,
                    "teacher_first_reply_sla_bucket": "within_target",
                },
                {
                    "status": "teacher_active",
                    "teacher_requested_at": "2026-06-08T08:00:00+00:00",
                    "teacher_first_replied_at": "2026-06-08T08:35:00+00:00",
                    "sla_request_to_takeover_seconds": 900,
                    "sla_request_to_first_reply_seconds": 2100,
                    "teacher_first_reply_sla_bucket": "breached",
                },
                {"status": "ai_answered"},
            ]
        }


def test_admin_stats_exposes_aggregate_teacher_sla_without_content(monkeypatch):
    monkeypatch.setattr(admin, "get_table", lambda: FakeAdminTable())

    client = _app(admin.router, "/admin", {"sub": "admin-1", "role": "admin"})
    response = client.get("/admin/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["teacher_sla"]["tracked_questions"] == 2
    assert data["teacher_sla"]["first_reply"] == {
        "count": 2,
        "average_seconds": 1350,
        "max_seconds": 2100,
    }
    assert data["teacher_sla"]["buckets"] == {
        "within_target": 1,
        "at_risk": 0,
        "breached": 1,
        "unknown": 0,
    }
    serialized = str(data)
    assert "content" not in serialized
    assert "private/" not in serialized
    assert "weekly-reports/" not in serialized


def test_teacher_note_accepts_rich_teacher_reply_payload(monkeypatch):
    table = FakeTeacherTable()
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(
        teachers,
        "_get_conversation",
        lambda request_id: {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "escalated": True,
            "teacher_id": "teacher-1",
            "escalated_at": "2026-06-08T08:00:00+00:00",
        },
    )
    monkeypatch.setattr(teachers.user_repo, "get_user", lambda user_id: {"name": "Teacher One"})

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post(
        "/teachers/me/help-requests/help-1/notes",
        json={
            "content": "Subtract 5 from both sides.\n3x = 15",
            "richContent": {
                "version": 1,
                "blocks": [
                    {"type": "paragraph", "text": "Subtract 5 from both sides."},
                    {"type": "formula", "latex": "3x = 15"},
                ],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["richContent"]["blocks"][1] == {"type": "formula", "latex": "3x = 15"}
    assert table.put_items[0]["teacher_response_format"] == "stoa_teacher_reply_v1"
    assert table.put_items[1]["teacher_response_rich"]["blocks"][1]["type"] == "formula"


def test_teacher_help_requests_expose_sla_and_average_response(monkeypatch):
    conversations = [
        {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "teacher_id": "teacher-1",
            "escalation_request_id": "help-1",
            "escalation_status": "pending",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:18:00+00:00",
            "subject": "Mathematics",
        },
        {
            "conversation_id": "conv-2",
            "student_id": "student-2",
            "teacher_id": "teacher-1",
            "escalation_request_id": "help-2",
            "escalation_status": "resolved",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:42:00+00:00",
            "subject": "Mathematics",
        },
    ]
    monkeypatch.setattr(teachers, "_get_escalated_conversations", lambda: conversations)
    monkeypatch.setattr(teachers, "_get_student_name", lambda student_id: "Student")

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})

    response = client.get("/teachers/me/help-requests")
    assert response.status_code == 200
    data = response.json()
    items_by_id = {item["requestId"]: item for item in data["items"]}
    assert items_by_id["help-2"]["sla"]["status"] == "breached"
    assert items_by_id["help-1"]["sla"]["requestToFirstActionMinutes"] == 18

    response = client.get("/teachers/me/stats")
    assert response.status_code == 200
    assert response.json()["averageResponseTimeMinutes"] == 30
