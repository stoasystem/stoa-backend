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
from stoa.services import (
    curriculum_service,
    curriculum_translations,
    knowledge_base_catalog,
    knowledge_mastery_service,
)

logger = logging.getLogger(__name__)

class UnknownSubject(Exception):
    """The request named a subject the catalog has never heard of (#124).

    Raised instead of an HTTP error so the read model stays free of the web
    layer; `routers/practice.py` turns it into the 422.
    """


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

    unit_names = {str(unit.get("id") or ""): str(unit.get("title") or "") for unit in units}
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
                "skills": _skills_of(unit_id, skill_states or {}, locale, unit_names),
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


#: What the whole sky is sent as. `skeleton` is every star with its state and
#: position but none of its small stars: the client opens on it and asks for the
#: few stars around where the student is with `neighbourhood`.
MAP_VIEWS = ("full", "skeleton")


def knowledge_map(
    student_id: str,
    *,
    subject_id: str | None = None,
    locale: str = "de",
    view: str = "full",
) -> dict[str, Any]:
    """The whole sky for one student, with `subject_id` as the galaxy in focus."""
    catalog = curriculum_service.list_catalog(locale=locale)
    # Blank is absent, whether it arrived as no parameter at all or as one with
    # nothing in it; either way the first galaxy takes the focus as it always has.
    requested = str(subject_id or "").strip()
    _require_known_subject(requested, catalog)
    states = knowledge_mastery_service.unit_states(student_id, locale=locale, catalog=catalog)
    lessons = [item for item in catalog.get("lessons") or () if isinstance(item, Mapping)]
    summary = curriculum_service.get_progress_summary(student_id)

    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    # Normalised, because the galaxies carry the catalog's own ids: asking for
    # `mathematics` matched no galaxy named `math`, so the sky came back whole
    # with a summary of 0 of 0 (#124). An alias names the subject it is an
    # alias of; it does not name a subject with nothing in it.
    focus = (
        practice_repo.normal_subject_id(requested)
        if requested
        else (str(subjects[0].get("id") or "") if subjects else "")
    )

    enrolled = frozenset(
        str(item.get("subject_id") or "")
        for item in practice_repo.get_progress(student_id, None)
        if item.get("subject_id")
    )
    sky = build_map(
        subject_id=focus,
        catalog=catalog,
        unit_states=states,
        review_due_by_unit=_review_due_by_unit(student_id, lessons),
        streak_days=int(summary.get("studyStreak") or 0),
        score=0,
        enrolled_subject_ids=enrolled,
        lit_facts=_lit_facts(student_id, states),
        skill_states=(
            None if view == "skeleton"
            else knowledge_mastery_service.skill_states(student_id, locale=locale, catalog=catalog)
        ),
        locale=locale,
    )
    if view == "skeleton":
        sky["view"] = "skeleton"
    return sky


#: How many stars of the same nebula, on each side of the one in focus, come with it.
NEIGHBOURS_EACH_SIDE = 2
#: The most stars one neighbourhood sends.
MAX_NEIGHBOURHOOD = 15


def neighbourhood(
    student_id: str,
    *,
    subject_id: str | None = None,
    around: str | None = None,
    locale: str = "de",
) -> dict[str, Any]:
    """A few stars in full - small stars, practice sets, what is missing - around one.

    The star in focus is `around`, else the one the student last finished
    practice in, else the map's recommendation. With it come the stars it needs
    (its prerequisites), the stars that need it, and its neighbours in its
    nebula, so the client loads what the student is about to look at rather than
    the whole sky."""
    catalog = curriculum_service.list_catalog(locale=locale)
    requested = str(subject_id or "").strip()
    _require_known_subject(requested, catalog)
    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    subject = (
        practice_repo.normal_subject_id(requested)
        if requested
        else (str(subjects[0].get("id") or "") if subjects else "")
    )
    indexed = knowledge_mastery_service.indexed_lessons()
    states = knowledge_mastery_service.unit_states(
        student_id, locale=locale, catalog=catalog, indexed=indexed
    )
    units = {
        str(unit.get("id") or ""): unit
        for unit in catalog.get("units") or ()
        if isinstance(unit, Mapping)
        and practice_repo.normal_subject_id(unit.get("subjectId")) == subject
        and states.get(str(unit.get("id") or "")) is not None
        and states[str(unit.get("id") or "")].lesson_count > 0
    }
    focus = _focus(student_id, around, units, states)
    if not focus:
        return {"subjectId": subject, "focus": None, "stars": []}

    picked = _around(focus, units)
    narrowed = {
        **catalog,
        "units": [units[unit_id] for unit_id in picked],
    }
    lessons = [item for item in catalog.get("lessons") or () if isinstance(item, Mapping)]
    sky = build_map(
        subject_id=subject,
        catalog=narrowed,
        unit_states=states,
        review_due_by_unit=_review_due_by_unit(student_id, lessons),
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset(),
        skill_states=knowledge_mastery_service.skill_states(
            student_id, locale=locale, catalog=catalog, indexed=indexed
        ),
        locale=locale,
    )
    done = frozenset(
        str(item.get("lesson_id") or "")
        for item in practice_repo.get_progress(student_id, None)
        if item.get("status") == "completed"
    )
    stars = []
    for star in sky["stars"]:
        unit_id = star["unitId"]
        stars.append({
            **star,
            "relation": picked[unit_id],
            "prerequisiteUnitIds": _prerequisites_of(unit_id, units),
            "practiceSets": _practice_sets(unit_id, lessons, indexed, done),
        })
    order = list(picked)
    stars.sort(key=lambda star: order.index(star["unitId"]))
    return {"subjectId": subject, "focus": focus, "stars": stars}


def _prerequisites_of(unit_id: str, units: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """What a star needs: the unit row's own prerequisites, and for a knowledge-base
    star those drawn from its knowledge points - shown, never locking."""
    stated = [str(item) for item in units[unit_id].get("prerequisiteUnitIds") or () if item]
    drawn = next(
        (list(star.get("prerequisites") or []) for star in knowledge_base_catalog.units()
         if star["unit_id"] == unit_id),
        [],
    )
    return [item for item in dict.fromkeys([*stated, *drawn]) if item in units and item != unit_id]


def _focus(
    student_id: str,
    around: str | None,
    units: Mapping[str, Mapping[str, Any]],
    states: Mapping[str, knowledge_mastery_service.UnitMastery],
) -> str:
    if around and around in units:
        return around
    finished = sorted(
        (
            item for item in practice_repo.get_progress(student_id, None)
            if item.get("status") == "completed" and str(item.get("unit_id") or "") in units
        ),
        key=lambda item: str(item.get("completed_at") or ""),
    )
    if finished:
        return str(finished[-1].get("unit_id") or "")
    ordered = sorted(units.values(), key=lambda unit: (str(unit.get("topicId") or ""), int(unit.get("order") or 0)))
    stars = [{"unitId": str(unit.get("id") or ""), "state": states[str(unit.get("id") or "")].state.value}
             for unit in ordered]
    return _recommended_unit(stars) or (stars[0]["unitId"] if stars else "")


def _around(focus: str, units: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The stars that come with the one in focus, each with why, in this order."""
    picked: dict[str, str] = {focus: "focus"}

    def add(unit_id: str, role: str) -> None:
        if unit_id in units and unit_id not in picked and len(picked) < MAX_NEIGHBOURHOOD:
            picked[unit_id] = role

    for unit_id in _prerequisites_of(focus, units):
        add(unit_id, "prerequisite")
    for unit_id in sorted(units):
        if focus in _prerequisites_of(unit_id, units):
            add(unit_id, "next")
    nebula = sorted(
        (unit for unit in units.values() if unit.get("topicId") == units[focus].get("topicId")),
        key=lambda unit: (int(unit.get("order") or 0), str(unit.get("id") or "")),
    )
    position = [str(unit.get("id") or "") for unit in nebula].index(focus)
    for unit in nebula[max(0, position - NEIGHBOURS_EACH_SIDE): position + NEIGHBOURS_EACH_SIDE + 1]:
        add(str(unit.get("id") or ""), "neighbour")
    return picked


def _practice_sets(
    unit_id: str,
    lessons: Sequence[Mapping[str, Any]],
    indexed: Mapping[str, list[dict[str, Any]]],
    done: frozenset[str],
) -> list[dict[str, Any]]:
    """A star's practice, in the order it is worked through, each under its small star."""
    mine = sorted(
        (lesson for lesson in lessons if str(lesson.get("unitId") or "") == unit_id),
        key=lambda lesson: (int(lesson.get("order") or 0), str(lesson.get("id") or "")),
    )
    sets = []
    for lesson in mine:
        lesson_id = str(lesson.get("id") or "")
        skills = [skill for entry in indexed.get(lesson_id, []) for skill in entry.get("skills") or ()]
        item: dict[str, Any] = {
            "lessonId": lesson_id,
            "title": str(lesson.get("title") or ""),
            "order": int(lesson.get("order") or 0),
            "exerciseCount": int(lesson.get("exerciseCount") or 0),
            "skillId": skills[0] if skills else None,
            "status": "completed" if lesson_id in done else "available",
        }
        if lesson.get("extension"):
            item["extension"] = True
        sets.append(item)
    return sets


def _known_subject_ids(catalog: Mapping[str, Any]) -> frozenset[str]:
    """Every subject this catalog knows of, in canonical form.

    Both the subjects that carry content today and the ones the curriculum
    declares it teaches: a galaxy with nothing in it yet is still a real
    galaxy, and `rolloutSubjects` is where the catalog says so.
    """
    known = {
        practice_repo.normal_subject_id(subject.get("id"))
        for subject in catalog.get("subjects") or ()
        if isinstance(subject, Mapping)
    }
    known.update(
        practice_repo.normal_subject_id(subject)
        for subject in catalog.get("rolloutSubjects") or ()
    )
    return frozenset(known - {""})


def _require_known_subject(subject_id: str | None, catalog: Mapping[str, Any]) -> None:
    """Refuse a subject nobody teaches rather than echo it back as the focus (#124).

    `chemistry` came back 200 with `"subjectId": "chemistry"` on a sky made
    entirely of mathematics, so the response agreed with a request that named
    nothing. A subject the student has simply not started is **not** refused:
    browsing a galaxy before enrolling in it is what the map is for.

    No subject at all is also not refused — that is the whole sky with the
    first galaxy in focus, and it keeps working exactly as before.
    """
    if not subject_id:
        return
    if practice_repo.normal_subject_id(subject_id) not in _known_subject_ids(catalog):
        raise UnknownSubject(str(subject_id))


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
    unit_names: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """The skill points around one star, in a fixed order (#58).

    A skill point that deepens its star says `extension`; one whose next
    practice needs knowledge not mastered yet names where that knowledge is
    (`missingPrerequisites`). Nothing is locked by it."""
    names = unit_names or {}
    mine = [state for state in states.values() if state.unit_id == unit_id]
    out = []
    for state in sorted(mine, key=lambda state: state.skill_id):
        item: dict[str, Any] = {
            "skillId": state.skill_id,
            "name": curriculum_translations.skill_title(state.skill_id, locale),
            "lit": state.lit,
        }
        if state.extension:
            item["extension"] = True
        if not state.ready:
            item["missingPrerequisites"] = [
                {"unitId": missing, "name": names.get(missing, missing)}
                for missing in state.missing_unit_ids
            ]
        out.append(item)
    return out


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
