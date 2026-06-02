from datetime import date

import pytest

from stoa.services import report_service


class FakeTable:
    def __init__(self, children=None, conversations=None):
        self.children = children or []
        self.conversations = conversations or []

    def scan(self, **kwargs):
        return {"Items": self.children}

    def query(self, **kwargs):
        return {"Items": self.conversations}


def patch_sources(monkeypatch, *, children=None, questions=None, progress=None, mistakes=None, conversations=None):
    monkeypatch.setattr(
        report_service,
        "get_table",
        lambda: FakeTable(children=children, conversations=conversations),
    )
    monkeypatch.setattr(
        report_service.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "email": f"{user_id}@example.com", "name": "Parent"},
    )
    monkeypatch.setattr(
        report_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500, last_key=None: {"Items": questions or []},
    )
    monkeypatch.setattr(report_service.practice_repo, "get_progress", lambda student_id: progress or [])
    monkeypatch.setattr(report_service.practice_repo, "get_mistakes", lambda student_id: mistakes or [])


def test_report_week_window_accepts_iso_date():
    start, end = report_service.report_week_window("2026-06-01")

    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 8)


def test_report_week_window_rejects_invalid_date():
    with pytest.raises(ValueError):
        report_service.report_week_window("not-a-date")


def test_empty_aggregation_returns_zero_payload(monkeypatch):
    patch_sources(
        monkeypatch,
        children=[
            {
                "user_id": "student-1",
                "parent_id": "parent-1",
                "role": "student",
                "email": "student@example.com",
                "name": "Student",
            }
        ],
    )

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")

    assert payload["metrics"] == {
        "questionsAsked": 0,
        "aiResolved": 0,
        "teacherHelpRequests": 0,
        "practiceLessonsCompleted": 0,
        "mistakesLogged": 0,
    }
    assert payload["weakTopics"] == []
    assert payload["activities"] == []
    assert payload["sourceCounts"] == {
        "questions": 0,
        "practiceProgress": 0,
        "mistakes": 0,
        "conversations": 0,
    }


def test_mixed_weekly_activity_aggregates_metrics_and_topics(monkeypatch):
    patch_sources(
        monkeypatch,
        children=[
            {
                "user_id": "student-1",
                "parent_id": "parent-1",
                "role": "student",
                "email": "student@example.com",
                "name": "Student",
                "grade": "6",
            }
        ],
        questions=[
            {
                "question_id": "q1",
                "student_id": "student-1",
                "status": "ai_answered",
                "subject": "math",
                "knowledge_points": ["fractions"],
                "created_at": "2026-06-02T10:00:00Z",
                "summary": "Fractions question",
            },
            {
                "question_id": "q2",
                "student_id": "student-1",
                "status": "teacher_requested",
                "subject": "math",
                "knowledge_points": ["fractions", "ratios"],
                "created_at": "2026-06-03T10:00:00Z",
            },
            {
                "question_id": "old",
                "student_id": "student-1",
                "status": "ai_answered",
                "created_at": "2026-05-20T10:00:00Z",
            },
        ],
        progress=[
            {
                "lesson_id": "lesson-1",
                "status": "completed",
                "subject_id": "math",
                "topic_id": "fractions",
                "completed_at": "2026-06-04T08:00:00Z",
            }
        ],
        mistakes=[
            {
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "fractions",
                "created_at": "2026-06-05T08:00:00Z",
            }
        ],
        conversations=[
            {
                "conversation_id": "conv-1",
                "student_id": "student-1",
                "entity_type": "conversation",
                "escalated": True,
                "subject": "math",
                "updated_at": "2026-06-06T08:00:00Z",
                "last_message_preview": "Need help",
            }
        ],
    )

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")

    assert payload["student"]["grade"] == "6"
    assert payload["metrics"] == {
        "questionsAsked": 2,
        "aiResolved": 1,
        "teacherHelpRequests": 2,
        "practiceLessonsCompleted": 1,
        "mistakesLogged": 1,
    }
    assert payload["weakTopics"][:2] == [
        {"topic": "fractions", "count": 3},
        {"topic": "math", "count": 3},
    ]
    assert [activity["id"] for activity in payload["activities"]][:2] == ["conv-1", "challenge-1"]


def test_unlinked_student_raises(monkeypatch):
    patch_sources(monkeypatch, children=[])

    with pytest.raises(ValueError, match="student is not linked"):
        report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")
