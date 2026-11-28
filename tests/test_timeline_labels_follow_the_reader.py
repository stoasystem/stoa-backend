"""Timeline labels on the parent's pages (#124, #693).

`Teacher help requested` / `AI conversation` and the rest were English
literals in the response, shown inside pages the client draws in the reader's
language. They are labels this backend writes, not anything a student or a
teacher wrote, so they follow the reader: the parent's routes pass the
request's language to `student_activity`, which takes every title from the
message catalog in it. The retired flow's question rows are no entries any
more (#693), so their two labels are not among these.
"""

from __future__ import annotations

from stoa.routers import parents
from stoa.services import curriculum_names, locale_service, message_catalog, student_activity, student_evidence

MOMENT = "2026-10-01T09:00:00+00:00"


def _session(locale: str, *, asked_teacher: bool = False) -> str:
    requests = {"c1": {"escalation_status": "pending"}} if asked_teacher else {}
    entry = student_activity._session(
        {"conversation_id": "c1", "created_at": MOMENT}, requests, locale
    )
    assert entry is not None
    return entry.title


def _cases(locale: str) -> dict[str, str]:
    lesson = student_activity._lesson(
        student_evidence.Completion(lesson_id="l1", unit_id="", subject_id="", completed_at=MOMENT),
        locale,
    )
    mistake = student_activity._mistake(
        {"challenge_id": "c1", "created_at": MOMENT}, curriculum_names.for_reader(locale), locale
    )
    report = parents._report_activity({"report_id": "r1", "created_at": MOMENT}, locale)
    assert lesson is not None and mistake is not None and report is not None
    return {
        "activity.teacher_help_requested": _session(locale, asked_teacher=True),
        "activity.ai_conversation": _session(locale),
        "activity.practice_lesson_completed": lesson.title,
        "activity.practice_mistake_logged": mistake.title,
        "activity.weekly_report_available": report.title,
    }


def test_every_timeline_label_is_written_in_the_reader_s_language() -> None:
    """Every label in the set, in every language, against the catalog.

    One label at a time would leave the others free to stay English, which is
    the state #124 found: the escalated branch was named and its sibling
    branch in the same expression was not.
    """
    produced = {locale: _cases(locale) for locale in locale_service.SUPPORTED_LOCALES}

    assert produced == {
        locale: {key: message_catalog.TEXT[key][locale] for key in produced[locale]}
        for locale in locale_service.SUPPORTED_LOCALES
    }


def test_the_labels_are_not_all_the_same_word() -> None:
    """Negative control: five branches, five labels, in each language."""
    for locale in locale_service.SUPPORTED_LOCALES:
        titles = set(_cases(locale).values())
        assert len(titles) == 5, (locale, titles)


def test_a_conversation_that_asked_a_teacher_says_so() -> None:
    """And the branch with a request holding a case is a different label from the plain one."""
    for locale in locale_service.SUPPORTED_LOCALES:
        assert _session(locale, asked_teacher=True) == message_catalog.TEXT[
            "activity.teacher_help_requested"
        ][locale]
        assert _session(locale) != _session(locale, asked_teacher=True)
