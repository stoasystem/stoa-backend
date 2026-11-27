"""What a reader calls each piece of curriculum content (#637, #660).

The one module that names a topic, a unit (star), a lesson or a skill point for
a reader, and that recognises any spelling of one. A request builds it once, in
the reader's language (`for_reader`), from the curriculum it already holds, and
asks it two things:

- `name(content_id)`: what that content is called in the reader's language,
  or None for an id it does not know. The caller decides what to show then.
- `resolve(spelling)`: the unit - or, failing one, the topic - that any
  spelling names: a unit, lesson or topic id, a skill id, a title in any of
  the four languages, or the slug made of one (#390). None when the
  curriculum does not know the spelling.

Where the names come from: a content row carries its own, `titles` - German,
English, French and Italian, the shape `normalized_titles` gives (#661) - with
the German one also in its `title` for the readers that read only that. A
language a row does not name is shown in German. A skill point has no row:
`curriculum_translations.SKILL_TITLES` and `SKILL_TRANSLATIONS` name it, and
`SUBJECT_TRANSLATIONS` a subject until #662. Only this module reads them to
name content; `tests/test_curriculum_names.py` keeps it that way.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from stoa.services import curriculum_translations, knowledge_base_catalog

#: The languages a content row is named in; German is the one every row has.
LOCALES = ("de", "en", "fr", "it")

#: The id a stored content row is named under: its own, the most specific it
#: carries (a lesson row also names its unit and topic).
_OWN_ID_KEYS = ("lesson_id", "unit_id", "topic_id")


def normalized_titles(value: object, *, german: object = None) -> dict[str, str]:
    """A content row's `titles` as it is stored (#661): the name in each of the
    four languages that has one, stripped, in `LOCALES` order.

    `german` is the row's `title`, its German name: where it is given it is the
    German name, whatever `value` says, so `title` and `titles["de"]` never
    disagree. Anything that is not a language's name is left out.
    """
    names: dict[str, str] = {}
    if isinstance(value, Mapping):
        for locale in LOCALES:
            text = value.get(locale)
            if isinstance(text, str) and text.strip():
                names[locale] = text.strip()
    if isinstance(german, str) and german.strip():
        names["de"] = german.strip()
    return {locale: names[locale] for locale in LOCALES if locale in names}


def missing_locales(titles: Mapping[str, str]) -> list[str]:
    """The languages `titles` has no name in, which a reader then sees in German."""
    return [locale for locale in LOCALES if locale not in titles]


def for_reader(
    locale: str,
    *,
    catalog: Mapping[str, Any] | None = None,
    rows: Iterable[Mapping[str, Any]] = (),
) -> Names:
    """The names of the curriculum content in `locale`.

    `catalog` is the student catalog in that language
    (`curriculum_service.list_catalog`, as `student_evidence.Content` holds
    it): its titles are what the reader is shown, and it is what `resolve`
    recognises spellings against. `rows` are stored content rows the caller
    has read itself - the catalog's own builder, or a route that reads one
    topic or a few lessons rather than the whole curriculum - named by the
    names they carry. Of two rows with one id, each language's name is taken
    from the first that has one. Given with `catalog`, the rows also tell
    `resolve` every language's spelling of the content the catalog shows.
    With neither, a content id is named by its translations and a skill point
    by its own name; nothing resolves.
    """
    return Names(locale, catalog or {}, rows)


class Names:
    """The curriculum's names in one reader's language. See the module docstring."""

    def __init__(
        self, locale: str, catalog: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]
    ) -> None:
        self._locale = locale
        self._catalog = catalog
        # A unit's title before a topic's and a lesson's, should two share an id.
        self._shown: dict[str, str] = {}
        for key in ("units", "topics", "lessons"):
            for content_id, row in _by_id(catalog, key).items():
                title = row.get("title")
                if _is_name(title):
                    self._shown.setdefault(content_id, title)
        self._stored: dict[str, dict[str, str]] = {}
        for row in rows:
            content_id = _own_id(row)
            if not content_id:
                continue
            stored = self._stored.setdefault(content_id, {})
            for locale, text in _row_names(row).items():
                stored.setdefault(locale, text)
        self._spellings: _Spellings | None = None

    def name(self, content_id: object) -> str | None:
        """What the topic, unit, lesson or skill point `content_id` is called, or None.

        The catalog's title where the catalog has it, as it is already in the
        reader's language; else the name its row carries in that language;
        else a skill point's or a subject's translation into that language;
        else the row's German name, then a skill point's own name.
        """
        if not isinstance(content_id, str) or not content_id:
            return None
        shown = self._shown.get(content_id)
        if shown is not None:
            return shown
        stored = self._stored.get(content_id, {})
        own = stored.get(self._locale)
        if own is not None:
            return own
        if self._locale != "de":
            translated = _translations(content_id).get(self._locale)
            if translated is not None:
                return translated
        return stored.get("de") or curriculum_translations.SKILL_TITLES.get(content_id)

    def resolve(
        self, *spellings: object, unit_id: object = None, lesson_id: object = None
    ) -> str | None:
        """The unit (or, failing one, the topic) these spellings name, if the catalog knows it.

        `unit_id` and `lesson_id` are the ids a row recorded beside its
        spelling; each counts only when the catalog has it as a unit, or as a
        lesson of one. Then the first spelling the curriculum knows wins.
        """
        known = self._spellings_known()
        if isinstance(unit_id, str) and unit_id in known.units:
            return unit_id
        if isinstance(lesson_id, str) and lesson_id in known.lesson_units:
            return known.lesson_units[lesson_id]
        for spelling in spellings:
            if isinstance(spelling, str) and spelling.strip():
                found = known.aliases.get(slug(spelling))
                if found:
                    return found
        return None

    def _spellings_known(self) -> _Spellings:
        if self._spellings is None:
            self._spellings = _Spellings.of(self._catalog, self._stored)
        return self._spellings


@dataclass
class _Spellings:
    """Every spelling of a knowledge point the catalog knows, and what it means (#390).

    A knowledge point reaches a reader spelled however its row was written: the
    unit id a current attempt carries, the lesson an older one names, the bare
    topic id every practice mistake stores, the title an answer wrote in the
    language it was asked in, or the slug made of that title. Each resolves to
    the current unit; a topic id resolves to its unit when the topic has only
    one, and otherwise stays the topic.
    """

    units: set[str] = field(default_factory=set)
    lesson_units: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def of(
        cls, catalog: Mapping[str, Any], stored: Mapping[str, Mapping[str, str]]
    ) -> _Spellings:
        # Read here, not at import: the curriculum service names its catalog
        # through this module.
        from stoa.services import curriculum_service

        units, topics = _by_id(catalog, "units"), _by_id(catalog, "topics")

        def every_name(content_id: str) -> tuple[str, ...]:
            """What a content row calls itself in any language."""
            return (*stored.get(content_id, {}).values(), *_every_translation(content_id))

        known = cls(
            units=set(units),
            lesson_units={
                str(row["id"]): str(row["unitId"])
                for row in _rows(catalog, "lessons")
                if row.get("id") and str(row.get("unitId") or "") in units
            },
        )
        units_of_topic: dict[str, list[str]] = defaultdict(list)
        for unit_id, row in units.items():
            units_of_topic[str(row.get("topicId") or "")].append(unit_id)
        # The first claim on a spelling wins: a unit's own names before the
        # names of what hangs under it, and those before a topic's.
        for unit_id, row in units.items():
            zap_title = knowledge_base_catalog.ZAP_UNITS.get(unit_id)
            known._claim(unit_id, unit_id, row.get("title"), *every_name(unit_id))
            known._claim(unit_id, zap_title, _without_aside(zap_title))
        for skill_id, unit_id in curriculum_service.skill_unit_ids().items():
            if unit_id in units:
                known._claim(
                    unit_id,
                    skill_id,
                    curriculum_translations.SKILL_TITLES.get(skill_id),
                    *_every_translation(skill_id),
                )
        for row in _rows(catalog, "lessons"):
            lesson_id = str(row.get("id") or "")
            if lesson_id in known.lesson_units:
                known._claim(
                    known.lesson_units[lesson_id],
                    lesson_id,
                    row.get("title"),
                    *every_name(lesson_id),
                )
        for topic_id, row in topics.items():
            under = units_of_topic.get(topic_id, [])
            target = under[0] if len(under) == 1 else topic_id
            known._claim(target, topic_id, row.get("title"), *every_name(topic_id))
        return known

    def _claim(self, target: str, *spellings: object) -> None:
        for spelling in spellings:
            if isinstance(spelling, str) and spelling.strip():
                self.aliases.setdefault(slug(spelling), target)


def _rows(catalog: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    return [row for row in catalog.get(key) or () if isinstance(row, Mapping)]


def _by_id(catalog: Mapping[str, Any], key: str) -> dict[str, Mapping[str, Any]]:
    """The catalog's rows of one kind by id; the last of two with one id wins."""
    return {str(row["id"]): row for row in _rows(catalog, key) if row.get("id")}


def _own_id(row: Mapping[str, Any]) -> str:
    for key in _OWN_ID_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _row_names(row: Mapping[str, Any]) -> dict[str, str]:
    """The names a stored content row carries: its `titles`, and its `title` as
    the German one where `titles` has none (a row written before #661)."""
    names = normalized_titles(row.get("titles"))
    if "de" not in names:
        names = normalized_titles(names, german=row.get("title"))
    return names


def _is_name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _translations(content_id: str) -> Mapping[str, str]:
    """A skill point's or a subject's English, French and Italian names; a
    topic, unit or lesson has its own on its row."""
    return (
        curriculum_translations.SKILL_TRANSLATIONS.get(content_id)
        or curriculum_translations.SUBJECT_TRANSLATIONS.get(content_id)
        or {}
    )


def _every_translation(content_id: str) -> tuple[str, ...]:
    """A skill point's or a subject's translated names: English, French and Italian."""
    return tuple(_translations(content_id).values())


def _without_aside(title: str | None) -> str | None:
    """A ZAP unit's import title without its bracketed aside, as the catalog shows it."""
    if not title:
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", title)


def slug(spelling: str) -> str:
    """A spelling as compared: lowercase, runs of anything else one hyphen.

    The slug older rows were keyed by (the retired memory snapshots, #675,
    and older practice rows), so such a slug resolves like the title it was
    made of. Recommendations still file a name the catalog does not know
    under its slug.
    """
    value = re.sub(r"[^a-z0-9]+", "-", spelling.strip().lower()).strip("-")
    return value or "general"
