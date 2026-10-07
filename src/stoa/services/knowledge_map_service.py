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
import math
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from typing import Any

from stoa.db.repositories import practice_repo, review_repo
from stoa.services import curriculum_service, knowledge_mastery_service

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
) -> dict[str, Any]:
    """One sky from facts already read. Pure; no I/O."""
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

    stars: list[dict[str, Any]] = []
    for unit in sorted(
        units,
        key=lambda item: (
            str(item.get("subjectId") or ""),
            str(item.get("topicId") or ""),
            int(item.get("order") or 0),
        ),
    ):
        unit_id = str(unit.get("id") or "")
        judged = unit_states.get(unit_id)
        if judged is None or judged.lesson_count == 0:
            # Units with no active lesson are never sent (model contract).
            continue
        topic_id = str(unit.get("topicId") or "")
        x, y = _star_position(unit_id, centres.get(topic_id, (0.5, 0.5)))
        stars.append(
            {
                "unitId": unit_id,
                "name": str(unit.get("title") or ""),
                "nebulaId": topic_id,
                "order": int(unit.get("order") or 0),
                "state": judged.state.value,
                "progress": round(judged.progress, 4),
                "unmetExercises": judged.unmet_exercises,
                "reviewDue": int(review_due_by_unit.get(unit_id, 0)),
                "recommendation": None,
                "x": round(x, 5),
                "y": round(y, 5),
                "skills": [],  # stoa-backend#58
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

    galaxies: list[dict[str, Any]] = []
    for subject in sorted(subjects, key=lambda item: int(item.get("order") or 0)):
        sid = str(subject.get("id") or "")
        mine = [star for star in stars if _subject_of(star, nebulae) == sid]
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
        mine = [star for star in stars if _subject_of(star, nebulae) == galaxy["subjectId"]]
        recommended = _recommended_unit(mine)
        for star in mine:
            if star["unitId"] == recommended:
                star["recommendation"] = {"source": "system"}

    focused = [star for star in stars if _subject_of(star, nebulae) == subject_id]
    return {
        "subjectId": subject_id,
        "galaxies": galaxies,
        "nebulae": nebulae,
        "stars": stars,
        "prerequisites": [],  # stoa-backend#56
        "summary": {
            "lit": sum(1 for star in focused if star["state"] == "lit"),
            "total": len(focused),
            "streakDays": streak_days,
            "score": score,
        },
        "source": "derived_mastery",
    }


def _subject_of(star: Mapping[str, Any], nebulae: Sequence[Mapping[str, Any]]) -> str:
    for nebula in nebulae:
        if nebula["topicId"] == star["nebulaId"]:
            return str(nebula["subjectId"])
    return ""


def _review_due_by_unit(student_id: str, lessons: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Due review cards, counted per unit through the lesson they belong to."""
    unit_of_lesson = {
        str(lesson.get("id") or ""): str(lesson.get("unitId") or "") for lesson in lessons
    }
    try:
        # The repository's default limit is a page for a review session; this
        # is a count across the whole sky, so it asks for the ceiling the map
        # can draw. Above it the badge under-reports rather than misleads.
        cards = review_repo.list_due_cards(
            student_id, now=datetime.now(timezone.utc), limit=REVIEW_COUNT_CEILING
        )
    except Exception:  # noqa: BLE001
        return {}
    counts: dict[str, int] = {}
    for card in cards:
        unit_id = unit_of_lesson.get(str(card.get("lesson_id") or ""), "")
        if unit_id:
            counts[unit_id] = counts.get(unit_id, 0) + 1
    return counts


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
    )
