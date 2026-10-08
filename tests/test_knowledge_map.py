"""The star map read model (#59): what `GET /practice/knowledge-map` answers.

Against the pure core, with no table double — same reason as the mastery
judgement it sits on: a read model verified through a double is verified
against whatever that double permits.
"""

from __future__ import annotations

import math
from typing import Any

from stoa.services import knowledge_map_service as km
from stoa.services import knowledge_mastery_service as mastery


def judged(
    unit_id: str,
    state: mastery.LearningState,
    *,
    topic_id: str = "t1",
    subject_id: str = "math",
    lesson_count: int = 1,
    lessons_done: int = 0,
) -> mastery.UnitMastery:
    return mastery.UnitMastery(
        unit_id=unit_id,
        topic_id=topic_id,
        subject_id=subject_id,
        state=state,
        progress=lessons_done / lesson_count if lesson_count else 0.0,
        unmet_exercises=0,
        lesson_count=lesson_count,
        lessons_done=lessons_done,
        next_lesson=None,
    )


def catalog(
    *,
    subjects: list[dict[str, Any]] | None = None,
    topics: list[dict[str, Any]] | None = None,
    units: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "subjects": subjects if subjects is not None else [{"id": "math", "name": "Mathematik", "order": 0}],
        "topics": topics if topics is not None else [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
        "units": units if units is not None else [{"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 0}],
        "lessons": [],
    }


def build(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "subject_id": "math",
        "catalog": catalog(),
        "unit_states": {"u1": judged("u1", mastery.LearningState.READY)},
        "review_due_by_unit": {},
        "streak_days": 0,
        "score": 0,
        "enrolled_subject_ids": frozenset({"math"}),
    }
    base.update(overrides)
    return km.build_map(**base)


def test_a_unit_with_no_active_lesson_is_never_sent() -> None:
    """The model's contract. A star with no chapter behind it is a dead end."""
    result = build(unit_states={"u1": judged("u1", mastery.LearningState.READY, lesson_count=0)})

    assert result["stars"] == []
    assert result["summary"]["total"] == 0


def test_a_unit_the_judgement_says_nothing_about_is_not_sent() -> None:
    result = build(unit_states={})

    assert result["stars"] == []


def test_each_star_carries_the_state_the_judgement_gave_it() -> None:
    result = build(unit_states={"u1": judged("u1", mastery.LearningState.LIT, lessons_done=1)})

    assert [star["state"] for star in result["stars"]] == ["lit"]
    assert result["stars"][0]["progress"] == 1.0
    assert result["summary"]["lit"] == 1


def test_a_galaxy_counts_only_its_own_stars() -> None:
    result = build(
        subject_id="math",
        catalog=catalog(
            subjects=[
                {"id": "math", "name": "Mathematik", "order": 0},
                {"id": "physics", "name": "Physik", "order": 1},
            ],
            topics=[
                {"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0},
                {"id": "t2", "subjectId": "physics", "title": "Optik", "order": 0},
            ],
            units=[
                {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 0},
                {"id": "u2", "subjectId": "physics", "topicId": "t2", "title": "Brechung", "order": 0},
            ],
        ),
        unit_states={
            "u1": judged("u1", mastery.LearningState.LIT, lessons_done=1),
            "u2": judged("u2", mastery.LearningState.READY, topic_id="t2", subject_id="physics"),
        },
        enrolled_subject_ids=frozenset({"math"}),
    )

    galaxies = {galaxy["subjectId"]: galaxy for galaxy in result["galaxies"]}
    assert (galaxies["math"]["lit"], galaxies["math"]["total"]) == (1, 1)
    assert (galaxies["physics"]["lit"], galaxies["physics"]["total"]) == (0, 1)
    # A subject the student does not take is still in the sky, drawn dimmed.
    assert galaxies["physics"]["enrolled"] is False
    assert galaxies["math"]["enrolled"] is True
    # The summary follows the galaxy in focus, not the whole sky.
    assert result["summary"]["total"] == 1


def test_at_most_one_recommendation_per_subject_and_it_prefers_an_unfinished_one() -> None:
    result = build(
        catalog=catalog(
            units=[
                {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "A", "order": 0},
                {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "B", "order": 1},
            ]
        ),
        unit_states={
            "u1": judged("u1", mastery.LearningState.READY),
            "u2": judged("u2", mastery.LearningState.IN_PROGRESS, lessons_done=1, lesson_count=2),
        },
    )

    recommended = [star["unitId"] for star in result["stars"] if star["recommendation"]]
    assert recommended == ["u2"], "what is already begun comes before what is not"
    assert result["stars"][1]["recommendation"] == {"source": "system"}


def test_a_sky_with_nothing_begun_recommends_the_first_one_that_is_open() -> None:
    result = build(
        catalog=catalog(
            units=[
                {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "A", "order": 0},
                {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "B", "order": 1},
            ]
        ),
        unit_states={
            "u1": judged("u1", mastery.LearningState.READY),
            "u2": judged("u2", mastery.LearningState.READY),
        },
    )

    assert [star["unitId"] for star in result["stars"] if star["recommendation"]] == ["u1"]


def test_a_fully_lit_subject_recommends_nothing() -> None:
    result = build(unit_states={"u1": judged("u1", mastery.LearningState.LIT, lessons_done=1)})

    assert [star for star in result["stars"] if star["recommendation"]] == []


def test_every_star_sits_inside_the_sky_and_lands_in_the_same_place_twice() -> None:
    first = build()
    second = build()

    star = first["stars"][0]
    assert 0.0 <= star["x"] <= 1.0 and 0.0 <= star["y"] <= 1.0
    assert (star["x"], star["y"]) == (second["stars"][0]["x"], second["stars"][0]["y"]), (
        "the same sky must come back in the same arrangement; a map that "
        "rearranges itself between requests cannot be navigated"
    )


def test_two_stars_of_one_nebula_do_not_land_on_top_of_each_other() -> None:
    result = build(
        catalog=catalog(
            units=[
                {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "A", "order": 0},
                {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "B", "order": 1},
            ]
        ),
        unit_states={
            "u1": judged("u1", mastery.LearningState.READY),
            "u2": judged("u2", mastery.LearningState.READY),
        },
    )

    a, b = result["stars"]
    # `!=` is not enough: audit measured two stars 0.001 apart in a 50-star
    # nebula, which is 1.7 px on a 1600 px canvas — distinct numbers, one dot
    # on screen. Assert a distance a reader could actually resolve.
    distance = math.dist((a["x"], a["y"]), (b["x"], b["y"]))
    assert distance > 0.004, f"two stars {distance:.5f} apart read as one"


def test_nebulae_of_one_subject_stay_together_along_the_band() -> None:
    """#119: one sky, galaxy by galaxy. Interleaved subjects would not read
    as galaxies at all."""
    result = build(
        catalog=catalog(
            subjects=[
                {"id": "math", "name": "Mathematik", "order": 0},
                {"id": "physics", "name": "Physik", "order": 1},
            ],
            topics=[
                {"id": "m1", "subjectId": "math", "title": "A", "order": 0},
                {"id": "p1", "subjectId": "physics", "title": "C", "order": 0},
                {"id": "m2", "subjectId": "math", "title": "B", "order": 1},
            ],
            units=[],
        ),
        unit_states={},
    )

    order = [nebula["subjectId"] for nebula in result["nebulae"]]
    assert order == ["math", "math", "physics"]
    assert [nebula["order"] for nebula in result["nebulae"]] == [0, 1, 2]


def test_the_gaps_that_are_not_built_yet_are_empty_rather_than_invented() -> None:
    """Prerequisites (stoa-backend#56) and skills (#58) have no data source.

    Returning a guess would put locks on the map that nothing can justify,
    and the lock is the one state a student cannot work around.
    """
    result = build()

    assert result["prerequisites"] == []
    assert result["stars"][0]["skills"] == []


def test_review_counts_ride_along_without_changing_the_state() -> None:
    """#9 point 9: a due review is a marker over a state, never a state."""
    result = build(
        unit_states={"u1": judged("u1", mastery.LearningState.LIT, lessons_done=1)},
        review_due_by_unit={"u1": 3},
    )

    assert result["stars"][0]["reviewDue"] == 3
    assert result["stars"][0]["state"] == "lit"


def test_the_streak_comes_from_the_student_not_the_subject() -> None:
    result = build(streak_days=7)

    assert result["summary"]["streakDays"] == 7


def test_an_empty_sky_answers_with_empty_lists_not_an_error() -> None:
    result = build(
        catalog=catalog(subjects=[], topics=[], units=[]),
        unit_states={},
        enrolled_subject_ids=frozenset(),
    )

    assert result["galaxies"] == [] and result["nebulae"] == [] and result["stars"] == []
    assert result["summary"]["total"] == 0


def test_the_recommendation_follows_the_chapter_order_not_the_spelling_of_its_id() -> None:
    """Found by audit on the real seed: `geometrie` sorts before `gleichungen`.

    A student who finished chapter 1 was sent to chapter 3, past an untouched
    chapter 2 — on the one affordance the student's home screen has.
    """
    chapters = [("brueche", 1), ("gleichungen", 2), ("geometrie", 3)]
    result = build(
        catalog=catalog(
            topics=[
                {"id": name, "subjectId": "math", "title": name, "order": order}
                for name, order in chapters
            ],
            units=[
                {"id": f"{name}-u1", "subjectId": "math", "topicId": name, "title": name, "order": 0}
                for name, _ in chapters
            ],
        ),
        unit_states={
            "brueche-u1": judged("brueche-u1", mastery.LearningState.LIT, topic_id="brueche", lessons_done=1),
            "gleichungen-u1": judged("gleichungen-u1", mastery.LearningState.READY, topic_id="gleichungen"),
            "geometrie-u1": judged("geometrie-u1", mastery.LearningState.READY, topic_id="geometrie"),
        },
    )

    assert [star["unitId"] for star in result["stars"]] == [
        "brueche-u1",
        "gleichungen-u1",
        "geometrie-u1",
    ], "stars follow the band, which follows topic.order"
    assert [star["unitId"] for star in result["stars"] if star["recommendation"]] == [
        "gleichungen-u1"
    ]
