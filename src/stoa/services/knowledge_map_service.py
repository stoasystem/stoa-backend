"""The star map read model: one sky, as the student's own evidence makes it.

Serves `GET /practice/knowledge-map` (stoasystem/stoa-frontend#48 draws it).
A subject is a galaxy, a topic is a nebula, a unit is a star, and each star
carries the learning state `knowledge_mastery_service` judges it to be in.

* **Prerequisites** are the unit rows' `prerequisite_unit_ids`, which only the
  seed writes, and the only source: the whole map, the view around one star and
  the mastery judgement all read them (stoa-backend#317). Since
  stoa-backend#125 they lock nothing; they decide which prerequisites a star
  reports unlit and where the map recommends starting.
* **Skills** are the skill points each star's exercises train (stoa-backend#58).

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
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.services import (
    curriculum_service,
    curriculum_translations,
    knowledge_base_catalog,
    knowledge_mastery_service,
    learning_profile_service,
)
from stoa.services.student_evidence import StudentEvidence

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


#: Where a year group sits in school, so a star's can be compared with the
#: student's: its HarmoS year (`learning_profile_service`). A stage counts from
#: its first year - a student who said only "lower secondary" starts where it
#: starts - and upper secondary comes after the last year of compulsory school.
#: Both stages are year groups a profile may store (upper secondary since #419)
#: and both have no HarmoS year, so they are placed here and only here.
SCHOOL_YEAR: dict[str, int] = {
    **{
        code: year
        for code, year in learning_profile_service.GRADE_LEVEL_HARMOS_YEARS.items()
        if year is not None
    },
    "grade_secondary_i": 9,
    knowledge_base_catalog.UPPER_SECONDARY: 12,
}


def _school_year(code: object) -> int | None:
    return SCHOOL_YEAR.get(str(code or "").strip())


def _star_years(
    units: Sequence[Mapping[str, Any]],
    topics: Sequence[Mapping[str, Any]],
    lessons: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """The school year each star belongs to, where the curriculum says (#310).

    A star's practice sets carry the year of the knowledge points in them, so a
    star is the year its earliest set is: where a student meets it first. A
    star none of whose sets says is its topic's year. One with neither has no
    year, and is never picked for one.
    """
    years: dict[str, int] = {}
    for lesson in lessons:
        year = _school_year(lesson.get("gradeLevel"))
        unit_id = str(lesson.get("unitId") or "")
        if year is not None and unit_id:
            years[unit_id] = min(year, years.get(unit_id, year))
    topic_year = {str(topic.get("id") or ""): _school_year(topic.get("gradeLevel")) for topic in topics}
    for unit in units:
        unit_id = str(unit.get("id") or "")
        year = topic_year.get(str(unit.get("topicId") or ""))
        if unit_id and unit_id not in years and year is not None:
            years[unit_id] = year
    return years


def _start_for_year(
    stars: Sequence[Mapping[str, Any]],
    *,
    student_year: int | None,
    star_years: Mapping[str, int],
) -> Mapping[str, Any] | None:
    """Where a student with nothing begun starts, by their year (#310).

    The first star of their year in the course; with none, the first of the
    latest year before theirs. Nothing when the student has no year or the
    subject has no star at or below it. The star need not be on the frontier:
    a prerequisite is advice, not a lock (ADR 0004).
    """
    if student_year is None:
        return None
    open_stars = [star for star in stars if star["state"] != "lit"]
    reachable = [
        star_years[star["unitId"]]
        for star in open_stars
        if star["unitId"] in star_years and star_years[star["unitId"]] <= student_year
    ]
    if not reachable:
        return None
    year = max(reachable)
    return next(star for star in open_stars if star_years.get(star["unitId"]) == year)


def _recommendation(
    stars: Sequence[dict[str, Any]],
    *,
    subject_id: str,
    subject_of: Callable[[Mapping[str, Any]], str],
    successors: Mapping[str, Sequence[str]],
    facts: Mapping[str, knowledge_mastery_service.LitFact],
    evidence: Mapping[str, str],
    student_year: int | None = None,
    star_years: Mapping[str, int] | None = None,
) -> tuple[dict[str, Any], str, str | None] | None:
    """The star one subject recommends, why, and after which lighting (#164).

    Decided in stoa-frontend#474: the recommendation follows the student.
    ``stars`` is the whole sky in course order (subject, chapter, unit).

    1. A star in progress, the one with the latest evidence (ties: earlier in
       the course), whatever its prerequisites: `in_progress`.
    2. Else after the latest lighting - this subject's own, or another's whose
       successor is here (ties: furthest in the course, this subject's own
       first; a backfilled lighting counts): its successor on the frontier
       that comes first in the course, else this subject's next frontier star
       after it, wrapping round: `after_lit`.
    3. Else, for a student whose year group can be read, the first star of
       that year in the course, else the first of the latest year before it,
       on the frontier or not: `grade` (#310).
       Else the first frontier star: `start`.

    The frontier is what is not lit and has every prerequisite lit; apart
    from rules 1 and 3 by year, only frontier stars are recommended.
    """
    position = {star["unitId"]: index for index, star in enumerate(stars)}
    mine = [star for star in stars if subject_of(star) == subject_id]
    by_id = {star["unitId"]: star for star in stars}

    in_progress = [star for star in mine if star["state"] == "in_progress"]
    if in_progress:
        latest = max(
            in_progress,
            key=lambda star: (str(evidence.get(star["unitId"]) or ""), -position[star["unitId"]]),
        )
        return latest, "in_progress", None

    frontier = [
        star for star in mine if star["state"] != "lit" and not star.get("unlitPrerequisiteIds")
    ]
    if not frontier:
        return None
    frontier_ids = {star["unitId"] for star in frontier}

    def after(lit_id: str) -> dict[str, Any] | None:
        following = [
            by_id[unit_id] for unit_id in successors.get(lit_id, ()) if unit_id in frontier_ids
        ]
        if following:
            return min(following, key=lambda star: position[star["unitId"]])
        if subject_of(by_id[lit_id]) != subject_id:
            return None
        # The course order, from the star after this one, round to the start.
        place = position[lit_id]
        later = [star for star in frontier if position[star["unitId"]] > place]
        return (later or frontier)[0]

    def lit_at(star: Mapping[str, Any]) -> str:
        fact = facts.get(star["unitId"])
        return fact.lit_at if fact else ""

    lightings = [
        star
        for star in stars
        if star["state"] == "lit"
        and (
            subject_of(star) == subject_id
            or any(unit_id in by_id and subject_of(by_id[unit_id]) == subject_id
                   for unit_id in successors.get(star["unitId"], ()))
        )
    ]
    lightings.sort(
        key=lambda star: (lit_at(star), subject_of(star) == subject_id, position[star["unitId"]]),
        reverse=True,
    )
    for lit in lightings:
        following = after(lit["unitId"])
        if following is not None:
            return following, "after_lit", lit["unitId"]
    by_year = _start_for_year(mine, student_year=student_year, star_years=star_years or {})
    if by_year is not None:
        return by_id[by_year["unitId"]], "grade", None
    return frontier[0], "start", None


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
    star_quiz_retry_at: Mapping[str, str] | None = None,
    last_evidence_by_unit: Mapping[str, str] | None = None,
    student_grade: str | None = None,
) -> dict[str, Any]:
    """One sky from facts already read. Pure; no I/O.

    ``last_evidence_by_unit`` is when the student last did something in each
    knowledge point (an answer, a finished lesson); the recommendation reads it.
    ``student_grade`` is the year group on the student's profile, as stored;
    where nothing is begun, the recommendation starts at that year.
    """
    facts = lit_facts or {}
    retry_at = star_quiz_retry_at or {}
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
                "unlitPrerequisiteIds": list(judged.unlit_prerequisite_ids),
                # When a lost star quiz can be taken again; None when it can now (#165).
                "starQuizRetryAt": retry_at.get(unit_id),
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
                "enrolled": curriculum_service.subject_key(sid)
                in {curriculum_service.subject_key(item) for item in enrolled_subject_ids},
            }
        )

    successors: dict[str, list[str]] = {}
    for unit in units:
        for before in unit.get("prerequisiteUnitIds") or ():
            successors.setdefault(str(before), []).append(str(unit.get("id") or ""))
    student_year = _school_year(learning_profile_service.resolve_grade_code(student_grade))
    star_years = (
        _star_years(
            units,
            topics,
            [item for item in catalog.get("lessons") or () if isinstance(item, Mapping)],
        )
        if student_year is not None
        else {}
    )
    for galaxy in galaxies:
        if not galaxy["enrolled"]:
            continue
        picked = _recommendation(
            stars,
            subject_id=galaxy["subjectId"],
            subject_of=lambda star: _subject_of(star, subject_of_nebula),
            successors=successors,
            facts=facts,
            evidence=last_evidence_by_unit or {},
            student_year=student_year,
            star_years=star_years,
        )
        if picked is not None:
            star, reason, related = picked
            star["recommendation"] = {"source": "system", "reason": reason, "relatedUnitId": related}

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


def _review_badges(evidence: StudentEvidence) -> dict[str, int]:
    """Due review cards per unit, or none drawn if they cannot be read."""
    try:
        return evidence.review_due_by_unit
    except Exception:  # noqa: BLE001
        # Silently zeroing every review badge would look like "nothing due".
        logger.warning("Review counts unavailable for the star map", exc_info=True)
        return {}


def _last_evidence_by_unit(evidence: StudentEvidence) -> dict[str, str]:
    """When the student last did something in each knowledge point, for the recommendation."""
    try:
        return evidence.last_activity_by_unit
    except Exception:  # noqa: BLE001
        # A recommendation without it still picks a star in progress, by order.
        logger.warning("Last activity unavailable for the star map", exc_info=True)
        return {}


def _lit_facts(
    evidence: StudentEvidence, states: Mapping[str, knowledge_mastery_service.UnitMastery]
) -> dict[str, knowledge_mastery_service.LitFact]:
    """This student's lightings, with the ones not seen before written down.

    The read model is where a lighting is first noticed, because it is the only
    place that holds the whole judgement. The writes are the new ones only, so a
    sky with nothing new in it costs no write at all.

    The ledger is opened **last**. If the lighting rows fail to write, the next
    read finds the ledger still shut and records them as history - a missed
    celebration. Opening it first and then failing would record them as
    `observed` on the next read and celebrate lightings from before the student
    ever had this feature.
    """
    student_id = evidence.student_id
    ledger_open = evidence.lit_ledger_open
    facts, fresh = knowledge_mastery_service.resolve_lit_facts(
        lit_unit_ids=sorted(knowledge_mastery_service.lit_unit_ids(states.values())),
        stored=evidence.lit_facts,
        ledger_open=ledger_open,
        now=datetime.now(timezone.utc).isoformat(),
    )
    try:
        for fact in fresh:
            practice_repo.record_lit_unit(
                student_id, fact.unit_id, lit_at=fact.lit_at, source=fact.source.value
            )
        if not ledger_open:
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
    evidence: StudentEvidence,
    *,
    subject_id: str | None = None,
    view: str = "full",
    student_grade: str | None = None,
    chosen_subject_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """The whole sky for one student, with `subject_id` as the galaxy in focus.

    `student_grade` is the year group on the student's profile, as stored.
    `chosen_subject_ids` are the subjects the student ticked on their profile:
    taken as much as a subject they have progress in (#321).
    """
    catalog = evidence.content.catalog
    # Blank is absent, whether it arrived as no parameter at all or as one with
    # nothing in it; either way the first galaxy takes the focus as it always has.
    requested = str(subject_id or "").strip()
    _require_known_subject(requested, catalog)
    states = knowledge_mastery_service.unit_states(evidence)

    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    # Normalised, because the galaxies carry the catalog's own ids: asking for
    # `mathematics` matched no galaxy named `math`, so the sky came back whole
    # with a summary of 0 of 0 (#124). An alias names the subject it is an
    # alias of; it does not name a subject with nothing in it.
    focus = (
        curriculum_service.subject_key(requested)
        if requested
        else (str(subjects[0].get("id") or "") if subjects else "")
    )

    sky = build_map(
        subject_id=focus,
        catalog=catalog,
        unit_states=states,
        review_due_by_unit=_review_badges(evidence),
        streak_days=evidence.study_streak,
        score=0,
        # Normalised there: a student taking maths was once told they do not
        # take it - drawn dimmed, and since #164 given no recommendation.
        # A subject is taken once there is progress in it or the student ticked
        # it: a new student has no progress anywhere, and would get nothing to
        # start with however their year group reads (#321). The union only
        # grows - unticking a subject with progress in it does not drop it.
        enrolled_subject_ids=evidence.subjects_taken
        | frozenset(curriculum_service.subject_key(item) for item in chosen_subject_ids),
        lit_facts=_lit_facts(evidence, states),
        star_quiz_retry_at=evidence.star_quiz_retry_at,
        last_evidence_by_unit=_last_evidence_by_unit(evidence),
        student_grade=student_grade,
        skill_states=(
            None if view == "skeleton" else knowledge_mastery_service.skill_states(evidence)
        ),
        locale=evidence.content.locale,
    )
    if view == "skeleton":
        sky["view"] = "skeleton"
    return sky


#: How many stars of the same nebula, on each side of the one in focus, come with it.
NEIGHBOURS_EACH_SIDE = 2
#: The most stars one neighbourhood sends.
MAX_NEIGHBOURHOOD = 15


def neighbourhood(
    evidence: StudentEvidence,
    *,
    subject_id: str | None = None,
    around: str | None = None,
) -> dict[str, Any]:
    """A few stars in full - small stars, practice sets, what is missing - around one.

    The star in focus is `around`, else the one the student last finished
    practice in, else the map's recommendation. With it come the stars it needs
    (its prerequisites), the stars that need it, and its neighbours in its
    nebula, so the client loads what the student is about to look at rather than
    the whole sky."""
    catalog = evidence.content.catalog
    requested = str(subject_id or "").strip()
    _require_known_subject(requested, catalog)
    subjects = [item for item in catalog.get("subjects") or () if isinstance(item, Mapping)]
    subject = (
        curriculum_service.subject_key(requested)
        if requested
        else (str(subjects[0].get("id") or "") if subjects else "")
    )
    states = knowledge_mastery_service.unit_states(evidence)
    units = {
        str(unit.get("id") or ""): unit
        for unit in catalog.get("units") or ()
        if isinstance(unit, Mapping)
        and curriculum_service.subject_key(unit.get("subjectId")) == subject
        and states.get(str(unit.get("id") or "")) is not None
        and states[str(unit.get("id") or "")].lesson_count > 0
    }
    focus = _focus(evidence, around, units, states)
    if not focus:
        return {"subjectId": subject, "focus": None, "stars": []}

    picked = _around(focus, units)
    narrowed = {
        **catalog,
        "units": [units[unit_id] for unit_id in picked],
    }
    lessons = evidence.content.lessons
    sky = build_map(
        subject_id=subject,
        catalog=narrowed,
        unit_states=states,
        review_due_by_unit=_review_badges(evidence),
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset(),
        skill_states=knowledge_mastery_service.skill_states(evidence),
        locale=evidence.content.locale,
        star_quiz_retry_at=evidence.star_quiz_retry_at,
    )
    done = evidence.completed_lesson_ids
    stars = []
    for star in sky["stars"]:
        unit_id = star["unitId"]
        stars.append({
            **star,
            "relation": picked[unit_id],
            "prerequisiteUnitIds": _prerequisites_of(unit_id, units),
            "practiceSets": _practice_sets(unit_id, lessons, evidence, done),
        })
    order = list(picked)
    stars.sort(key=lambda star: order.index(star["unitId"]))
    return {"subjectId": subject, "focus": focus, "stars": stars}


def _prerequisites_of(unit_id: str, units: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """What a star needs, from its unit row - shown, never locking."""
    stated = units[unit_id].get("prerequisiteUnitIds")
    if not isinstance(stated, list | tuple):
        return []
    return [
        item for item in dict.fromkeys(str(entry or "") for entry in stated)
        if item and item in units and item != unit_id
    ]


def _focus(
    evidence: StudentEvidence,
    around: str | None,
    units: Mapping[str, Mapping[str, Any]],
    states: Mapping[str, knowledge_mastery_service.UnitMastery],
) -> str:
    if around and around in units:
        return around
    finished = [item for item in evidence.completions if item.unit_id in units]
    if finished:
        return finished[-1].unit_id
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
    evidence: StudentEvidence,
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
        skills = [
            skill
            for entry in evidence.content.indexed.get(lesson_id, [])
            for skill in entry.get("skills") or ()
        ]
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
        curriculum_service.subject_key(subject.get("id"))
        for subject in catalog.get("subjects") or ()
        if isinstance(subject, Mapping)
    }
    known.update(
        curriculum_service.subject_key(subject)
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
    if curriculum_service.subject_key(subject_id) not in _known_subject_ids(catalog):
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
