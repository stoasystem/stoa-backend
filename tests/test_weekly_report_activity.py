"""The weekly report reads what the student did from `student_activity` (#694).

Its numbers and its entries are the Zurich week's of the Monday the report is
for, every row of it read, in the language the parent stored. The typical
students are #693's (`fakes.activity_students`); the week is theirs: Monday
23 November 2026, 00:00 in Zurich, which is Sunday 23:00 UTC.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from fakes import activity_students as typical
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_conversation, seed_message
from stoa.services import locale_service, message_catalog, report_service, student_activity

PARENT = "parent-694"
#: The Monday the typical students' week starts on, as the job names it.
WEEK_START = "2026-11-23"
#: The same week, as `student_activity` reads it at the students' `NOW`.
WEEK = student_activity.zurich_week(typical.NOW)

#: (questions asked, AI resolved, asked a teacher, lessons, wrong answers):
#: the numbers the parent's dashboard shows for the same week (#693).
METRICS = {
    "lena": (3, 3, 0, 1, 2),
    "jonas": (4, 2, 1, 0, 0),
    "mia": (1, 1, 0, 1, 0),
    "noah": (0, 0, 0, 0, 0),
    "sara": (60, 58, 2, 0, 0),
}

#: The week's entries: (id, type, summary, subject, when), newest first.
ACTIVITIES = {
    "lena": [
        ("lena-l1", "practice", "Lektion lena-l1", "math", "2026-11-25T17:00:00+00:00"),
        ("brueche-l3", "practice_mistake", "Brüche rechnen", "mathematics", "2026-11-25T16:30:00+00:00"),
        # A knowledge point the curriculum does not know is named by nothing.
        ("lena-e2", "practice_mistake", "", "mathematics", "2026-11-25T16:20:00+00:00"),
        ("lena-c1", "conversation", "", "math", "2026-11-24T16:00:00+00:00"),
    ],
    # Last week's session, with this week's new question in it, is no entry
    # of this week; withdrawn and expired requests leave a conversation.
    "jonas": [
        ("jonas-c3", "conversation", "", "math", "2026-11-25T15:00:00+00:00"),
        ("jonas-c2", "conversation", "", "physics", "2026-11-24T15:00:00+00:00"),
        ("jonas-c1", "teacher_help", "", "math", "2026-11-23T15:00:00+00:00"),
    ],
    # Monday 00:30 Zurich, still Sunday in UTC, is this week; 23:30 is not.
    "mia": [
        ("mia-l1", "practice", "Lektion mia-l1", "math", "2026-11-22T23:30:00+00:00"),
        ("mia-c1", "conversation", "", "math", "2026-11-22T23:29:00+00:00"),
    ],
    "noah": [],
}


@pytest.fixture
def report_for(fake_table: FakeTable, monkeypatch: pytest.MonkeyPatch):
    """The report payload of one typical student's week, for a parent who stored `locale`."""

    def build(
        student: typical.Student, *, locale: str = "de", week_start: str = WEEK_START
    ) -> dict[str, Any]:
        typical.seed(fake_table, student)
        fake_evidence.install(monkeypatch, typical.evidence(student))
        monkeypatch.setattr(report_service.locale_service, "stored_locale", lambda _user_id: locale)
        monkeypatch.setattr(
            report_service.user_repo,
            "get_user",
            lambda user_id, **_kwargs: {"user_id": user_id, "name": user_id},
        )
        monkeypatch.setattr(
            report_service,
            "_get_linked_student_profile",
            lambda _parent, student_id: {"user_id": student_id, "name": student_id, "grade": 5},
        )
        return report_service.build_weekly_learning_payload(PARENT, student.id, week_start)

    return build


# ── The week ─────────────────────────────────────────────────────────────────


def test_the_report_s_week_is_the_zurich_week_of_its_monday() -> None:
    assert report_service.report_period(WEEK_START) == WEEK
    assert WEEK.start == datetime(2026, 11, 22, 23, 0, tzinfo=UTC)
    # In summer the week turns over at 22:00 UTC.
    assert report_service.report_period("2026-06-01") == student_activity.Period(
        datetime(2026, 5, 31, 22, 0, tzinfo=UTC), datetime(2026, 6, 7, 22, 0, tzinfo=UTC)
    )
    # The weeks the clocks change in are still Monday to Monday in Zurich.
    assert report_service.report_period("2026-10-19") == student_activity.Period(
        datetime(2026, 10, 18, 22, 0, tzinfo=UTC), datetime(2026, 10, 25, 23, 0, tzinfo=UTC)
    )


def test_an_answer_on_sunday_2330_utc_falls_in_the_new_week(report_for) -> None:
    """Monday 00:30 in Zurich: the new week's, though the UTC day is last week's."""
    new_week = report_for(typical.MIA)

    assert new_week["week"] == {"start": "2026-11-23", "end": "2026-11-29"}
    assert new_week["metrics"]["questionsAsked"] == 1
    assert new_week["metrics"]["practiceLessonsCompleted"] == 1
    assert "2026-11-22T23:30:00+00:00" in [entry["createdAt"] for entry in new_week["activities"]]

    week_before = report_for(typical.MIA, week_start="2026-11-16")

    # The week before holds what was done by Sunday 23:59 Zurich, and no more.
    assert week_before["metrics"]["questionsAsked"] == 1
    assert [(entry["id"], entry["createdAt"]) for entry in week_before["activities"]] == [
        ("mia-l0", "2026-11-22T22:40:00+00:00"),
        ("mia-c0", "2026-11-22T22:30:00+00:00"),
    ]


def test_the_right_answers_the_stars_and_the_ask_records_are_of_the_same_week(
    fake_table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = {
        **typical.CATALOG,
        "rolloutSubjects": ["math"],
    }
    attempts = [
        # Sunday 23:30 UTC: this week's. Sunday 22:30 UTC: last week's.
        {"challenge_id": "in", "correct": True, "unit_id": "brueche-u2", "created_at": "2026-11-22T23:30:00+00:00"},
        {"challenge_id": "out", "correct": True, "unit_id": "brueche-u2", "created_at": "2026-11-22T22:30:00+00:00"},
    ]
    fake_evidence.install(
        monkeypatch,
        fake_evidence.evidence(typical.MIA.id, catalog=catalog, attempts=attempts, now=typical.NOW),
    )
    monkeypatch.setattr(report_service.locale_service, "stored_locale", lambda _user_id: "de")
    monkeypatch.setattr(report_service.user_repo, "get_user", lambda user_id, **_k: {"user_id": user_id})
    monkeypatch.setattr(
        report_service, "_get_linked_student_profile", lambda _parent, student_id: {"user_id": student_id}
    )
    seen: dict[str, Any] = {}

    def asked(student_id: str, *, since: str | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        seen["asked_since"] = since
        return []

    def lit_between(_evidence: Any, start: datetime, end: datetime) -> tuple[str, ...]:
        seen["lit"] = (start, end)
        return ()

    monkeypatch.setattr(report_service.asked_knowledge_repo, "list_for_student", asked)
    monkeypatch.setattr(report_service.knowledge_mastery_service, "lit_between", lit_between)

    payload = report_service.build_weekly_learning_payload(PARENT, typical.MIA.id, WEEK_START)

    assert payload["answeredRight"] == {"onOwn": 1, "afterAskingAi": 0}
    assert seen["lit"] == (WEEK.start, WEEK.end)
    # A moment in UTC, as the records' `created_at` is written, not a date.
    assert seen["asked_since"] == "2026-11-22T23:00:00+00:00"


def test_an_ask_record_of_monday_0030_zurich_is_read_for_the_new_week(
    report_for, fake_table: FakeTable
) -> None:
    for message_id, asked_at in (("in", "2026-11-22T23:30:00+00:00"), ("out", "2026-11-22T22:30:00+00:00")):
        fake_table.seed(
            {
                "PK": "CONV#mia-c1",
                "SK": f"KNOWLEDGE#{message_id}",
                "entity_type": "asked_knowledge_points",
                "student_id": typical.MIA.id,
                "owner_id": typical.MIA.id,
                "conversation_id": "mia-c1",
                "subject": "math",
                "knowledge_points": [f"Bruchrechnen {message_id}"],
                "unit_ids": [],
                "created_at": asked_at,
            }
        )

    payload = report_for(typical.MIA)

    assert payload["weakTopics"] == [{"topic": "Bruchrechnen in", "count": 1}]


# ── The numbers ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("student", typical.STUDENTS, ids=lambda student: student.key)
def test_the_numbers_of_the_report_are_the_week_s(report_for, student: typical.Student) -> None:
    payload = report_for(student)

    metrics = payload["metrics"]
    assert (
        metrics["questionsAsked"],
        metrics["aiResolved"],
        metrics["teacherHelpRequests"],
        metrics["practiceLessonsCompleted"],
        metrics["mistakesLogged"],
    ) == METRICS[student.key]

    # The report row stores the same numbers.
    record = report_service.build_weekly_report_record(
        payload, report_service.build_deterministic_report_fallback(payload)
    )
    assert (
        record["usage_count"],
        record["ai_resolved"],
        record["teacher_resolved"],
        record["practice_lessons_completed"],
        record["mistakes_logged"],
    ) == METRICS[student.key]


def test_a_week_of_sixty_conversations_is_read_to_the_end(report_for) -> None:
    payload = report_for(typical.SARA)

    assert len(payload["activities"]) == 60
    assert payload["sourceCounts"] == {
        "questions": 60,
        "practiceProgress": 0,
        "mistakes": 0,
        "conversations": 60,
    }
    # The two oldest asked a teacher; they are the last two entries.
    assert [(entry["id"], entry["type"]) for entry in payload["activities"][-2:]] == [
        ("sara-c01", "teacher_help"),
        ("sara-c00", "teacher_help"),
    ]


def test_a_question_row_of_the_retired_flow_is_no_source(report_for, fake_table: FakeTable) -> None:
    fake_table.seed(
        {
            "PK": "QUESTION#old",
            "SK": "META",
            "question_id": "old",
            "student_id": typical.NOAH.id,
            "status": "teacher_requested",
            "subject": "math",
            "knowledge_points": ["Brüche"],
            "created_at": "2026-11-24T10:00:00+00:00",
        }
    )

    payload = report_for(typical.NOAH)

    assert set(payload["metrics"].values()) == {0}
    assert payload["activities"] == []
    assert payload["weakTopics"] == []


def test_a_follow_up_and_an_answer_without_a_structure_are_no_new_questions(
    report_for, fake_table: FakeTable
) -> None:
    seed_conversation(
        fake_table,
        conversation_id="noah-c9",
        student_id=typical.NOAH.id,
        subject="math",
        now="2026-11-24T10:00:00+00:00",
    )
    for message_id, structured in (("a1", {"kind": "followUp"}), ("a2", None)):
        seed_message(
            fake_table,
            conversation_id="noah-c9",
            role="assistant",
            message_id=message_id,
            student_id=typical.NOAH.id,
            content="So geht es.",
            created_at="2026-11-24T10:01:00+00:00",
            structured=structured,
        )

    payload = report_for(typical.NOAH)

    assert payload["metrics"]["questionsAsked"] == 0
    assert [entry["id"] for entry in payload["activities"]] == ["noah-c9"]


# ── The entries ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", sorted(ACTIVITIES))
def test_the_entries_of_the_report_are_the_week_s(report_for, key: str) -> None:
    student = next(student for student in typical.STUDENTS if student.key == key)

    payload = report_for(student)

    assert [
        (entry["id"], entry["type"], entry["summary"], entry["subject"], entry["createdAt"])
        for entry in payload["activities"]
    ] == ACTIVITIES[key]


_TITLE_KEYS = (
    "activity.ai_conversation",
    "activity.teacher_help_requested",
    "activity.practice_lesson_completed",
    "activity.practice_mistake_logged",
)


@pytest.mark.parametrize("locale", sorted(locale_service.SUPPORTED_LOCALES))
def test_the_titles_are_in_the_language_the_parent_stored(report_for, locale: str) -> None:
    titles = {
        entry["type"]: entry["title"]
        for student in (typical.JONAS, typical.LENA)
        for entry in report_for(student, locale=locale)["activities"]
    }

    assert titles == {
        "conversation": message_catalog.text("activity.ai_conversation", locale),
        "teacher_help": message_catalog.text("activity.teacher_help_requested", locale),
        "practice": message_catalog.text("activity.practice_lesson_completed", locale),
        "practice_mistake": message_catalog.text("activity.practice_mistake_logged", locale),
    }


@pytest.mark.parametrize("student", [typical.LENA, typical.JONAS], ids=lambda student: student.key)
def test_a_german_speaking_parent_s_report_input_has_no_english_title_and_no_raw_topic_id(
    report_for, student: typical.Student
) -> None:
    payload = report_for(student, locale="de")
    content = report_service.build_deterministic_report_fallback(payload)
    record = report_service.build_weekly_report_record(payload, content)

    model_input = report_service.build_bedrock_report_input(payload)
    artifact = report_service.build_weekly_report_json_artifact(payload, content, record)

    assert model_input["language"] == "de"
    english = {message_catalog.text(key, "en") for key in _TITLE_KEYS} | {
        # What the report wrote itself before (#633).
        "Question answered",
        "Teacher help requested",
        "Practice lesson completed",
        "Practice mistake logged",
        "AI conversation",
    }
    german = {message_catalog.text(key, "de") for key in _TITLE_KEYS}
    assert not english & german
    for shown in (model_input, artifact, payload):
        assert {entry["title"] for entry in shown["activities"]} <= german
        for title in english:
            assert title not in json.dumps(shown, ensure_ascii=False)
        # A wrong answer is named as the curriculum names it, or by nothing:
        # never by the id stored on it (#637). The weak topics are another
        # rule's (`weak_topics`, #632): they keep a spelling the curriculum
        # does not know as it was written.
        entries = json.dumps(shown["activities"], ensure_ascii=False)
        assert "kopfrechnen-raw-id" not in entries
        assert "brueche" not in entries.replace("brueche-l3", "")
    if student is typical.LENA:
        mistakes = [entry for entry in payload["activities"] if entry["type"] == "practice_mistake"]
        assert [(entry["id"], entry["summary"]) for entry in mistakes] == [
            ("brueche-l3", "Brüche rechnen"),
            ("lena-e2", ""),
        ]
