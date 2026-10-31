"""The stars an Ask answer may name: the student's map, as the model is shown it.

An answer names knowledge points (#142) and, later, the star the student wants
to go to (#124). Both are chosen by the model from one list and checked against
that same list, so this module is the only place either is decided:

* `for_student` reads the list once for each attempt at an answer, just before
  the model is asked, and the same list then checks what the model picked. It
  is not stored with the command: a few hundred stars would be most of the
  item, paid for on every write of it.
* `find` is the whitelist. The model names a star by the short `ref` it was
  shown; anything that is not one of those refs names no star, however much it
  looks like a unit id. `find_topic` is the same for a topic (a nebula), which
  the model is shown as a heading over its stars.

Every star the map draws is on the list, in every subject: a question asked in
the maths conversation may well be about a physics star. A star is drawn when it
has at least one active lesson, the same rule `knowledge_map_service` follows.

The model is shown a short `ref` (`k1`, `k2`, ...) rather than the unit id: the
ids are long slugs, and the whole sky is a few hundred stars sent with every
question, paid for out of the student's own token allowance.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from stoa.services import curriculum_service, knowledge_mastery_service

logger = logging.getLogger(__name__)

#: How long a warm runtime keeps the half of the map that is the same for every
#: student - the catalog and its lesson index - before reading it again. A
#: change to the curriculum reaches the list this much later at most.
CONTENT_TTL_SECONDS = 300

#: locale -> (read at, catalog, lesson index)
_content: dict[str, tuple[float, Mapping[str, Any], Mapping[str, Any]]] = {}


class Candidate(TypedDict):
    """One star the model may name."""

    #: What the model is shown and answers with. Stable only within one list.
    ref: str
    unitId: str
    #: In the language the list was read in, which is the answer's language.
    name: str
    subjectId: str
    topicId: str
    #: The topic's title, in the same language as `name`.
    topicName: str
    #: `lit`, `in_progress` or `ready`, as the map draws it.
    state: str


def from_catalog(
    catalog: Mapping[str, Any],
    states: Mapping[str, knowledge_mastery_service.UnitMastery],
) -> list[Candidate]:
    """The list from facts already read. Pure; in course order: subject, chapter, unit."""
    topics = [topic for topic in catalog.get("topics") or () if isinstance(topic, Mapping)]
    topic_order = {str(topic.get("id") or ""): int(topic.get("order") or 0) for topic in topics}
    topic_names = {
        str(topic.get("id") or ""): str(topic.get("title") or topic.get("id") or "")
        for topic in topics
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
            topicId=str(unit.get("topicId") or ""),
            topicName=topic_names.get(str(unit.get("topicId") or ""), str(unit.get("topicId") or "")),
            state=states[str(unit["id"])].state.value,
        )
        for index, unit in enumerate(drawn, start=1)
    ]


def _shared_content(locale: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """The catalog and lesson index in `locale`, read at most once per TTL."""
    now = time.monotonic()
    cached = _content.get(locale)
    if cached is not None and now - cached[0] < CONTENT_TTL_SECONDS:
        return cached[1], cached[2]
    catalog = curriculum_service.list_catalog(locale=locale)
    indexed = knowledge_mastery_service.indexed_lessons()
    _content[locale] = (now, catalog, indexed)
    return catalog, indexed


def for_student(student_id: str, *, locale: str) -> list[Candidate] | None:
    """Every star on this student's map, or None when the map cannot be read.

    None is not an empty map: an answer given without the list cannot have
    matched anything, so nothing it names may be taken for a gap in the
    knowledge base either. Only the student's own progress is read on every
    call; the content is shared (`CONTENT_TTL_SECONDS`).
    """
    try:
        catalog, indexed = _shared_content(locale)
        states = knowledge_mastery_service.unit_states(
            student_id, locale=locale, catalog=catalog, indexed=indexed
        )
        return from_catalog(catalog, states)
    except Exception:  # noqa: BLE001
        # An answer without the list is far better than no answer at all.
        logger.warning("star_map_candidates_unavailable", exc_info=True)
        return None


def find(candidates: Sequence[Candidate] | None, ref: object) -> Candidate | None:
    """The star `ref` names, if it is one the model was shown; otherwise None."""
    if not candidates or not isinstance(ref, str):
        return None
    wanted = ref.strip()
    return next((candidate for candidate in candidates if candidate["ref"] == wanted), None)


def topic_refs(candidates: Sequence[Candidate]) -> dict[str, str]:
    """Each topic's ref (`t1`, `t2`, ...) by topic id, in the order the list holds them."""
    refs: dict[str, str] = {}
    for candidate in candidates:
        refs.setdefault(candidate["topicId"], f"t{len(refs) + 1}")
    return refs


def find_topic(candidates: Sequence[Candidate] | None, ref: object) -> list[Candidate]:
    """The stars of the topic `ref` names, in course order; none for any other ref."""
    if not candidates or not isinstance(ref, str):
        return []
    wanted = ref.strip()
    topic = next((topic_id for topic_id, shown in topic_refs(candidates).items() if shown == wanted), None)
    return [candidate for candidate in candidates if topic is not None and candidate["topicId"] == topic]
