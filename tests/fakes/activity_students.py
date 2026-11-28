"""Five typical students, made up, for what a student did in a week (#693).

There are no real students in production yet, so these stand in for them: each
is the shape one rule of `student_activity` is about. The week they are read
in is the Zurich week of `NOW` (Thursday 26 November 2026): Monday 23 November
00:00 Zurich, which is Sunday 22 November 23:00 UTC, to the Monday after.

- `lena`: one conversation with three new questions and two follow-ups.
- `jonas`: a request a teacher is on, one withdrawn, one expired; and a new
  question this week in last week's conversation whose request was resolved.
- `mia`: answers at Monday 00:30 Zurich, still Sunday in UTC; and the Sunday
  before, which is last week.
- `noah`: only last week's things, and last week's report.
- `sara`: sixty conversations in one week, the two oldest asking a teacher.

`seed(table, student)` plants the sessions, answers and requests the way their
modules write them; `evidence(student)` is their practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from fakes.help_requests import seed_request
from fakes.learning_session import seed_conversation, seed_message
from stoa.services import student_evidence

NOW = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)

#: The knowledge points the students' wrong answers name.
CATALOG = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "brueche", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "brueche-u2", "subjectId": "math", "topicId": "brueche", "title": "Brüche rechnen", "order": 0}
    ],
    "lessons": [
        {"id": "brueche-l3", "unitId": "brueche-u2", "topicId": "brueche", "subjectId": "math"}
    ],
}


@dataclass(frozen=True)
class Conversation:
    id: str
    subject: str
    started_at: str
    #: (written at, `answer` or `followUp`) per assistant answer.
    answers: tuple[tuple[str, str], ...] = ()
    #: (state, asked at) of its help request, if it has one.
    request: tuple[str, str] | None = None


@dataclass(frozen=True)
class Student:
    key: str
    conversations: tuple[Conversation, ...] = ()
    progress: tuple[dict[str, Any], ...] = ()
    attempts: tuple[dict[str, Any], ...] = ()
    #: The parent's weekly reports of this child, as stored.
    reports: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        return f"student-{self.key}"


def _lesson(lesson_id: str, completed_at: str) -> dict[str, Any]:
    return {
        "lesson_id": lesson_id,
        "subject_id": "math",
        "lesson_title": f"Lektion {lesson_id}",
        "status": "completed",
        "completed_at": completed_at,
    }


def _mistake(challenge_id: str, created_at: str, *, known: bool = True) -> dict[str, Any]:
    if known:
        return {
            "challenge_id": challenge_id,
            "subject_id": "mathematics",
            "topic_id": "brueche",
            "unit_id": "brueche-u2",
            "lesson_id": "brueche-l3",
            "created_at": created_at,
        }
    # A knowledge point the curriculum does not know: named by nothing.
    return {
        "challenge_id": challenge_id,
        "subject_id": "mathematics",
        "topic_id": "kopfrechnen-raw-id",
        "created_at": created_at,
    }


LENA = Student(
    "lena",
    conversations=(
        Conversation(
            "lena-c1",
            "math",
            "2026-11-24T16:00:00+00:00",
            answers=(
                ("2026-11-24T16:01:00+00:00", "answer"),
                ("2026-11-24T16:03:00+00:00", "followUp"),
                ("2026-11-24T16:05:00+00:00", "answer"),
                ("2026-11-24T16:07:00+00:00", "followUp"),
                ("2026-11-24T16:10:00+00:00", "answer"),
            ),
        ),
    ),
    progress=(_lesson("lena-l1", "2026-11-25T17:00:00+00:00"),),
    attempts=(
        _mistake("lena-e1", "2026-11-25T16:30:00+00:00"),
        _mistake("lena-e2", "2026-11-25T16:20:00+00:00", known=False),
    ),
)

JONAS = Student(
    "jonas",
    conversations=(
        # Last week's, its request resolved last week; a new question this week.
        Conversation(
            "jonas-c0",
            "math",
            "2026-11-20T10:00:00+00:00",
            answers=(
                ("2026-11-20T10:01:00+00:00", "answer"),
                ("2026-11-23T09:00:00+00:00", "answer"),
            ),
            request=("resolved", "2026-11-20T10:10:00+00:00"),
        ),
        Conversation(
            "jonas-c1",
            "math",
            "2026-11-23T15:00:00+00:00",
            answers=(("2026-11-23T15:01:00+00:00", "answer"),),
            request=("in_progress", "2026-11-23T15:10:00+00:00"),
        ),
        Conversation(
            "jonas-c2",
            "physics",
            "2026-11-24T15:00:00+00:00",
            answers=(("2026-11-24T15:01:00+00:00", "answer"),),
            request=("withdrawn", "2026-11-24T15:05:00+00:00"),
        ),
        Conversation(
            "jonas-c3",
            "math",
            "2026-11-25T15:00:00+00:00",
            answers=(
                ("2026-11-25T15:01:00+00:00", "answer"),
                ("2026-11-25T15:04:00+00:00", "followUp"),
            ),
            request=("expired", "2026-11-25T15:06:00+00:00"),
        ),
    ),
)

MIA = Student(
    "mia",
    conversations=(
        # Sunday 23:30 Zurich: last week.
        Conversation(
            "mia-c0",
            "math",
            "2026-11-22T22:30:00+00:00",
            answers=(("2026-11-22T22:31:00+00:00", "answer"),),
        ),
        # Monday 00:29 Zurich, Sunday 23:29 UTC: this week.
        Conversation(
            "mia-c1",
            "math",
            "2026-11-22T23:29:00+00:00",
            answers=(("2026-11-22T23:30:00+00:00", "answer"),),
        ),
    ),
    progress=(
        _lesson("mia-l0", "2026-11-22T22:40:00+00:00"),
        _lesson("mia-l1", "2026-11-22T23:30:00+00:00"),
    ),
)

NOAH = Student(
    "noah",
    conversations=(
        Conversation(
            "noah-c1",
            "math",
            "2026-11-18T10:00:00+00:00",
            answers=(
                ("2026-11-18T10:01:00+00:00", "answer"),
                ("2026-11-18T10:05:00+00:00", "answer"),
            ),
            request=("resolved", "2026-11-18T10:20:00+00:00"),
        ),
    ),
    progress=(_lesson("noah-l1", "2026-11-19T10:00:00+00:00"),),
    attempts=(_mistake("noah-e1", "2026-11-19T09:30:00+00:00"),),
    reports=(
        {
            "report_id": "report-noah-2026-11-16",
            "student_id": "student-noah",
            "week_start": "2026-11-16",
            "status": "email_sent",
            "summary": "Eine ruhige Woche.",
            "created_at": "2026-11-23T06:00:00+00:00",
        },
    ),
)


def _busy_week() -> tuple[Conversation, ...]:
    start = datetime(2026, 11, 23, 6, 0, tzinfo=UTC)
    conversations = []
    for index in range(60):
        started = start + timedelta(hours=index)
        request = None
        if index == 0:
            request = ("resolved", (started + timedelta(minutes=10)).isoformat())
        elif index == 1:
            request = ("in_progress", (started + timedelta(minutes=10)).isoformat())
        conversations.append(
            Conversation(
                f"sara-c{index:02d}",
                "math" if index % 2 == 0 else "german",
                started.isoformat(),
                answers=(((started + timedelta(minutes=1)).isoformat(), "answer"),),
                request=request,
            )
        )
    return tuple(conversations)


SARA = Student("sara", conversations=_busy_week())

STUDENTS = (LENA, JONAS, MIA, NOAH, SARA)


def seed(table: FakeTable, student: Student) -> None:
    """Plant the student's sessions, their messages and their requests."""
    for conversation in student.conversations:
        seed_conversation(
            table,
            conversation_id=conversation.id,
            student_id=student.id,
            subject=conversation.subject,
            now=conversation.started_at,
        )
        for number, (written_at, kind) in enumerate(conversation.answers):
            asked_at = (datetime.fromisoformat(written_at) - timedelta(seconds=30)).isoformat()
            seed_message(
                table,
                conversation_id=conversation.id,
                role="student",
                message_id=f"{conversation.id}-q{number}",
                student_id=student.id,
                content="Bitte hilf mir.",
                created_at=asked_at,
            )
            seed_message(
                table,
                conversation_id=conversation.id,
                role="assistant",
                message_id=f"{conversation.id}-a{number}",
                student_id=student.id,
                content="So geht es.",
                created_at=written_at,
                structured={"kind": kind, "answer": "So geht es."},
            )
        if conversation.request is not None:
            status, asked_at = conversation.request
            seed_request(
                table,
                conversation_id=conversation.id,
                student_id=student.id,
                status=status,
                asked_at=asked_at,
                subject=conversation.subject,
            )


def evidence(student: Student) -> student_evidence.StudentEvidence:
    """The student's practice, read at `NOW`."""
    return fake_evidence.evidence(
        student.id,
        catalog=CATALOG,
        progress=student.progress,
        attempts=student.attempts,
        now=NOW,
    )
