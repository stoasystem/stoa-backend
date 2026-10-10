"""Timeline labels on the student's and the parent's pages (#124).

`Teacher help requested` / `Question asked` / `AI conversation` and the rest
were English literals in the response, shown inside pages the client draws in
the reader's language. They are labels this backend writes, not anything a
student or a teacher wrote, so they follow the reader.
"""

from __future__ import annotations

from typing import Any

from stoa.routers import parents
from stoa.services import locale_service, message_catalog


def _in(locale: str, build) -> Any:
    locale_service.set_request_locale(locale)
    try:
        return build()
    finally:
        locale_service.set_request_locale(None)


def _question(status: str) -> dict[str, Any]:
    return {
        "question_id": "question-1",
        "status": status,
        "created_at": "2026-10-01T09:00:00+00:00",
        "summary": "Bitte hilf mir beim Dividieren.",
        "subject": "mathematics",
    }


def test_every_timeline_label_is_written_in_the_reader_s_language() -> None:
    """Every label in the set, in every language, against the catalog.

    One label at a time would leave the others free to stay English, which is
    the state this found: the escalated branch was named and its sibling
    branch in the same expression was not.
    """
    cases = {
        "activity.question_answered": lambda: parents._question_activity(
            _question("ai_answered")
        ).title,
        "activity.question_asked": lambda: parents._question_activity(
            _question("pending")
        ).title,
        "activity.teacher_help_requested": lambda: parents._question_activity(
            _question("escalated")
        ).title,
        "activity.ai_conversation": lambda: parents._conversation_activity(
            {"conversation_id": "c1", "created_at": "2026-10-01T09:00:00+00:00"}
        ).title,
        "activity.practice_lesson_completed": lambda: parents._practice_activity(
            {"lesson_id": "l1", "completed_at": "2026-10-01T09:00:00+00:00"}, "practice"
        ).title,
        "activity.practice_mistake_logged": lambda: parents._practice_activity(
            {"challenge_id": "c1", "created_at": "2026-10-01T09:00:00+00:00"}, "mistake"
        ).title,
    }

    produced = {
        locale: {key: _in(locale, build) for key, build in cases.items()}
        for locale in locale_service.SUPPORTED_LOCALES
    }

    assert produced == {
        locale: {key: message_catalog.TEXT[key][locale] for key in cases}
        for locale in locale_service.SUPPORTED_LOCALES
    }


def test_the_labels_are_not_all_the_same_word() -> None:
    """Negative control: six branches, six labels, in each language."""
    for locale in locale_service.SUPPORTED_LOCALES:
        titles = {
            _in(locale, lambda: parents._question_activity(_question("ai_answered")).title),
            _in(locale, lambda: parents._question_activity(_question("pending")).title),
            _in(locale, lambda: parents._question_activity(_question("escalated")).title),
            _in(
                locale,
                lambda: parents._conversation_activity(
                    {"conversation_id": "c1", "created_at": "2026-10-01T09:00:00+00:00"}
                ).title,
            ),
        }
        assert len(titles) == 4, (locale, titles)


def test_a_conversation_that_was_escalated_says_so() -> None:
    """And the escalated branch is a different label from the plain one."""
    for locale in locale_service.SUPPORTED_LOCALES:
        escalated = _in(
            locale,
            lambda: parents._conversation_activity(
                {
                    "conversation_id": "c1",
                    "created_at": "2026-10-01T09:00:00+00:00",
                    "escalated": True,
                }
            ).title,
        )
        assert escalated == message_catalog.TEXT["activity.teacher_help_requested"][locale]
