"""The learning profile's three totals, for the five typical students (#695).

`questionCount`, `aiResolvedCount` and `teacherEscalationCount` are
`student_activity`'s new questions, AI resolved and asked a teacher, per
subject, over the last 90 days: the stretch the weak topics are judged over.
The student's page, the parent's page and the learning memory all get them
from `learning_profile_service.build_learning_profile`. The numbers of each
typical student (`fakes.activity_students`) are written out here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes import activity_students as typical
from fakes import student_evidence as fake_evidence
from fakes.help_requests import seed_request
from fakes.learning_session import seed_conversation, seed_message
from stoa.db.repositories import user_repo
from stoa.routers import parents, students
from stoa.services import adaptive_learning_service, learning_profile_service

#: (questionCount, aiResolvedCount, teacherEscalationCount) per subject; a
#: subject not named has done nothing.
TOTALS = {
    # Three new questions in one conversation; the two follow-ups are none.
    "lena": {"math": (3, 3, 0)},
    # Last week's conversation counts with both its new questions and its
    # resolved request; the one a teacher is on counts; the withdrawn and the
    # expired ones do not, so their questions are AI resolved.
    "jonas": {"math": (4, 1, 2), "physics": (1, 1, 0)},
    # Both sides of the week's edge: ninety days know no week.
    "mia": {"math": (2, 2, 0)},
    # Last week's two questions, in a conversation that asked a teacher.
    "noah": {"math": (2, 0, 1)},
    # Sixty conversations, every one read.
    "sara": {"german": (30, 29, 1), "math": (30, 29, 1)},
}


def _totals(profile: dict) -> dict[str, tuple[int, int, int]]:
    """The subjects that have done something, with their three totals."""
    return {
        item["subject"]: numbers
        for item in profile["subjectActivity"]
        if (
            numbers := (
                item["questionCount"],
                item["aiResolvedCount"],
                item["teacherEscalationCount"],
            )
        )
        != (0, 0, 0)
    }


def _profile(student_id: str, evidence, questions: list[dict] | None = None) -> dict:
    return learning_profile_service.build_learning_profile(
        student_id=student_id, questions=questions or [], evidence=evidence
    )


@pytest.mark.parametrize("student", typical.STUDENTS, ids=lambda student: student.key)
def test_the_totals_of_the_last_ninety_days(fake_table, student: typical.Student) -> None:
    typical.seed(fake_table, student)

    profile = _profile(student.id, typical.evidence(student))

    assert _totals(profile) == TOTALS[student.key]
    # Every subject the platform teaches has its line, done or not.
    assert [item["subject"] for item in profile["subjectActivity"]] == [
        "math",
        "physics",
        "german",
        "english",
    ]


def test_what_is_older_than_ninety_days_is_not_counted(fake_table) -> None:
    # `typical.NOW` is 26 November 15:00 UTC; ninety days before is 28 August 15:00.
    for conversation_id, started, answered, asked in (
        ("old", "2026-08-28T14:00:00+00:00", "2026-08-28T14:01:00+00:00", "2026-08-28T14:30:00+00:00"),
        ("new", "2026-08-28T15:00:00+00:00", "2026-08-28T15:01:00+00:00", "2026-08-28T15:30:00+00:00"),
    ):
        seed_conversation(
            fake_table, conversation_id=conversation_id, student_id="s1", subject="physics", now=started
        )
        seed_message(
            fake_table,
            conversation_id=conversation_id,
            role="assistant",
            message_id=f"{conversation_id}-a",
            student_id="s1",
            content="So geht es.",
            created_at=answered,
            structured={"kind": "answer", "answer": "So geht es."},
        )
        seed_request(
            fake_table,
            conversation_id=conversation_id,
            student_id="s1",
            status="resolved",
            asked_at=asked,
            subject="physics",
        )

    profile = _profile("s1", fake_evidence.evidence("s1", now=typical.NOW))

    assert _totals(profile) == {"physics": (1, 0, 1)}


def test_a_question_row_of_the_retired_flow_counts_for_nothing_but_its_rating(fake_table) -> None:
    rows = [
        {
            "question_id": "q1",
            "subject": "physics",
            "status": "ai_answered",
            "student_feedback": Decimal(4),
            "created_at": "2026-11-20T08:00:00+00:00",
        },
        {
            "question_id": "q2",
            "subject": "physics",
            "status": "escalated",
            "teacher_help_requested": True,
            "student_feedback": Decimal(1),
            "created_at": "2026-11-21T08:00:00+00:00",
        },
    ]

    profile = _profile("s1", fake_evidence.evidence("s1", now=typical.NOW), rows)

    assert _totals(profile) == {}
    physics = next(item for item in profile["subjectActivity"] if item["subject"] == "physics")
    assert physics["feedbackAverage"] == 2.5


# ── The three readers ────────────────────────────────────────────────────────


@pytest.fixture
def jonas(fake_table, monkeypatch: pytest.MonkeyPatch) -> typical.Student:
    typical.seed(fake_table, typical.JONAS)
    fake_evidence.install(monkeypatch, typical.evidence(typical.JONAS))
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_k: {"user_id": user_id, "role": "student", "account_status": "active"},
    )
    return typical.JONAS


def test_the_student_reads_them(jonas: typical.Student) -> None:
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    install_actor_overrides(app, {"sub": jonas.id, "role": "student"})

    response = TestClient(app).get(f"/students/{jonas.id}/learning-profile")

    assert response.status_code == 200, response.text
    assert _totals(response.json()) == TOTALS["jonas"]


def test_the_parent_reads_them(jonas: typical.Student) -> None:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    install_actor_overrides(app, {"sub": "parent-695", "role": "parent"})

    response = TestClient(app).get(f"/parents/me/children/{jonas.id}/learning-profile")

    assert response.status_code == 200, response.text
    assert _totals(response.json()) == TOTALS["jonas"]


def test_the_learning_memory_reads_them(jonas: typical.Student) -> None:
    summary = adaptive_learning_service.get_memory_summary(
        student_id=jonas.id, user={"user_id": jonas.id, "role": "student"}
    )

    assert _totals(summary) == TOTALS["jonas"]
