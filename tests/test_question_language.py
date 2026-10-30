"""The answer comes back in the language the question was asked in (#172)."""

from __future__ import annotations

import pytest

from stoa.services import question_language


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("Wie löse ich die Gleichung auf dem Foto?", "de"),
        ("Wie kürze ich Brüche?", "de"),
        ("Warum bleibt der Nenner gleich?", "de"),
        ("Was ist eine Ableitung? Kannst du mir das erklären?", "de"),
        ("How do I solve the equation in the photo?", "en"),
        ("Why does the denominator stay the same?", "en"),
        ("Comment résoudre l'équation sur la photo ?", "fr"),
        ("Pourquoi le dénominateur reste le même ?", "fr"),
        ("Come si risolve questa equazione?", "it"),
        ("Perché il denominatore resta uguale?", "it"),
    ],
)
def test_a_question_is_answered_in_the_language_it_is_written_in(
    question: str, language: str
) -> None:
    assert question_language.detect(question) == language


@pytest.mark.parametrize("question", ["3x + 5 = 20", "ok", "?", "", None, "3/4 + 1/8"])
def test_a_question_without_words_of_any_language_is_not_recognised(question) -> None:
    assert question_language.detect(question) is None


def test_a_tie_between_two_languages_is_not_recognised() -> None:
    assert question_language.detect("the der") is None


def test_words_two_languages_share_do_not_count() -> None:
    # "la" is French and Italian, "il" Italian and French, "du" French and
    # German: none of them may tip the question one way.
    assert question_language.detect("la il du des da per non tu") is None


def _history(*messages: tuple[str, str]) -> list[dict[str, object]]:
    return [{"role": role, "content": content} for role, content in messages]


def test_the_question_wins_over_the_display_language() -> None:
    assert (
        question_language.answer_language(
            "Wie löse ich die Gleichung auf dem Foto?", [], fallback="en"
        )
        == "de"
    )


def test_a_question_that_says_nothing_keeps_the_language_of_the_conversation() -> None:
    history = _history(
        ("student", "Wie kürze ich Brüche?"),
        ("assistant", "1. Step one, in whatever language the answer came back"),
        ("student", "3/4"),
    )

    assert question_language.answer_language("ok", history, fallback="en") == "de"


def test_the_newest_recognised_student_message_counts() -> None:
    history = _history(
        ("student", "Wie kürze ich Brüche?"),
        ("student", "Why does the denominator stay the same?"),
    )

    assert question_language.answer_language("ok", history, fallback="fr") == "en"


def test_the_assistant_does_not_decide_the_language() -> None:
    history = _history(("assistant", "Comment résoudre l'équation ? Pourquoi ?"))

    assert question_language.answer_language("3x = 15", history, fallback="it") == "it"


def test_nothing_recognised_falls_back_to_the_display_language() -> None:
    assert question_language.answer_language("3x + 5 = 20", [], fallback="it") == "it"
