"""What a student did in a week, for five typical students (#693).

The parent's dashboard and history read `student_activity` alone. Each typical
student (`fakes.activity_students`) is the shape of one rule; their numbers,
their five most recent entries and their history are written out here, so a
change to a rule shows up as a changed number rather than a quiet one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes import activity_students as typical
from fakes import student_evidence as fake_evidence
from fakes.help_requests import seed_request
from fakes.learning_session import seed_conversation, seed_message
from stoa.db.repositories import user_repo
from stoa.main import RequestLocaleMiddleware
from stoa.routers import parents
from stoa.services import (
    help_requests,
    learning_session,
    locale_service,
    message_catalog,
    student_activity,
)
from stoa.services.student_activity import SubjectCounts

WEEK = student_activity.zurich_week(typical.NOW)


# ── The week ─────────────────────────────────────────────────────────────────


def test_the_week_is_the_zurich_week_the_allowance_turns_over_in() -> None:
    assert WEEK == student_activity.Period(
        datetime(2026, 11, 22, 23, 0, tzinfo=UTC), datetime(2026, 11, 29, 23, 0, tzinfo=UTC)
    )
    # Monday 00:30 in Zurich is still Sunday in UTC, and already this week.
    assert WEEK.holds("2026-11-22T23:30:00+00:00")
    assert not WEEK.holds("2026-11-22T22:59:59+00:00")
    assert not WEEK.holds("2026-11-29T23:00:00Z")
    assert not WEEK.holds("not a moment")
    # In summer the week turns over at 22:00 UTC.
    summer = student_activity.zurich_week(datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
    assert summer.start == datetime(2026, 6, 28, 22, 0, tzinfo=UTC)


def test_the_last_days_end_at_the_moment_given() -> None:
    assert student_activity.last_days(90, typical.NOW) == student_activity.Period(
        datetime(2026, 8, 28, 15, 0, tzinfo=UTC), typical.NOW
    )


# ── Which help requests count ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "holds"),
    [
        ("pending", True),
        ("in_progress", True),
        ("resolved", True),
        ("withdrawn", False),
        ("expired", False),
    ],
)
def test_a_request_holds_a_case_until_it_is_withdrawn_or_expires(status: str, holds: bool) -> None:
    assert help_requests.holds_case({"escalation_status": status}) is holds


def test_a_request_stored_without_a_state_is_pending_and_holds_a_case() -> None:
    assert help_requests.holds_case({}) is True


# ── The numbers of the week ──────────────────────────────────────────────────

COUNTS = {
    # Three new questions and two follow-ups in one conversation; a lesson,
    # two wrong answers.
    "lena": student_activity.Counts(
        new_questions=3,
        ai_resolved=3,
        teacher_help=0,
        lessons_completed=1,
        mistakes=2,
        by_subject={"math": SubjectCounts(3, 3, 0)},
    ),
    # In progress counts; withdrawn and expired do not, and their questions are
    # AI resolved. Last week's conversation, whose request was resolved last
    # week, has a new question this week: it counts, and is not AI resolved.
    "jonas": student_activity.Counts(
        new_questions=4,
        ai_resolved=2,
        teacher_help=1,
        lessons_completed=0,
        mistakes=0,
        by_subject={"math": SubjectCounts(3, 1, 1), "physics": SubjectCounts(1, 1, 0)},
    ),
    # Monday 00:30 Zurich is this week; Sunday 23:30 Zurich is not.
    "mia": student_activity.Counts(
        new_questions=1,
        ai_resolved=1,
        teacher_help=0,
        lessons_completed=1,
        mistakes=0,
        by_subject={"math": SubjectCounts(1, 1, 0)},
    ),
    # Last week's things only.
    "noah": student_activity.Counts(
        new_questions=0, ai_resolved=0, teacher_help=0, lessons_completed=0, mistakes=0
    ),
    # Sixty conversations: every one read, the two oldest asked a teacher.
    "sara": student_activity.Counts(
        new_questions=60,
        ai_resolved=58,
        teacher_help=2,
        lessons_completed=0,
        mistakes=0,
        by_subject={"german": SubjectCounts(30, 29, 1), "math": SubjectCounts(30, 29, 1)},
    ),
}


@pytest.mark.parametrize("student", typical.STUDENTS, ids=lambda student: student.key)
def test_the_numbers_of_the_week(fake_table, student: typical.Student) -> None:
    typical.seed(fake_table, student)

    counts = student_activity.counts(student.id, WEEK, evidence=typical.evidence(student))

    assert counts == COUNTS[student.key]


def test_a_new_question_in_a_session_started_last_week_takes_its_subject(fake_table) -> None:
    typical.seed(fake_table, typical.JONAS)

    period = learning_session.between(typical.JONAS.id, WEEK.start, WEEK.end)

    assert [record["conversation_id"] for record in period.records] == [
        "jonas-c1",
        "jonas-c2",
        "jonas-c3",
    ]
    assert [(answer.conversation_id, answer.new_question, answer.subject) for answer in period.answers] == [
        ("jonas-c0", True, "math"),
        ("jonas-c1", True, "math"),
        ("jonas-c2", True, "physics"),
        ("jonas-c3", True, "math"),
        ("jonas-c3", False, "math"),
    ]


def test_an_answer_stored_without_a_structure_is_no_new_question(fake_table) -> None:
    seed_conversation(
        fake_table, conversation_id="c1", student_id="s1", now="2026-11-24T10:00:00+00:00"
    )
    seed_message(
        fake_table,
        conversation_id="c1",
        role="assistant",
        message_id="a1",
        student_id="s1",
        content="Hallo",
        created_at="2026-11-24T10:01:00+00:00",
    )

    counts = student_activity.counts("s1", WEEK, evidence=fake_evidence.evidence("s1", now=typical.NOW))

    assert (counts.new_questions, counts.ai_resolved) == (0, 0)


def test_another_student_s_rows_are_not_counted(fake_table) -> None:
    typical.seed(fake_table, typical.LENA)
    seed_request(
        fake_table,
        conversation_id="lena-c1",
        student_id="somebody-else",
        status="pending",
        asked_at="2026-11-24T16:20:00+00:00",
    )

    counts = student_activity.counts(
        "somebody-else", WEEK, evidence=fake_evidence.evidence("somebody-else", now=typical.NOW)
    )

    assert (counts.new_questions, counts.teacher_help) == (0, 1)


# ── The entries ──────────────────────────────────────────────────────────────


def test_the_entries_of_a_period_are_the_sessions_started_and_the_practice_in_it(fake_table) -> None:
    typical.seed(fake_table, typical.MIA)

    entries = student_activity.activities(
        typical.MIA.id, WEEK, evidence=typical.evidence(typical.MIA), locale="de"
    )

    assert [(entry.id, entry.type, entry.created_at) for entry in entries] == [
        ("mia-l1", "practice", "2026-11-22T23:30:00+00:00"),
        ("mia-c1", "conversation", "2026-11-22T23:29:00+00:00"),
    ]


@pytest.mark.parametrize("locale", sorted(locale_service.SUPPORTED_LOCALES))
def test_the_titles_are_in_the_language_the_caller_asks_for(fake_table, locale: str) -> None:
    typical.seed(fake_table, typical.JONAS)
    typical.seed(fake_table, typical.LENA)

    titles = {
        entry.type: entry.title
        for student in (typical.JONAS, typical.LENA)
        for entry in student_activity.recent(
            student.id, limit=10, evidence=typical.evidence(student), locale=locale
        )
    }

    assert titles == {
        "conversation": message_catalog.text("activity.ai_conversation", locale),
        "teacher_help": message_catalog.text("activity.teacher_help_requested", locale),
        "practice": message_catalog.text("activity.practice_lesson_completed", locale),
        "practice_mistake": message_catalog.text("activity.practice_mistake_logged", locale),
    }


# ── Through the parent's dashboard and history ───────────────────────────────

#: (questions, AI resolved, asked a teacher, lessons) on the dashboard.
DASHBOARD = {
    "lena": (3, 3, 0, 1),
    "jonas": (4, 2, 1, 0),
    "mia": (1, 1, 0, 1),
    "noah": (0, 0, 0, 0),
    "sara": (60, 58, 2, 0),
}

#: The dashboard's five most recent entries: (id, type, summary, subject, when).
RECENT = {
    "lena": [
        ("lena-l1", "practice", "Lektion lena-l1", "math", "2026-11-25T17:00:00+00:00"),
        ("brueche-l3", "practice_mistake", "Brüche rechnen", "mathematics", "2026-11-25T16:30:00+00:00"),
        # A knowledge point the curriculum does not know is named by nothing.
        ("lena-e2", "practice_mistake", "", "mathematics", "2026-11-25T16:20:00+00:00"),
        ("lena-c1", "conversation", "", "math", "2026-11-24T16:00:00+00:00"),
    ],
    "jonas": [
        ("jonas-c3", "conversation", "", "math", "2026-11-25T15:00:00+00:00"),
        ("jonas-c2", "conversation", "", "physics", "2026-11-24T15:00:00+00:00"),
        ("jonas-c1", "teacher_help", "", "math", "2026-11-23T15:00:00+00:00"),
        ("jonas-c0", "teacher_help", "", "math", "2026-11-20T10:00:00+00:00"),
    ],
    "mia": [
        ("mia-l1", "practice", "Lektion mia-l1", "math", "2026-11-22T23:30:00+00:00"),
        ("mia-c1", "conversation", "", "math", "2026-11-22T23:29:00+00:00"),
        ("mia-l0", "practice", "Lektion mia-l0", "math", "2026-11-22T22:40:00+00:00"),
        ("mia-c0", "conversation", "", "math", "2026-11-22T22:30:00+00:00"),
    ],
    "noah": [
        ("report-noah-2026-11-16", "report", "Eine ruhige Woche.", None, "2026-11-23T06:00:00+00:00"),
        ("noah-l1", "practice", "Lektion noah-l1", "math", "2026-11-19T10:00:00+00:00"),
        ("brueche-l3", "practice_mistake", "Brüche rechnen", "mathematics", "2026-11-19T09:30:00+00:00"),
        ("noah-c1", "teacher_help", "", "math", "2026-11-18T10:00:00+00:00"),
    ],
    "sara": [
        (f"sara-c{index}", "conversation", "", "german" if index % 2 else "math", f"2026-11-25T{index - 42:02d}:00:00+00:00")
        for index in range(59, 54, -1)
    ],
}

#: The history's first twenty: (id, type, when). Below twenty, all of it.
HISTORY = {
    "lena": [(item[0], item[1], item[4]) for item in RECENT["lena"]],
    "jonas": [(item[0], item[1], item[4]) for item in RECENT["jonas"]],
    "mia": [(item[0], item[1], item[4]) for item in RECENT["mia"]],
    "noah": [(item[0], item[1], item[4]) for item in RECENT["noah"]],
    "sara": [
        (
            f"sara-c{index}",
            "conversation",
            f"2026-11-25T{index - 42:02d}:00:00+00:00"
            if index >= 42
            else f"2026-11-24T{index - 18:02d}:00:00+00:00",
        )
        for index in range(59, 39, -1)
    ],
}


@pytest.fixture
def parent_client(fake_table, monkeypatch: pytest.MonkeyPatch):
    def client(student: typical.Student) -> TestClient:
        typical.seed(fake_table, student)
        fake_evidence.install(monkeypatch, typical.evidence(student))
        monkeypatch.setattr(
            user_repo,
            "get_user",
            lambda user_id, **_k: {
                "user_id": user_id,
                "role": "student",
                "account_status": "active",
                "name": user_id,
            },
        )
        reports = [dict(report, parent_id="parent-693") for report in student.reports]
        monkeypatch.setattr(
            parents.report_repo, "list_reports_for_parent", lambda *_a, **_k: {"Items": reports}
        )
        app = FastAPI()
        app.include_router(parents.router, prefix="/parents")
        app.add_middleware(RequestLocaleMiddleware)
        install_actor_overrides(app, {"sub": "parent-693", "role": "parent"})
        return TestClient(app)

    yield client
    locale_service.set_request_locale(None)


@pytest.mark.parametrize("student", typical.STUDENTS, ids=lambda student: student.key)
def test_the_parent_dashboard(parent_client, student: typical.Student) -> None:
    response = parent_client(student).get(f"/parents/me/children/{student.id}/summary")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body["questionsAskedThisWeek"],
        body["aiResolvedThisWeek"],
        body["teacherHelpRequestsThisWeek"],
        body["practiceLessonsCompletedThisWeek"],
    ) == DASHBOARD[student.key]
    assert [
        (item["id"], item["type"], item["summary"], item["subject"], item["createdAt"])
        for item in body["recentActivity"]
    ] == RECENT[student.key]


@pytest.mark.parametrize("student", typical.STUDENTS, ids=lambda student: student.key)
def test_the_parent_history(parent_client, student: typical.Student) -> None:
    response = parent_client(student).get(f"/parents/me/children/{student.id}/history")

    assert response.status_code == 200, response.text
    assert [
        (item["id"], item["type"], item["createdAt"]) for item in response.json()["items"]
    ] == HISTORY[student.key]


def test_the_history_takes_the_newest_of_every_source_up_to_its_limit(parent_client) -> None:
    response = parent_client(typical.NOAH).get(
        f"/parents/me/children/{typical.NOAH.id}/history?limit=2"
    )

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == ["report-noah-2026-11-16", "noah-l1"]


@pytest.mark.parametrize("locale", ["de", "en"])
def test_the_parent_reads_the_titles_in_the_language_of_the_request(parent_client, locale: str) -> None:
    client = parent_client(typical.NOAH)
    headers = {"Accept-Language": locale}

    summary = client.get(f"/parents/me/children/{typical.NOAH.id}/summary", headers=headers)
    history = client.get(f"/parents/me/children/{typical.NOAH.id}/history", headers=headers)

    expected = [
        message_catalog.text(key, locale)
        for key in (
            "activity.weekly_report_available",
            "activity.practice_lesson_completed",
            "activity.practice_mistake_logged",
            "activity.teacher_help_requested",
        )
    ]
    assert [item["title"] for item in summary.json()["recentActivity"]] == expected
    assert [item["title"] for item in history.json()["items"]] == expected
