"""The stars an Ask answer may name: the student's map, as the model is shown it.

An answer names knowledge points (#142) and, later, the star the student wants
to go to (#124). Both are chosen by the model from one list and checked against
that same list, so this module is the only place either is decided:

* `for_student` reads the list once, when the question is asked. The caller
  stores it with the rest of the generation context, so the worker checks the
  model's choice against the list the model was shown, not against whatever the
  map says by the time the answer is generated.
* `find` is the whitelist. The model names a star by the short `ref` it was
  shown; anything that is not one of those refs names no star, however much it
  looks like a unit id.

Every star the map draws is on the list, in every subject: a question asked in
the maths conversation may well be about a physics star. A star is drawn when it
has at least one active lesson, the same rule `knowledge_map_service` follows.

The model is shown a short `ref` (`k1`, `k2`, ...) rather than the unit id: the
ids are long slugs, and the whole sky is a few hundred stars sent with every
question, paid for out of the student's own token allowance.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from stoa.services import curriculum_service, knowledge_mastery_service

logger = logging.getLogger(__name__)


class Candidate(TypedDict):
    """One star the model may name."""

    #: What the model is shown and answers with. Stable only within one list.
    ref: str
    unitId: str
    #: In the language the list was read in, which is the answer's language.
    name: str
    subjectId: str
    #: `lit`, `in_progress`, `ready` or `locked`, as the map draws it.
    state: str


def from_catalog(
    catalog: Mapping[str, Any],
    states: Mapping[str, knowledge_mastery_service.UnitMastery],
) -> list[Candidate]:
    """The list from facts already read. Pure; ordered by subject, chapter and unit."""
    topic_order = {
        str(topic.get("id") or ""): int(topic.get("order") or 0)
        for topic in catalog.get("topics") or ()
        if isinstance(topic, Mapping)
    }
    units = [unit for unit in catalog.get("units") or () if isinstance(unit, Mapping)]
    drawn = [
        unit
        for unit in units
        if (judged := states.get(str(unit.get("id") or ""))) is not None
        and judged.lesson_count > 0
        and str(unit.get("id") or "")
    ]
    drawn.sort(
        key=lambda unit: (
            str(unit.get("subjectId") or ""),
            topic_order.get(str(unit.get("topicId") or ""), 0),
            str(unit.get("topicId") or ""),
            int(unit.get("order") or 0),
            str(unit.get("id") or ""),
        )
    )
    return [
        Candidate(
            ref=f"k{index}",
            unitId=str(unit["id"]),
            name=str(unit.get("title") or unit["id"]),
            subjectId=str(unit.get("subjectId") or ""),
            state=states[str(unit["id"])].state.value,
        )
        for index, unit in enumerate(drawn, start=1)
    ]


def for_student(student_id: str, *, locale: str) -> list[Candidate] | None:
    """Every star on this student's map, or None when the map cannot be read.

    None is not an empty map: an answer given without the list cannot have
    matched anything, so nothing it names may be taken for a gap in the
    knowledge base either.
    """
    try:
        catalog = curriculum_service.list_catalog(locale=locale)
        states = knowledge_mastery_service.unit_states(
            student_id, locale=locale, catalog=catalog
        )
        return from_catalog(catalog, states)
    except Exception:  # noqa: BLE001
        # An answer without the list is far better than no answer at all.
        logger.warning("star_map_candidates_unavailable", exc_info=True)
        return None


def stored(value: object) -> list[Candidate] | None:
    """The list as the generation context kept it; None when it kept none.

    Read back from DynamoDB, so every entry is checked: one that is not whole
    is left out rather than trusted.
    """
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    keys = Candidate.__annotations__
    return [
        Candidate(**{key: entry[key] for key in keys})  # type: ignore[typeddict-item]
        for entry in value
        if isinstance(entry, Mapping) and all(isinstance(entry.get(key), str) for key in keys)
    ]


def find(candidates: Sequence[Candidate] | None, ref: object) -> Candidate | None:
    """The star `ref` names, if it is one the model was shown; otherwise None."""
    if not candidates or not isinstance(ref, str):
        return None
    wanted = ref.strip()
    return next((candidate for candidate in candidates if candidate["ref"] == wanted), None)
