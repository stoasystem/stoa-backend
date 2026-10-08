"""The star map read model: one sky, as the student's own evidence makes it.

Serves `GET /practice/knowledge-map` (stoasystem/stoa-frontend#48 draws it).
A subject is a galaxy, a topic is a nebula, a unit is a star, and each star
carries the learning state `knowledge_mastery_service` judges it to be in.

Two things are deliberately absent rather than faked:

* **Prerequisites** are `[]` until stoa-backend#56 stores them. With no edge,
  nothing locks, which is what stoa-frontend#9 point 7 asks for.
* **Skills** are `[]` until stoa-backend#58 fills the vocabulary. The 60
  exercises on the platform today carry none.

Coordinates are computed here, deterministically from the identifiers, so the
same sky comes back in the same arrangement on every request and for every
student. That is a stand-in for the offline layout in stoa-backend#60, not a
second implementation of it: when #60 stores `(x, y)` on the rows, this reads
them instead and the shape below does not change.

The core is pure over facts the caller has read, for the same reason the
mastery judgement is: it can be tested without a table double.
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from typing import Any

from stoa.db.repositories import practice_repo, review_repo
from stoa.services import curriculum_translations, curriculum_service, knowledge_mastery_service

logger = logging.getLogger(__name__)

#: Where a nebula's stars sit relative to its centre, as a share of the sky.
NEBULA_RADIUS = 0.055
#: How far the band of galaxies is inset from the edges, so labels have room.
BAND_INSET = 0.08
#: Most due cards the per-unit counts will look at in one request.
REVIEW_COUNT_CEILING = 500


def _unit_interval(value: str, salt: str) -> float:
    """A stable number in [0, 1) from an identifier. Same id, same place."""
    digest = hashlib.sha256(f"{salt}:{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _nebula_centres(nebulae: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float, float]]:
    """Lay the nebulae along one horizontal band, galaxy by galaxy (#119).

    The band is the whole sky: subjects do not get their own canvases, they
    get stretches of one. Nebulae of the same subject stay adjacent because
    the caller hands them in subject-then-order sequence.
    """
    count = len(nebulae)
    if count == 0:
        return {}
    span = 1.0 - 2 * BAND_INSET
    centres: dict[str, tuple[float, float]] = {}
    for index, nebula in enumerate(nebulae):
        topic_id = str(nebula.get("topicId") or "")
        x = BAND_INSET + (span * (index + 0.5) / count)
        # A gentle vertical wander keeps the band from reading as a ruled line
        # while staying deterministic.
        y = 0.5 + 0.18 * math.sin((index + 1) * 2.399) * (0.6 + 0.4 * _unit_interval(topic_id, "y"))
        centres[topic_id] = (x, min(max(y, 0.08), 0.92))
    return centres


def _star_position(unit_id: str, centre: tuple[float, float]) -> tuple[float, float]:
    """Scatter a star inside its nebula, evenly rather than in a ring."""
    angle = _unit_interval(unit_id, "angle") * 2 * math.pi
    # sqrt keeps the scatter uniform over the disc instead of crowding the centre.
    radius = NEBULA_RADIUS * math.sqrt(_unit_interval(unit_id, "radius"))
    x = centre[0] + radius * math.cos(angle)
    y = centre[1] + radius * math.sin(angle)
    return (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0))


def _recommended_unit(
    stars: Sequence[Mapping[str, Any]],
) -> str:
    """At most one recommendation per subject (#9 point 8).

    What the student has already begun comes before anything they have not:
    sending somebody to a new knowledge point while one stands half-finished
    is how a map turns into a list of abandoned starts.
    """
    for state in ("in_progress", "ready"):
        for star in stars:
            if star.get("state") == state:
                return str(star.get("unitId") or "")
    return ""


def build_map(
    *,
    subject_id: str,
    catalog: Mapping[str, Any],
    unit_states: Mapping[str, knowledge_mastery_service.UnitMastery],
    review_due_by_unit: Mapping[str, int],
    streak_days: int,
    score: int,
    enrolled_subject_ids: frozenset[str],
    lit_facts: Mapping[str, knowledge_mastery_service.LitFact] | None = None,
    skill_states: Mapping[str, knowledge_mastery_service.SkillMastery] | None = None,
    locale: str = "de",
) -> dict[str, Any]:
    """One sky from facts already read. Pure; no I/O."""
    facts = lit_facts or {}
    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    topics = [item for item in catalog.get("topics") or () if isinstance(item, Mapping)]
    units = [item for item in catalog.get("units") or () if isinstance(item, Mapping)]

    ordered_topics = sorted(
        topics,
        key=lambda topic: (
            str(topic.get("subjectId") or ""),
            int(topic.get("order") or 0),
            str(topic.get("id") or ""),
        ),
    )
    centres = _nebula_centres(
        [{"topicId": str(topic.get("id") or "")} for topic in ordered_topics]
    )

    nebulae = [
        {
            "topicId": str(topic.get("id") or ""),
            "name": str(topic.get("title") or ""),
            "order": index,
            "subjectId": str(topic.get("subjectId") or ""),
        }
        for index, topic in enumerate(ordered_topics)
    ]

    # The band's own order, so a star sorts by the chapter it is in rather than
    # by how its topic id happens to spell. Sorting by the id put "geometrie"
    # before "gleichungen", and the recommendation - the one affordance on the
    # student's home screen - then pointed at chapter 3 while chapter 2 stood
    # untouched.
    chapter_order = {nebula["topicId"]: nebula["order"] for nebula in nebulae}

    stars: list[dict[str, Any]] = []
    for unit in sorted(
        units,
        key=lambda item: (
            chapter_order.get(str(item.get("topicId") or ""), len(chapter_order)),
            int(item.get("order") or 0),
            str(item.get("id") or ""),
        ),
    ):
        unit_id = str(unit.get("id") or "")
        judged = unit_states.get(unit_id)
        if judged is None or judged.lesson_count == 0:
            # Units with no active lesson are never sent (model contract).
            continue
        topic_id = str(unit.get("topicId") or "")
        # The offline layout wins when the row has been given one (#60); the
        # arrangement below is the stand-in for a map that has not been laid
        # out yet, not a second implementation of it.
        x, y = _laid_out(unit) or _star_position(unit_id, centres.get(topic_id, (0.5, 0.5)))
        fact = facts.get(unit_id)
        stars.append(
            {
                "unitId": unit_id,
                "name": str(unit.get("title") or ""),
                "nebulaId": topic_id,
                "order": int(unit.get("order") or 0),
                "state": judged.state.value,
                "litAt": fact.lit_at if fact else None,
                "litAtSource": fact.source.value if fact else None,
                "progress": round(judged.progress, 4),
                "unmetExercises": judged.unmet_exercises,
                "reviewDue": int(review_due_by_unit.get(unit_id, 0)),
                "recommendation": None,
                "x": round(x, 5),
                "y": round(y, 5),
                "skills": _skills_of(unit_id, skill_states or {}, locale),
                "chapter": {
                    "lessonCount": judged.lesson_count,
                    "lessonsDone": judged.lessons_done,
                    "nextLesson": (
                        {
                            "lessonId": judged.next_lesson.lesson_id,
                            "title": judged.next_lesson.title,
                        }
                        if judged.next_lesson
                        else None
                    ),
                },
            }
        )

    subject_of_nebula = _subject_index(nebulae)
    galaxies: list[dict[str, Any]] = []
    for subject in sorted(subjects, key=lambda item: int(item.get("order") or 0)):
        sid = str(subject.get("id") or "")
        mine = [star for star in stars if _subject_of(star, subject_of_nebula) == sid]
        galaxies.append(
            {
                "subjectId": sid,
                "name": str(subject.get("name") or ""),
                "lit": sum(1 for star in mine if star["state"] == "lit"),
                "total": len(mine),
                "enrolled": sid in enrolled_subject_ids,
            }
        )

    for galaxy in galaxies:
        mine = [star for star in stars if _subject_of(star, subject_of_nebula) == galaxy["subjectId"]]
        recommended = _recommended_unit(mine)
        for star in mine:
            if star["unitId"] == recommended:
                star["recommendation"] = {"source": "system"}

    focused = [star for star in stars if _subject_of(star, subject_of_nebula) == subject_id]
    return {
        "subjectId": subject_id,
        "galaxies": galaxies,
        "nebulae": nebulae,
        "stars": stars,
        "prerequisites": _prerequisite_edges(units),
        "unacknowledgedLit": list(
            knowledge_mastery_service.unacknowledged_lit(
                facts, among=[star["unitId"] for star in stars]
            )
        ),
        "summary": {
            "lit": sum(1 for star in focused if star["state"] == "lit"),
            "total": len(focused),
            "streakDays": streak_days,
            "score": score,
        },
        "source": "derived_mastery",
    }


def _subject_index(nebulae: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {str(nebula["topicId"]): str(nebula["subjectId"]) for nebula in nebulae}


def _subject_of(star: Mapping[str, Any], subject_of_nebula: Mapping[str, str]) -> str:
    return subject_of_nebula.get(str(star["nebulaId"]), "")


def _review_due_by_unit(student_id: str, lessons: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Due review cards, counted per unit through the lesson they belong to."""
    unit_of_lesson = {
        str(lesson.get("id") or ""): str(lesson.get("unitId") or "") for lesson in lessons
    }
    try:
        # The repository's default limit is a page for a review session; this
        # is a count across the whole sky, so it asks for the ceiling the map
        # can draw. Above it the badge under-reports rather than misleads.
        #
        # The real ceiling is lower than this number: `list_cards` reads one
        # DynamoDB page (1 MB) without following `LastEvaluatedKey`, so past a
        # page the "soonest first" ordering is only over that first slice.
        cards = review_repo.list_due_cards(
            student_id, now=datetime.now(timezone.utc), limit=REVIEW_COUNT_CEILING
        )
    except Exception:  # noqa: BLE001
        # Silently zeroing every review badge would look like "nothing due".
        logger.warning("Review counts unavailable for the star map", exc_info=True)
        return {}
    counts: dict[str, int] = {}
    for card in cards:
        unit_id = unit_of_lesson.get(str(card.get("lesson_id") or ""), "")
        if unit_id:
            counts[unit_id] = counts.get(unit_id, 0) + 1
    return counts


def _stored_lit_facts(rows: Sequence[Mapping[str, Any]]) -> dict[str, knowledge_mastery_service.LitFact]:
    facts: dict[str, knowledge_mastery_service.LitFact] = {}
    for row in rows:
        unit_id = str(row.get("unit_id") or "")
        if not unit_id:
            continue
        try:
            source = knowledge_mastery_service.LitSource(str(row.get("lit_at_source") or ""))
        except ValueError:
            # A row whose source cannot be read is treated as history. Guessing
            # `observed` here would celebrate a lighting nobody watched happen.
            source = knowledge_mastery_service.LitSource.BACKFILLED
        facts[unit_id] = knowledge_mastery_service.LitFact(
            unit_id=unit_id,
            lit_at=str(row.get("lit_at") or ""),
            source=source,
            acknowledged=bool(row.get("acknowledged_at")),
        )
    return facts


def _lit_facts(
    student_id: str, states: Mapping[str, knowledge_mastery_service.UnitMastery]
) -> dict[str, knowledge_mastery_service.LitFact]:
    """Read this student's lightings, and write down the ones not seen before.

    The read model is where a lighting is first noticed, because it is the only
    place that holds the whole judgement. The writes are the new ones only, so a
    sky with nothing new in it costs no write at all.

    The ledger is opened **last**. If the lighting rows fail to write, the next
    read finds the ledger still shut and records them as history - a missed
    celebration. Opening it first and then failing would record them as
    `observed` on the next read and celebrate lightings from before the student
    ever had this feature.
    """
    ledger = practice_repo.read_lit_ledger(student_id)
    facts, fresh = knowledge_mastery_service.resolve_lit_facts(
        lit_unit_ids=sorted(knowledge_mastery_service.lit_unit_ids(states.values())),
        stored=_stored_lit_facts(ledger["units"]),
        ledger_open=bool(ledger["open"]),
        now=datetime.now(timezone.utc).isoformat(),
    )
    try:
        for fact in fresh:
            practice_repo.record_lit_unit(
                student_id, fact.unit_id, lit_at=fact.lit_at, source=fact.source.value
            )
        if not ledger["open"]:
            practice_repo.open_lit_ledger(student_id)
    except Exception:  # noqa: BLE001
        # A sky that will not draw is worse than one whose celebration is late.
        logger.warning("Lighting facts could not be recorded", exc_info=True)
    return facts


def acknowledge_lit(student_id: str, unit_ids: Sequence[str]) -> dict[str, Any]:
    """Record that this student has been shown these lightings.

    Kept on the server and keyed by the student, so a refresh does not replay
    the celebration and a second device does not play it again.
    """
    confirmed = practice_repo.acknowledge_lit_units(
        student_id, [str(unit_id) for unit_id in unit_ids if unit_id]
    )
    return {"acknowledged": confirmed}


def knowledge_map(
    student_id: str,
    *,
    subject_id: str | None = None,
    locale: str = "de",
) -> dict[str, Any]:
    """The whole sky for one student, with `subject_id` as the galaxy in focus."""
    catalog = curriculum_service.list_catalog(locale=locale)
    states = knowledge_mastery_service.unit_states(
        student_id, locale=locale, catalog=catalog
    )
    lessons = [item for item in catalog.get("lessons") or () if isinstance(item, Mapping)]
    summary = curriculum_service.get_progress_summary(student_id)

    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    focus = subject_id or (str(subjects[0].get("id") or "") if subjects else "")

    enrolled = frozenset(
        str(item.get("subject_id") or "")
        for item in practice_repo.get_progress(student_id, None)
        if item.get("subject_id")
    )
    return build_map(
        subject_id=focus,
        catalog=catalog,
        unit_states=states,
        review_due_by_unit=_review_due_by_unit(student_id, lessons),
        streak_days=int(summary.get("studyStreak") or 0),
        score=0,
        enrolled_subject_ids=enrolled,
        lit_facts=_lit_facts(student_id, states),
        skill_states=knowledge_mastery_service.skill_states(
            student_id, locale=locale, catalog=catalog
        ),
        locale=locale,
    )


def _laid_out(row: Mapping[str, Any]) -> tuple[float, float] | None:
    """The coordinates the layout script wrote on this row, if it has run."""
    x, y = row.get("x"), row.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x), float(y)
    return None


def _skills_of(
    unit_id: str,
    states: Mapping[str, knowledge_mastery_service.SkillMastery],
    locale: str,
) -> list[dict[str, Any]]:
    """The skill points around one star, in a fixed order (#58)."""
    mine = [state for state in states.values() if state.unit_id == unit_id]
    return [
        {
            "skillId": state.skill_id,
            "name": curriculum_translations.skill_title(state.skill_id, locale),
            "lit": state.lit,
        }
        for state in sorted(mine, key=lambda state: state.skill_id)
    ]


def _prerequisite_edges(units: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """What has to come first, as edges the map can draw (#56).

    Only edges whose both ends are units this map knows about: a reference to
    a unit that has been archived or removed would otherwise be drawn as a
    line to nowhere.
    """
    known = {str(unit.get("id") or "") for unit in units}
    edges: list[dict[str, str]] = []
    for unit in sorted(units, key=lambda item: str(item.get("id") or "")):
        unit_id = str(unit.get("id") or "")
        stated = unit.get("prerequisiteUnitIds")
        if not isinstance(stated, list | tuple):
            continue
        for item in stated:
            before = str(item or "")
            if before and before in known and before != unit_id:
                edges.append({"from": before, "to": unit_id})
    return edges
