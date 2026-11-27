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

Where the names come from is the same as before this module (#661 moves them
onto the content rows): a content row's stored German `title`, the English,
French and Italian titles in `curriculum_translations.TITLE_TRANSLATIONS`
(the knowledge base's titles merged in), and `SKILL_TITLES` for a skill point,
which has no row. Only this module reads them to name content;
`tests/test_curriculum_names.py` keeps it that way.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from stoa.services import curriculum_translations, knowledge_base_catalog

#: The id a stored content row is named under: its own, the most specific it
#: carries (a lesson row also names its unit and topic).
_OWN_ID_KEYS = ("lesson_id", "unit_id", "topic_id")


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
    topic or a few lessons rather than the whole curriculum - named by their
    stored titles. With neither, a content id is named by its translations
    and a skill point by its own name; nothing resolves.
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
        self._stored: dict[str, str] = {}
        for row in rows:
            content_id, title = _own_id(row), row.get("title")
            if content_id and _is_name(title):
                self._stored.setdefault(content_id, title)
        self._spellings: _Spellings | None = None

    def name(self, content_id: object) -> str | None:
        """What the topic, unit, lesson or skill point `content_id` is called, or None.

        The catalog's title where the catalog has it, as it is already in the
        reader's language; else the translation into that language; else the
        stored German title, then a skill point's own name.
        """
        if not isinstance(content_id, str) or not content_id:
            return None
        shown = self._shown.get(content_id)
        if shown is not None:
            return shown
        if self._locale != "de":
            translated = curriculum_translations.TITLE_TRANSLATIONS.get(content_id, {}).get(
                self._locale
            )
            if translated is not None:
                return translated
        return self._stored.get(content_id) or curriculum_translations.SKILL_TITLES.get(content_id)

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
                found = known.aliases.get(_slug(spelling))
                if found:
                    return found
        return None

    def _spellings_known(self) -> _Spellings:
        if self._spellings is None:
            self._spellings = _Spellings.of(self._catalog)
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
    def of(cls, catalog: Mapping[str, Any]) -> _Spellings:
        # Read here, not at import: the curriculum service names its catalog
        # through this module.
        from stoa.services import curriculum_service

        units, topics = _by_id(catalog, "units"), _by_id(catalog, "topics")
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
            known._claim(unit_id, unit_id, row.get("title"), *_every_translation(unit_id))
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
                    *_every_translation(lesson_id),
                )
        for topic_id, row in topics.items():
            under = units_of_topic.get(topic_id, [])
            target = under[0] if len(under) == 1 else topic_id
            known._claim(target, topic_id, row.get("title"), *_every_translation(topic_id))
        return known

    def _claim(self, target: str, *spellings: object) -> None:
        for spelling in spellings:
            if isinstance(spelling, str) and spelling.strip():
                self.aliases.setdefault(_slug(spelling), target)


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


def _is_name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _every_translation(content_id: str) -> tuple[str, ...]:
    """A content id's translated titles: English, French and Italian."""
    return tuple(curriculum_translations.TITLE_TRANSLATIONS.get(content_id, {}).values())


def _without_aside(title: str | None) -> str | None:
    """A ZAP unit's import title without its bracketed aside, as the catalog shows it."""
    if not title:
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", title)


def _slug(spelling: str) -> str:
    """A spelling as compared: lowercase, runs of anything else one hyphen.

    The same as `learning_profile_service.normalize_topic_id`, which makes a
    weak topic's id of a name the curriculum does not know.
    """
    value = re.sub(r"[^a-z0-9]+", "-", spelling.strip().lower()).strip("-")
    return value or "general"
