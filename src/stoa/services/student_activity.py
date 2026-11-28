"""What a student did in a stretch of time: one place, one set of rules (#633, #693).

The parent's dashboard, the parent's history and the learning profile's totals
(#695) ask this module and nothing else; the weekly report (#694) is to follow.
It keeps no copy of anything: it puts together what the modules that own each
piece read.

- **A stretch of time** is a `Period`, `[start, end)` with time zones. A week
  is the Zurich week (`zurich_week`: Monday 00:00 Europe/Zurich to the next,
  `weekly_counter.zurich_week`, so it turns over the moment the allowance
  does); `last_days` is the last N days to a moment. The history is no
  stretch: it is the most recent N entries (`recent`).
- **A new question** is an Ask answer that answered one
  (`learning_session.Answer.new_question`: `structured.kind == "answer"`),
  counted at the moment it was written. A follow-up is not one; one session
  can hold several.
- **Asked a teacher** is a help request that holds a case of the week
  (`help_requests.holds_case`: pending, in progress or resolved), counted at
  the moment it was asked. A withdrawn or expired one is not; a session has
  at most one.
- **AI resolved** is a new question in the stretch whose session has no help
  request holding a case.
- **Lessons finished and wrong answers** are `student_evidence`'s
  (`completions_between`, `mistakes_between`).
- Question rows of the retired flow (`QUESTION#…/META`, written by nothing
  now) are no source.

The numbers of a stretch read all of it, without a cap. Entries carry titles
from the message catalog in the language the caller passes, and a knowledge
point by the name `curriculum_names` gives it, or none - never its stored id.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from stoa.db.repositories import weekly_counter
from stoa.services import (
    curriculum_names,
    curriculum_service,
    help_requests,
    learning_session,
    message_catalog,
    student_evidence,
)


@dataclass(frozen=True, slots=True)
class Period:
    """A stretch of time, `[start, end)`; both ends carry a time zone."""

    start: datetime
    end: datetime

    def holds(self, raw: object) -> bool:
        """Whether a stored moment falls in the stretch; one that cannot be read does not."""
        moment = _moment(raw)
        return moment is not None and self.start <= moment < self.end


def zurich_week(moment: datetime) -> Period:
    """The Zurich week `moment` falls in: the allowance's week."""
    week = weekly_counter.zurich_week(moment)
    return Period(week.window_start, week.window_end)


def last_days(days: int, now: datetime) -> Period:
    """The `days` days up to `now`."""
    return Period(now - timedelta(days=days), now)


@dataclass(frozen=True, slots=True)
class SubjectCounts:
    """The Ask numbers of one subject."""

    new_questions: int = 0
    ai_resolved: int = 0
    teacher_help: int = 0


@dataclass(frozen=True, slots=True)
class Counts:
    """What a student did in one stretch, in numbers."""

    new_questions: int
    ai_resolved: int
    teacher_help: int
    lessons_completed: int
    mistakes: int
    #: The Ask numbers per subject, under its canonical id
    #: (`curriculum_service.counted_subject`).
    by_subject: Mapping[str, SubjectCounts] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Activity:
    """One entry of what a student did, as a reader is shown it."""

    id: str
    #: `conversation`, `teacher_help`, `practice` or `practice_mistake`.
    type: str
    title: str
    summary: str
    subject: str | None
    #: When it happened, as stored.
    created_at: str


def counts(
    student_id: str, period: Period, *, evidence: student_evidence.StudentEvidence
) -> Counts:
    """The student's numbers for `period`, every row of it read."""
    sessions = learning_session.between(student_id, period.start, period.end)
    requests = _holding_requests(student_id)
    asked = [request for request in requests.values() if period.holds(help_requests.asked_at(request))]

    subjects: dict[str, list[int]] = {}

    def tally(subject: object, slot: int) -> None:
        subjects.setdefault(curriculum_service.counted_subject(subject), [0, 0, 0])[slot] += 1

    new_questions = ai_resolved = 0
    for answer in sessions.answers:
        if not answer.new_question:
            continue
        new_questions += 1
        tally(answer.subject, 0)
        if answer.conversation_id not in requests:
            ai_resolved += 1
            tally(answer.subject, 1)
    for request in asked:
        tally(request.get("subject"), 2)

    return Counts(
        new_questions=new_questions,
        ai_resolved=ai_resolved,
        teacher_help=len(asked),
        lessons_completed=len(evidence.completions_between(period.start, period.end)),
        mistakes=len(evidence.mistakes_between(period.start, period.end)),
        by_subject={
            subject: SubjectCounts(*numbers) for subject, numbers in sorted(subjects.items())
        },
    )


def recent(
    student_id: str,
    *,
    limit: int,
    evidence: student_evidence.StudentEvidence,
    locale: str,
) -> list[Activity]:
    """The student's `limit` most recent entries, newest first, every source mixed.

    A session is one entry, at the moment it was started; the `limit` newest
    sessions are all that can be among them, so no more are read.
    """
    sessions = learning_session.list_for_student(student_id, limit=limit).items
    entries = _entries(
        sessions,
        evidence.completions,
        evidence.mistakes,
        requests=_holding_requests(student_id),
        evidence=evidence,
        locale=locale,
    )
    return newest_first(entries, limit)


def activities(
    student_id: str,
    period: Period,
    *,
    evidence: student_evidence.StudentEvidence,
    locale: str,
) -> list[Activity]:
    """Every entry of `period`, newest first: the sessions started in it, the
    lessons finished and the wrong answers given."""
    sessions = learning_session.between(student_id, period.start, period.end).records
    entries = _entries(
        sessions,
        evidence.completions_between(period.start, period.end),
        evidence.mistakes_between(period.start, period.end),
        requests=_holding_requests(student_id),
        evidence=evidence,
        locale=locale,
    )
    return newest_first(entries)


def newest_first(entries: Iterable[Activity], limit: int | None = None) -> list[Activity]:
    """Entries newest first, then by id; the first `limit` of them when given.

    For a caller that mixes in entries of its own (a parent's weekly reports).
    """
    never = datetime.min.replace(tzinfo=UTC)
    ordered = sorted(
        entries,
        key=lambda entry: (_moment(entry.created_at) or never, entry.id),
        reverse=True,
    )
    return ordered if limit is None else ordered[:limit]


def _holding_requests(student_id: str) -> dict[str, dict[str, Any]]:
    """The student's help requests that hold a case, by session id."""
    return {
        conversation_id: request
        for conversation_id, request in help_requests.for_student(student_id).items()
        if help_requests.holds_case(request)
    }


def _entries(
    sessions: Iterable[Mapping[str, Any]],
    completions: Iterable[student_evidence.Completion],
    mistakes: Iterable[Mapping[str, Any]],
    *,
    requests: Mapping[str, Mapping[str, Any]],
    evidence: student_evidence.StudentEvidence,
    locale: str,
) -> list[Activity]:
    content = evidence.content
    names = curriculum_names.for_reader(locale, catalog=content.catalog, rows=content.named_rows)
    entries = [
        entry for session in sessions if (entry := _session(session, requests, locale)) is not None
    ]
    entries.extend(
        entry for lesson in completions if (entry := _lesson(lesson, locale)) is not None
    )
    entries.extend(
        entry for mistake in mistakes if (entry := _mistake(mistake, names, locale)) is not None
    )
    return entries


def _session(
    session: Mapping[str, Any], requests: Mapping[str, Mapping[str, Any]], locale: str
) -> Activity | None:
    created_at = _text(session.get("created_at"))
    conversation_id = _text(session.get("conversation_id"))
    if not created_at or not conversation_id or _moment(created_at) is None:
        return None
    asked_teacher = conversation_id in requests
    return Activity(
        id=conversation_id,
        type="teacher_help" if asked_teacher else "conversation",
        title=message_catalog.text(
            "activity.teacher_help_requested" if asked_teacher else "activity.ai_conversation",
            locale,
        ),
        # A session's title and preview are the child's own words; a parent
        # reads that there was a conversation, never what was asked (#143).
        summary="",
        subject=_text(session.get("subject")) or None,
        created_at=created_at,
    )


def _lesson(lesson: student_evidence.Completion, locale: str) -> Activity | None:
    if _moment(lesson.completed_at) is None:
        return None
    return Activity(
        id=lesson.lesson_id,
        type="practice",
        title=message_catalog.text("activity.practice_lesson_completed", locale),
        summary=lesson.title or lesson.topic_id or lesson.subject_id,
        subject=lesson.subject_id or None,
        created_at=lesson.completed_at,
    )


def _mistake(
    mistake: Mapping[str, Any], names: curriculum_names.Names, locale: str
) -> Activity | None:
    created_at = _text(mistake.get("created_at") or mistake.get("createdAt"))
    if not created_at or _moment(created_at) is None:
        return None
    return Activity(
        id=_text(mistake.get("lesson_id") or mistake.get("challenge_id"))
        or f"practice_mistake-{created_at}",
        type="practice_mistake",
        title=message_catalog.text("activity.practice_mistake_logged", locale),
        # The knowledge point as the curriculum names it, or nothing; never
        # its stored id (#390, #637).
        summary=names.name(
            names.resolve(
                mistake.get("topic_id"),
                unit_id=mistake.get("unit_id"),
                lesson_id=mistake.get("lesson_id"),
            )
        )
        or "",
        subject=_text(mistake.get("subject_id")) or None,
        created_at=created_at,
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
