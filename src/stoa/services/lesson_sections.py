"""A lesson's explanation cards, in the reader's language (#465).

A lesson may carry `sections`: the cards a student reads before its exercises,
in order. Each card holds an `id`, a German `title` and `body` - the body may
hold LaTeX - and may carry `translations`: for a locale, the card's `title` and
`body` in that language. This is the shape the AI lesson draft writes
(`scripts/ai_lesson_draft.py`, #441):

    [{id: "card-1", title, body, translations: {en|fr|it: {title, body}}}]

A reader sees a card in their locale where it has both a title and a body there,
and in German otherwise. Only `id`, `title` and `body` leave the server; the
stored `translations` do not.

Curriculum authoring checks the shape (`issues`) on every write, so a bad card is
a validation issue in a migration dry run, not a lesson that fails to load.
"""

from __future__ import annotations

from collections.abc import Mapping

from stoa.services.curriculum_issues import Issue, IssueCode
from stoa.services.exercise_localization import LOCALES

#: What every card holds, in German.
CARD_FIELDS = ("id", "title", "body")
#: What a card's translation into one locale holds.
TRANSLATION_FIELDS = ("title", "body")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _complete(value: object, fields: tuple[str, ...]) -> bool:
    return isinstance(value, Mapping) and all(_text(value.get(name)) for name in fields)


def localized(sections: object, locale: str) -> list[dict[str, str]]:
    """The cards as a reader in `locale` sees them, in stored order.

    A stored card that is not whole is left out, so content written before the
    shape was checked cannot stop a student from opening the lesson.
    """
    if not isinstance(sections, list):
        return []
    cards: list[dict[str, str]] = []
    for card in sections:
        if not _complete(card, CARD_FIELDS):
            continue
        translations = card.get("translations")
        shown = translations.get(locale) if isinstance(translations, Mapping) else None
        if not _complete(shown, TRANSLATION_FIELDS):
            shown = card
        cards.append({"id": card["id"].strip(), "title": shown["title"], "body": shown["body"]})
    return cards


def issues(sections: object) -> list[tuple[str, Issue]]:
    """What is wrong with a lesson's `sections`, as (field, issue) pairs."""
    if sections in (None, []):
        return []
    if not isinstance(sections, list):
        return [("sections", Issue.of(IssueCode.SECTIONS_NOT_A_LIST))]
    found: list[tuple[str, Issue]] = []
    seen: set[str] = set()
    for index, card in enumerate(sections):
        field = f"sections[{index}]"
        if not isinstance(card, Mapping):
            found.append((field, Issue.of(IssueCode.SECTION_FIELD_MISSING, fields=", ".join(CARD_FIELDS))))
            continue
        missing = [name for name in CARD_FIELDS if not _text(card.get(name))]
        if missing:
            found.append((field, Issue.of(IssueCode.SECTION_FIELD_MISSING, fields=", ".join(missing))))
        card_id = _text(card.get("id"))
        if card_id and card_id in seen:
            found.append((f"{field}.id", Issue.of(IssueCode.SECTION_ID_REPEATED)))
        seen.add(card_id)
        found.extend(_translation_issues(field, card.get("translations")))
    return found


def _translation_issues(field: str, translations: object) -> list[tuple[str, Issue]]:
    if translations in (None, {}):
        return []
    if not isinstance(translations, Mapping):
        return [(f"{field}.translations", Issue.of(IssueCode.TRANSLATIONS_NOT_A_MAP))]
    found: list[tuple[str, Issue]] = []
    for locale, text in translations.items():
        where = f"{field}.translations.{locale}"
        if locale not in LOCALES:
            found.append((where, Issue.of(IssueCode.TRANSLATION_LOCALE_UNSUPPORTED, language=locale)))
        elif not _complete(text, TRANSLATION_FIELDS):
            found.append((where, Issue.of(IssueCode.SECTION_TRANSLATION_INCOMPLETE)))
    return found
