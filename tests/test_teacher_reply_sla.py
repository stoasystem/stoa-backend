from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable, without_owner_registry
from stoa.db import table as db_table
from stoa.routers import admin, teachers
from stoa.routers.admin import stats
from stoa.services import help_requests
from actor_helpers import install_actor_overrides


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
    return TestClient(app)


def _help_requests_table(*records: dict) -> FakeTable:
    """Help requests as their own records (#189), on the shared table double."""
    table = FakeTable()
    table.seed(
        *(
            # With the index keys the store writes (#608): the teacher's queue
            # reads the requests through them.
            {**row, **help_requests.index_fields(row)}
            for row in (
                {
                    "PK": f"CONV#{record['conversation_id']}",
                    "SK": "HELP",
                    "entity_type": "help_request",
                    "escalation_request_id": record["conversation_id"],
                    "version": 1,
                    **record,
                }
                for record in records
            )
        )
    )
    return table


def test_admin_stats_exposes_aggregate_teacher_sla_without_content(monkeypatch):
    # Help requests in the period (#697), each with a teacher's reply.
    monkeypatch.setattr(stats, "_now", lambda: datetime(2026, 6, 10, tzinfo=timezone.utc))
    table = _help_requests_table(
        {
            "conversation_id": "c-1",
            "student_id": "student-1",
            "escalation_status": "resolved",
            "created_at": "2026-06-08T08:00:00+00:00",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "accepted_at": "2026-06-08T08:05:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:10:00+00:00",
            "content": "private question text",
        },
        {
            "conversation_id": "c-2",
            "student_id": "student-1",
            "escalation_status": "in_progress",
            "created_at": "2026-06-08T08:00:00+00:00",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "accepted_at": "2026-06-08T08:15:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:35:00+00:00",
        },
    )
    for row in list(table.rows.values()):
        table.seed({**row, **help_requests.listing_fields(row)})
    db_table.install(table)

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
    assert "private" not in serialized
    assert "student-1" not in serialized
    assert "weekly-reports/" not in serialized


def test_teacher_note_accepts_rich_teacher_reply_payload(monkeypatch):
    table = _help_requests_table(
        {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "account_fence_generation": 4,
            "escalation_status": "in_progress",
            "teacher_id": "teacher-1",
            "escalated_at": "2026-06-08T08:00:00+00:00",
        }
    )
    db_table.install(table)
    monkeypatch.setattr(teachers.user_repo, "get_user", lambda user_id, **_kwargs: {"name": "Teacher One"})
    # The holder's reply is one transaction behind the student's fence (#74).
    captured: list[dict] = []
    monkeypatch.setattr(
        help_requests.account_deletion_repo,
        "require_active_account_fence",
        lambda user_id, generation=None, *, table=None: {"status": "active", "generation": 4},
    )
    monkeypatch.setattr(
        db_table,
        "transact",
        lambda operations, *, table=None: captured.extend(operations),
    )

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})
    response = client.post(
        "/teachers/me/help-requests/conv-1/notes",
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
    assert captured[0]["ConditionCheck"]["Key"] == {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE"}
    assert captured[0]["ConditionCheck"]["ExpressionAttributeValues"][":generation"] == 4
    # ...and only while the request is still the replying teacher's (#145),
    # in the same write as the request's own (#189).
    [holder] = [op["Update"] for op in captured if "Update" in op]
    assert holder["Key"] == {"PK": "CONV#conv-1", "SK": "HELP"}
    assert "teacher_id = :teacher" in holder["ConditionExpression"]
    assert holder["ExpressionAttributeValues"][":teacher"] == "teacher-1"
    note, message = (op["Put"]["Item"] for op in without_owner_registry(captured) if "Put" in op)
    assert note["teacher_response_format"] == "stoa_teacher_reply_v1"
    assert message["teacher_response_rich"]["blocks"][1]["type"] == "formula"


def test_teacher_help_requests_expose_sla_and_average_response(monkeypatch):
    table = _help_requests_table(
        {
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "teacher_id": "teacher-1",
            "escalation_status": "pending",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:18:00+00:00",
            "subject": "Mathematics",
        },
        {
            "conversation_id": "conv-2",
            "student_id": "student-2",
            "teacher_id": "teacher-1",
            "escalation_status": "resolved",
            "escalated_at": "2026-06-08T08:00:00+00:00",
            "first_teacher_action_at": "2026-06-08T08:42:00+00:00",
            "subject": "Mathematics",
        },
    )
    db_table.install(table)
    monkeypatch.setattr(teachers, "_get_student_name", lambda student_id: "Student")

    client = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"})

    response = client.get("/teachers/me/help-requests")
    assert response.status_code == 200
    data = response.json()
    items_by_id = {item["requestId"]: item for item in data["items"]}
    assert items_by_id["conv-2"]["sla"]["status"] == "breached"
    assert items_by_id["conv-1"]["sla"]["requestToFirstActionMinutes"] == 18

    response = client.get("/teachers/me/stats")
    assert response.status_code == 200
    assert response.json()["averageResponseTimeMinutes"] == 30
