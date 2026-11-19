"""The prep table of a help request: what the student asked, sent and touched (#517).

A teacher opening a help request reads, without any model in between: the
student's first question, their last question before asking for a teacher,
every file they sent, and the stars the conversation's Ask answers named. The
rules are `teacher_help_prep`'s; the detail route hands them over.

Rows, dispatch and the authorization facts are real, over the shared table
double (see test_chat_help_request_lifecycle.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from fakes.learning_session import seed_message

from stoa.db.repositories import asked_knowledge_repo
from stoa.models.attachment import AttachmentStatus, AttachmentSummary
from stoa.routers import teachers
from stoa.services import learning_session, teacher_help_prep
from test_chat_help_request_lifecycle import CONV, CREATED, REQUEST, STUDENT, TEACHER, _client, _dispatch_to
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

BEFORE = "2026-09-28T11:40:00+00:00"
LATER = "2026-09-28T11:50:00+00:00"
AFTER = "2026-09-28T12:10:00+00:00"


def _message(
    message_id: str, role: str, created_at: str, content: str = "", *attachments: str
) -> learning_session.Message:
    return learning_session.Message(
        id=message_id,
        conversation_id=CONV,
        student_id=STUDENT,
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=created_at,
        attachment_ids=tuple(attachments),
    )


# ── the rules ───────────────────────────────────────────────────────────────


def test_the_first_and_the_last_question_before_asking_for_a_teacher() -> None:
    messages = [
        _message("m1", "student", BEFORE, "Wie kürze ich 12/18?"),
        _message("m2", "assistant", BEFORE, "Teile durch den ggT."),
        _message("m3", "student", LATER, "Und warum ist der ggT 6?"),
        _message("m4", "system", CREATED, "Teacher help requested"),
        # Sent after asking for a teacher: not the last question.
        _message("m5", "student", AFTER, "Hallo?"),
    ]

    asked = teacher_help_prep.questions(messages, asked_at=CREATED)

    assert asked.first is not None and asked.first.id == "m1"
    assert asked.last is not None and asked.last.id == "m3"


def test_one_question_is_shown_once() -> None:
    messages = [
        _message("m1", "student", BEFORE, "Wie kürze ich 12/18?"),
        _message("m2", "assistant", BEFORE, "Teile durch den ggT."),
        _message("m3", "student", AFTER, "Hallo?"),
    ]

    asked = teacher_help_prep.questions(messages, asked_at=CREATED)

    assert asked.first is not None and asked.first.id == "m1"
    assert asked.last is None


def test_a_photo_alone_is_a_question_and_an_empty_message_is_not() -> None:
    messages = [
        _message("m1", "student", BEFORE, "   "),
        _message("m2", "student", BEFORE, "", "att-1"),
        _message("m3", "student", LATER, "Und jetzt?"),
    ]

    asked = teacher_help_prep.questions(messages, asked_at=CREATED)

    assert asked.first is not None and asked.first.id == "m2"
    assert asked.last is not None and asked.last.id == "m3"


def test_without_a_request_time_every_question_counts() -> None:
    messages = [
        _message("m1", "student", BEFORE, "Erste"),
        _message("m2", "student", AFTER, "Letzte"),
    ]

    asked = teacher_help_prep.questions(messages, asked_at=None)

    assert asked.last is not None and asked.last.id == "m2"


def test_no_question_at_all() -> None:
    asked = teacher_help_prep.questions(
        [_message("m1", "assistant", BEFORE, "Hallo")], asked_at=CREATED
    )

    assert asked == teacher_help_prep.Questions(first=None, last=None)


def test_uploads_are_every_file_the_student_sent_once_in_order() -> None:
    messages = [
        _message("m1", "student", BEFORE, "Aufgabe", "att-1", "att-2"),
        _message("m2", "assistant", BEFORE, "Antwort", "att-x"),
        _message("m3", "student", LATER, "Nochmal", "att-2"),
        _message("m4", "student", AFTER, "Nach dem Hilferuf", "att-3"),
    ]

    assert teacher_help_prep.uploads(messages) == ["att-1", "att-2", "att-3"]


def test_asked_stars_are_the_unit_ids_newest_first_once_each() -> None:
    records = [
        {"knowledge_points": ["Kürzen", "frei geschrieben"], "unit_ids": ["u1"]},
        {"knowledge_points": ["Erweitern", "Kürzen"], "unit_ids": ["u2", "u1"]},
        {"knowledge_points": ["nur frei"], "unit_ids": []},
    ]

    assert teacher_help_prep.asked_star_ids(records) == ["u1", "u2"]


# ── the detail ──────────────────────────────────────────────────────────────

CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 1},
        {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "Erweitern", "order": 2},
    ],
    "lessons": [],
}


def _summary(attachment_id: str) -> AttachmentSummary:
    return AttachmentSummary(
        attachmentId=attachment_id,
        filename=f"{attachment_id}.png",
        mediaType="image/png",
        sizeBytes=1024,
        status=AttachmentStatus.ACTIVE,
        createdAt=datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc),
    )


def _asked(message_id: str, asked_at: str, *points: tuple[str, str | None]) -> dict[str, Any]:
    put = asked_knowledge_repo.record_put(
        conversation_id=CONV,
        message_id=message_id,
        student_id=STUDENT,
        subject="math",
        points=list(points),
        asked_at=asked_at,
    )
    assert put is not None
    return put["Put"]["Item"]


def _say(table: FakeTable, message_id: str, created_at: str, content: str, *attachments: str) -> None:
    seed_message(
        table,
        conversation_id=CONV,
        role="student",
        message_id=message_id,
        student_id=STUDENT,
        content=content,
        created_at=created_at,
        attachment_ids=list(attachments),
    )


@pytest.fixture
def files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        teachers.attachment_service,
        "list_attachment_summaries",
        lambda ids: {value: _summary(value) for value in ids},
    )


def _detail() -> dict[str, Any]:
    response = _client(TEACHER).get(f"/teachers/me/help-requests/{REQUEST}")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_detail_carries_the_prep_table(
    table: FakeTable, files: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _say(table, "m1", BEFORE, "Wie kürze ich 12/18?", "att-1")
    _say(table, "m2", LATER, "Und warum ist der ggT 6?")
    _say(table, "m3", AFTER, "Hallo?", "att-2")
    table.seed(
        _asked("m1", BEFORE, ("Kürzen", "u1"), ("ggT", None)),
        _asked("m2", LATER, ("Erweitern", "u2"), ("Kürzen", "u1"), ("Primzahlen", None)),
    )
    fake_evidence.install(
        monkeypatch, fake_evidence.evidence(STUDENT, catalog=CATALOG, exercises={})
    )
    _dispatch_to(table, TEACHER)

    detail = _detail()

    assert detail["firstQuestion"] == {
        "messageId": "m1",
        "content": "Wie kürze ich 12/18?",
        "createdAt": BEFORE,
        "attachments": [_summary("att-1").model_dump(mode="json", by_alias=True)],
    }
    assert detail["lastQuestion"]["messageId"] == "m2"
    assert detail["lastQuestion"]["attachments"] == []
    assert [item["attachmentId"] for item in detail["uploads"]] == ["att-1", "att-2"]
    assert detail["askedStars"] == [
        {"unitId": "u2", "title": "Erweitern"},
        {"unitId": "u1", "title": "Kürzen"},
    ]
    # The names the model wrote freely stay where they were.
    assert "Primzahlen" in detail["weakTopics"]
    # The whole conversation is still there for the folded view.
    assert [message["id"] for message in detail["messages"] if message["role"] == "student"] == [
        "m1",
        "m2",
        "m3",
    ]


def test_a_star_the_catalog_no_longer_has_is_left_out(
    table: FakeTable, files: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _say(table, "m1", BEFORE, "Frage")
    table.seed(_asked("m1", BEFORE, ("Kürzen", "u1"), ("Alt", "u-gone")))
    fake_evidence.install(
        monkeypatch, fake_evidence.evidence(STUDENT, catalog=CATALOG, exercises={})
    )
    _dispatch_to(table, TEACHER)

    detail = _detail()

    assert detail["askedStars"] == [{"unitId": "u1", "title": "Kürzen"}]
    assert detail["lastQuestion"] is None


def test_a_conversation_without_questions_has_an_empty_table(table: FakeTable) -> None:
    _dispatch_to(table, TEACHER)

    detail = _detail()

    assert detail["firstQuestion"] is None
    assert detail["lastQuestion"] is None
    assert detail["uploads"] == []
    assert detail["askedStars"] == []


def test_the_request_opens_without_stars_when_the_records_cannot_be_read(
    table: FakeTable, files: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("table unavailable")

    _say(table, "m1", BEFORE, "Frage")
    monkeypatch.setattr(asked_knowledge_repo, "list_for_conversation", unavailable)
    _dispatch_to(table, TEACHER)

    detail = _detail()

    assert detail["askedStars"] == []
    assert detail["weakTopics"] == []
    assert detail["firstQuestion"]["messageId"] == "m1"
