"""Questions read from a student index shared with every other row: #77.

GSI-StudentId holds every row with a `student_id` and a `created_at`: in
production 52 rows for the busiest test student, one of them a question.
`Limit` counts rows read, so a page of 20 was usually empty while more
questions waited, and readers that took a page as "questions" counted
conversations and messages. A chat help request's queue row is shaped like
a question but is not one (user decision, 2026-09-29): it is counted, and
shown, through its conversation.
"""

from __future__ import annotations

import sys


from fakes.dynamodb import FakeTable
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.db.repositories import question_repo
from stoa.routers import students

STUDENT = "student-77"


def _table(monkeypatch) -> FakeTable:
    table = FakeTable()
    rows = [
        {"PK": "CONV#c1", "SK": f"MSG#{i:03d}", "entity_type": "conversation_message",
         "student_id": STUDENT, "owner_id": STUDENT, "role": "student", "content": "m",
         "created_at": f"2026-09-2{i % 9}T10:{i:02d}:00+00:00"}
        for i in range(25)
    ]
    rows += [
        {"PK": f"QUESTION#q{n}", "SK": "META", "entity_type": "question", "question_id": f"q{n}",
         "student_id": STUDENT, "status": "ai_answered", "subject": "math", "content": f"question {n}",
         "created_at": f"2026-09-1{n}T09:00:00+00:00"}
        for n in range(3)
    ]
    rows.append(
        {"PK": "QUESTION#chat", "SK": "META", "entity_type": "question", "question_id": "chat",
         "source": "conversation_escalation", "conversation_id": "c1", "student_id": STUDENT,
         "status": "escalated", "subject": "math", "content": "help", "created_at": "2026-09-28T09:00:00+00:00"}
    )
    rows += [
        {"PK": f"USER#{STUDENT}", "SK": "PROFILE", "user_id": STUDENT, "role": "student",
         "account_status": "active", "version": 1},
        {"PK": f"USER#{STUDENT}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    ]
    table.seed(*rows)
    for name, module in list(sys.modules.items()):
        if name.startswith("stoa.") and hasattr(module, "get_table"):
            monkeypatch.setattr(module, "get_table", lambda table=table: table)
    return table


def test_a_chat_help_requests_queue_row_is_not_a_question():
    assert question_repo.is_question_record({"PK": "QUESTION#q", "SK": "META"})
    assert not question_repo.is_question_record(
        {"PK": "QUESTION#chat", "SK": "META", "source": "conversation_escalation"}
    )


def test_questions_are_read_past_the_other_rows_until_a_page_is_full(monkeypatch):
    _table(monkeypatch)

    first = question_repo.list_questions_by_student(STUDENT, limit=2)
    assert [q["question_id"] for q in first["Items"]] == ["q2", "q1"]
    assert first.get("LastEvaluatedKey")

    rest = question_repo.list_questions_by_student(STUDENT, limit=2, last_key=first["LastEvaluatedKey"])
    assert [q["question_id"] for q in rest["Items"]] == ["q0"]
    assert "LastEvaluatedKey" not in rest


def test_the_question_history_pages_without_empty_pages(monkeypatch):
    _table(monkeypatch)
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    client = TestClient(app)

    pages, token = [], None
    for _ in range(5):
        url = f"/students/{STUDENT}/questions?limit=2" + (f"&next_token={token}" if token else "")
        body = client.get(url).json()
        pages.append([item["question_id"] for item in body["items"]])
        token = body.get("next_token")
        if not token:
            break

    assert pages == [["q2", "q1"], ["q0"]]
    assert all(pages)


def test_a_parents_activity_feed_shows_questions_not_every_message(monkeypatch):
    # Every conversation message on the index used to become a "Question asked"
    # item in the parent's feed.
    from stoa.routers import parents

    _table(monkeypatch)

    activities = parents._question_history_events(STUDENT, limit=100)

    assert sorted(activity.id for activity in activities) == ["q0", "q1", "q2"]
