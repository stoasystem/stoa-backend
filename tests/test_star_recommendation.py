"""Which star the map recommends: the one that follows the student (#164, stoa-frontend#474).

Against the pure `build_map`, as the rest of the read model's tests are. Per
subject, at most one, only in a subject the student takes:

1. a star in progress, the one with the latest evidence (ties: earlier in the
   course), whatever its prerequisites - `in_progress`;
2. else after the latest lighting - this subject's own, or another subject's
   whose successor is here (ties: furthest in the course; this subject's own
   over another's): its successor on the frontier, else the next frontier star
   after it in the course, wrapping round - `after_lit`;
3. else the first frontier star - `start`.

The frontier is what is not lit and has every prerequisite lit.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.db import table as db_table
from stoa.services import knowledge_map_service as km
from stoa.services import knowledge_mastery_service as mastery

LIT = mastery.LearningState.LIT
READY = mastery.LearningState.READY
IN_PROGRESS = mastery.LearningState.IN_PROGRESS


def judged(
    unit_id: str,
    state: mastery.LearningState,
    *,
    subject_id: str = "math",
    unlit: tuple[str, ...] = (),
) -> mastery.UnitMastery:
    return mastery.UnitMastery(
        unit_id=unit_id,
        topic_id="t-" + subject_id,
        subject_id=subject_id,
        state=state,
        progress=1.0 if state is LIT else 0.0,
        unmet_exercises=0,
        lesson_count=1,
        lessons_done=1 if state is LIT else 0,
        next_lesson=None,
        unlit_prerequisite_ids=unlit,
    )


def unit(unit_id: str, order: int, *, subject_id: str = "math", before: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": unit_id,
        "subjectId": subject_id,
        "topicId": "t-" + subject_id,
        "title": unit_id,
        "order": order,
        "prerequisiteUnitIds": before or [],
    }


def fact(unit_id: str, lit_at: str, source: mastery.LitSource = mastery.LitSource.OBSERVED) -> mastery.LitFact:
    return mastery.LitFact(unit_id=unit_id, lit_at=lit_at, source=source)


def build(
    units: list[dict[str, Any]],
    states: dict[str, mastery.UnitMastery],
    *,
    facts: list[mastery.LitFact] = (),
    evidence: dict[str, str] | None = None,
    enrolled: frozenset[str] = frozenset({"math", "physics"}),
) -> dict[str, Any]:
    subjects = sorted({item["subjectId"] for item in units})
    return km.build_map(
        subject_id="math",
        catalog={
            "subjects": [{"id": sid, "name": sid, "order": index} for index, sid in enumerate(subjects)],
            "topics": [
                {"id": "t-" + sid, "subjectId": sid, "title": sid, "order": 0} for sid in subjects
            ],
            "units": units,
            "lessons": [],
        },
        unit_states=states,
        review_due_by_unit={},
        streak_days=0,
        score=0,
        enrolled_subject_ids=enrolled,
        lit_facts={item.unit_id: item for item in facts},
        last_evidence_by_unit=evidence or {},
    )


def recommended(result: dict[str, Any], subject_id: str = "math") -> list[tuple[str, dict]]:
    subject_of = {item["topicId"]: item["subjectId"] for item in result["nebulae"]}
    return [
        (star["unitId"], star["recommendation"])
        for star in result["stars"]
        if star["recommendation"] and subject_of[star["nebulaId"]] == subject_id
    ]


# ── 1. what is in progress ───────────────────────────────────────────────────


def test_the_star_in_progress_with_the_latest_evidence_is_recommended() -> None:
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2)],
        {"a": judged("a", IN_PROGRESS), "b": judged("b", IN_PROGRESS), "c": judged("c", READY)},
        evidence={"a": "2026-11-01T10:00:00+00:00", "b": "2026-11-01T11:00:00+00:00"},
    )

    assert recommended(result) == [
        ("b", {"source": "system", "reason": "in_progress", "relatedUnitId": None})
    ]


def test_in_progress_ties_go_to_the_earlier_star_in_the_course() -> None:
    same = "2026-11-01T10:00:00+00:00"
    result = build(
        [unit("a", 0), unit("b", 1)],
        {"a": judged("a", IN_PROGRESS), "b": judged("b", IN_PROGRESS)},
        evidence={"a": same, "b": same},
    )

    assert [item for item, _ in recommended(result)] == ["a"]


def test_a_star_in_progress_is_recommended_even_behind_an_unlit_prerequisite() -> None:
    result = build(
        [unit("a", 0), unit("b", 1, before=["a"])],
        {"a": judged("a", READY), "b": judged("b", IN_PROGRESS, unlit=("a",))},
        evidence={"b": "2026-11-01T10:00:00+00:00"},
    )

    assert recommended(result) == [
        ("b", {"source": "system", "reason": "in_progress", "relatedUnitId": None})
    ]


# ── 2. after the latest lighting ─────────────────────────────────────────────


def test_after_a_lighting_its_successor_on_the_frontier_comes_first() -> None:
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2, before=["a"])],
        {"a": judged("a", LIT), "b": judged("b", READY), "c": judged("c", READY)},
        facts=[fact("a", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == [
        ("c", {"source": "system", "reason": "after_lit", "relatedUnitId": "a"})
    ]


def test_of_several_successors_the_earliest_in_the_course_is_taken() -> None:
    result = build(
        [unit("a", 0), unit("d", 3, before=["a"]), unit("c", 2, before=["a"])],
        {"a": judged("a", LIT), "c": judged("c", READY), "d": judged("d", READY)},
        facts=[fact("a", "2026-11-01T10:00:00+00:00")],
    )

    assert [item for item, _ in recommended(result)] == ["c"]


def test_a_successor_off_the_frontier_is_passed_over_for_the_next_in_the_course() -> None:
    # `c` follows `a` but also needs `x`, which is not lit: not on the frontier.
    result = build(
        [unit("a", 0), unit("x", 1), unit("b", 2), unit("c", 3, before=["a", "x"])],
        {
            "a": judged("a", LIT),
            "x": judged("x", LIT),
            "b": judged("b", READY),
            "c": judged("c", READY, unlit=("y",)),
        },
        facts=[fact("a", "2026-11-01T11:00:00+00:00"), fact("x", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == [
        ("b", {"source": "system", "reason": "after_lit", "relatedUnitId": "a"})
    ]


def test_finishing_late_in_the_course_does_not_send_the_student_back_to_the_start() -> None:
    """The case that opened #164: trigonometry done, integers recommended."""
    result = build(
        [unit("integers", 0), unit("fractions", 1), unit("trigonometry", 2), unit("vectors", 3)],
        {
            "integers": judged("integers", READY),
            "fractions": judged("fractions", READY),
            "trigonometry": judged("trigonometry", LIT),
            "vectors": judged("vectors", READY),
        },
        facts=[fact("trigonometry", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == [
        ("vectors", {"source": "system", "reason": "after_lit", "relatedUnitId": "trigonometry"})
    ]


def test_at_the_end_of_the_course_it_wraps_round_to_the_start() -> None:
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2)],
        {"a": judged("a", READY), "b": judged("b", READY), "c": judged("c", LIT)},
        facts=[fact("c", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == [
        ("a", {"source": "system", "reason": "after_lit", "relatedUnitId": "c"})
    ]


def test_the_latest_lighting_decides_whatever_its_place() -> None:
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2), unit("d", 3)],
        {"a": judged("a", LIT), "b": judged("b", READY), "c": judged("c", LIT), "d": judged("d", READY)},
        facts=[fact("a", "2026-11-01T12:00:00+00:00"), fact("c", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == [
        ("b", {"source": "system", "reason": "after_lit", "relatedUnitId": "a"})
    ]


def test_lightings_at_the_same_moment_go_to_the_furthest_in_the_course() -> None:
    same = "2026-11-01T10:00:00+00:00"
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2), unit("d", 3)],
        {"a": judged("a", LIT), "b": judged("b", READY), "c": judged("c", LIT), "d": judged("d", READY)},
        facts=[fact("a", same), fact("c", same)],
    )

    assert recommended(result) == [
        ("d", {"source": "system", "reason": "after_lit", "relatedUnitId": "c"})
    ]


def test_a_backfilled_lighting_counts_too() -> None:
    result = build(
        [unit("a", 0), unit("b", 1), unit("c", 2)],
        {"a": judged("a", READY), "b": judged("b", LIT), "c": judged("c", READY)},
        facts=[fact("b", "2026-10-01T10:00:00+00:00", mastery.LitSource.BACKFILLED)],
    )

    assert [item for item, _ in recommended(result)] == ["c"]


# ── 2b. a lighting in another subject ────────────────────────────────────────


def _two_subjects(math_lit_at: str, physics_lit_at: str) -> dict[str, Any]:
    # Physics `p1` is a prerequisite of math `m3`.
    return build(
        [
            unit("m1", 0),
            unit("m2", 1),
            unit("m3", 2, before=["p1"]),
            unit("p1", 0, subject_id="physics"),
        ],
        {
            "m1": judged("m1", LIT),
            "m2": judged("m2", READY),
            "m3": judged("m3", READY),
            "p1": judged("p1", LIT, subject_id="physics"),
        },
        facts=[fact("m1", math_lit_at), fact("p1", physics_lit_at)],
    )


def test_a_later_lighting_in_another_subject_leads_to_its_successor_here() -> None:
    result = _two_subjects("2026-11-01T10:00:00+00:00", "2026-11-01T11:00:00+00:00")

    assert recommended(result) == [
        ("m3", {"source": "system", "reason": "after_lit", "relatedUnitId": "p1"})
    ]


def test_at_the_same_moment_this_subjects_own_lighting_wins() -> None:
    same = "2026-11-01T10:00:00+00:00"
    result = _two_subjects(same, same)

    assert recommended(result) == [
        ("m2", {"source": "system", "reason": "after_lit", "relatedUnitId": "m1"})
    ]


def test_another_subjects_lighting_with_nothing_here_does_not_count() -> None:
    result = build(
        [unit("m1", 0), unit("m2", 1), unit("p1", 0, subject_id="physics")],
        {"m1": judged("m1", READY), "m2": judged("m2", READY), "p1": judged("p1", LIT, subject_id="physics")},
        facts=[fact("p1", "2026-11-01T11:00:00+00:00")],
    )

    assert recommended(result) == [
        ("m1", {"source": "system", "reason": "start", "relatedUnitId": None})
    ]


# ── 3. where to start ────────────────────────────────────────────────────────


def test_nothing_lit_starts_at_the_first_star_on_the_frontier() -> None:
    result = build(
        [unit("a", 0, before=["z"]), unit("b", 1), unit("z", 2)],
        {"a": judged("a", READY, unlit=("z",)), "b": judged("b", READY), "z": judged("z", READY)},
    )

    assert recommended(result) == [
        ("b", {"source": "system", "reason": "start", "relatedUnitId": None})
    ]


# ── what is not recommended ──────────────────────────────────────────────────


def test_a_subject_the_student_does_not_take_has_no_recommendation() -> None:
    result = build(
        [unit("a", 0), unit("b", 1)],
        {"a": judged("a", READY), "b": judged("b", READY)},
        enrolled=frozenset(),
    )

    assert recommended(result) == []


def test_a_fully_lit_subject_recommends_nothing() -> None:
    result = build(
        [unit("a", 0)],
        {"a": judged("a", LIT)},
        facts=[fact("a", "2026-11-01T10:00:00+00:00")],
    )

    assert recommended(result) == []


def test_each_subject_has_at_most_one() -> None:
    result = build(
        [unit("m1", 0), unit("m2", 1), unit("p1", 0, subject_id="physics"), unit("p2", 1, subject_id="physics")],
        {
            "m1": judged("m1", READY),
            "m2": judged("m2", READY),
            "p1": judged("p1", READY, subject_id="physics"),
            "p2": judged("p2", READY, subject_id="physics"),
        },
    )

    assert [item for item, _ in recommended(result, "math")] == ["m1"]
    assert [item for item, _ in recommended(result, "physics")] == ["p1"]


# ── the evidence it reads ────────────────────────────────────────────────────


def test_the_latest_evidence_is_an_answer_or_a_finished_lesson_never_a_self_report(monkeypatch) -> None:
    from fakes.dynamodb import FakeTable

    from stoa.services import student_evidence

    table = FakeTable()
    table.seed(
        {"PK": "ATTEMPTS#s1", "SK": "ATTEMPT#1", "unit_id": "a", "created_at": "2026-11-01T09:00:00+00:00", "correct": False},
        {"PK": "ATTEMPTS#s1", "SK": "ATTEMPT#2", "unit_id": "a", "created_at": "2026-11-01T08:00:00+00:00", "correct": True},
        {"PK": "ATTEMPTS#s1", "SK": "ATTEMPT#3", "unit_id": "b", "created_at": "2026-11-01T12:00:00+00:00", "self_reported": True},
        {"PK": "PROGRESS#s1", "SK": "LESSON#l1", "lesson_id": "l1", "unit_id": "b", "status": "completed", "completed_at": "2026-11-01T10:00:00+00:00"},
        {"PK": "PROGRESS#s1", "SK": "LESSON#l2", "lesson_id": "l2", "unit_id": "c", "status": "in_progress", "completed_at": "2026-11-01T11:00:00+00:00"},
    )
    db_table.install(table)

    assert student_evidence.for_student("s1").last_activity_by_unit == {
        "a": "2026-11-01T09:00:00+00:00",
        "b": "2026-11-01T10:00:00+00:00",
    }


def test_a_subject_taken_under_its_other_name_is_taken() -> None:
    """Progress rows say `mathematics`, the galaxy says `math`: the same subject."""
    result = build(
        [unit("a", 0), unit("b", 1)],
        {"a": judged("a", IN_PROGRESS), "b": judged("b", READY)},
        enrolled=frozenset({"mathematics"}),
    )

    assert [galaxy["enrolled"] for galaxy in result["galaxies"]] == [True]
    assert [item for item, _ in recommended(result)] == ["a"]


# ── 3. where to start, by the student's year group (#310) ────────────────────
#
# A course whose chapters carry a year, one star each unless said otherwise:
# t6 (year 6), t7 (year 7), t9a and t9b (year 9), and t-none with no year.


def _graded_unit(unit_id: str, topic_id: str, order: int, before: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": unit_id,
        "subjectId": "math",
        "topicId": topic_id,
        "title": unit_id,
        "order": order,
        "prerequisiteUnitIds": before or [],
    }


def build_graded(
    grade: str | None,
    *,
    topics: list[tuple[str, str]] = (("t6", "grade_6_primary"), ("t7", "grade_7_secondary"),
                                     ("t9a", "grade_9_secondary"), ("t9b", "grade_9_secondary")),
    units: list[dict[str, Any]] | None = None,
    lessons: list[dict[str, Any]] = (),
    states: dict[str, mastery.UnitMastery] | None = None,
    facts: list[mastery.LitFact] = (),
    evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    units = units if units is not None else [
        _graded_unit(f"{topic_id}-s1", topic_id, 0) for topic_id, _ in topics
    ]
    states = states if states is not None else {
        item["id"]: judged(item["id"], READY) for item in units
    }
    return km.build_map(
        subject_id="math",
        catalog={
            "subjects": [{"id": "math", "name": "math", "order": 0}],
            "topics": [
                {"id": topic_id, "subjectId": "math", "title": topic_id, "order": index,
                 "gradeLevel": grade_level}
                for index, (topic_id, grade_level) in enumerate(topics)
            ],
            "units": units,
            "lessons": list(lessons),
        },
        unit_states=states,
        review_due_by_unit={},
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset({"math"}),
        lit_facts={item.unit_id: item for item in facts},
        last_evidence_by_unit=evidence or {},
        student_grade=grade,
    )


def by_grade(unit_id: str) -> tuple[str, dict]:
    return (unit_id, {"source": "system", "reason": "grade", "relatedUnitId": None})


def by_start(unit_id: str) -> tuple[str, dict]:
    return (unit_id, {"source": "system", "reason": "start", "relatedUnitId": None})


def test_a_new_student_in_year_9_starts_at_the_first_star_of_year_9() -> None:
    assert recommended(build_graded("grade_9_secondary")) == [by_grade("t9a-s1")]


def test_a_year_with_no_chapter_of_its_own_starts_at_the_latest_year_before_it() -> None:
    # Year 8 has no chapter: year 7 is the latest before it.
    assert recommended(build_graded("grade_8_secondary")) == [by_grade("t7-s1")]


def test_the_first_star_of_that_year_is_taken_not_the_last_chapter_of_it() -> None:
    result = build_graded(
        "grade_9_secondary",
        units=[
            _graded_unit("t6-s1", "t6", 0),
            _graded_unit("t9a-s1", "t9a", 0),
            _graded_unit("t9a-s2", "t9a", 1),
            _graded_unit("t9b-s1", "t9b", 0),
        ],
    )
    assert recommended(result) == [by_grade("t9a-s1")]


def test_the_star_by_year_need_not_be_on_the_frontier() -> None:
    """A prerequisite is advice, not a lock (ADR 0004); the client draws the path."""
    units = [_graded_unit("t6-s1", "t6", 0), _graded_unit("t9a-s1", "t9a", 0, before=["t6-s1"])]
    result = build_graded(
        "grade_9_secondary",
        topics=[("t6", "grade_6_primary"), ("t9a", "grade_9_secondary")],
        units=units,
        states={"t6-s1": judged("t6-s1", READY), "t9a-s1": judged("t9a-s1", READY, unlit=("t6-s1",))},
    )
    assert recommended(result) == [by_grade("t9a-s1")]


def test_a_star_is_the_year_of_its_earliest_practice_set_before_its_chapters() -> None:
    """The live mathematics chapters all say year 6; their practice sets say the year
    of the knowledge points in them, which is what a star's year is."""
    units = [_graded_unit("a", "t6", 0), _graded_unit("b", "t6", 1), _graded_unit("c", "t6", 2)]
    lessons = [
        {"id": "a-1", "unitId": "a", "gradeLevel": "grade_5_primary"},
        {"id": "b-1", "unitId": "b", "gradeLevel": "grade_secondary_ii"},
        {"id": "b-2", "unitId": "b", "gradeLevel": "grade_9_secondary"},
        {"id": "c-1", "unitId": "c", "gradeLevel": ""},
    ]
    result = build_graded(
        "grade_9_secondary", topics=[("t6", "grade_6_primary")], units=units, lessons=lessons
    )
    assert recommended(result) == [by_grade("b")]
    # c says nothing in its sets and takes its chapter's year 6; a is year 5.
    assert recommended(
        build_graded("grade_6_primary", topics=[("t6", "grade_6_primary")], units=units, lessons=lessons)
    ) == [by_grade("c")]


def test_lower_secondary_with_no_year_given_starts_at_its_first_year() -> None:
    assert recommended(build_graded("grade_secondary_i")) == [by_grade("t7-s1")]


def test_upper_secondary_starts_at_the_latest_year_the_sky_has() -> None:
    """#419: a Gymnasium student is older than every chapter here, not unplaced."""
    assert recommended(build_graded("grade_secondary_ii")) == [by_grade("t9a-s1")]


def test_a_legacy_spelling_the_profile_can_read_counts_as_its_year() -> None:
    assert recommended(build_graded("Grade 6")) == [by_grade("t6-s1")]


@pytest.mark.parametrize("grade", [None, "", "   ", "14", "6. Klasse", "grade_10_secondary"])
def test_no_readable_year_starts_where_it_always_has(grade: str | None) -> None:
    assert recommended(build_graded(grade)) == [by_start("t6-s1")]


def test_a_year_before_every_chapter_starts_where_it_always_has() -> None:
    assert recommended(build_graded("grade_3_primary")) == [by_start("t6-s1")]


def test_a_subject_with_no_year_anywhere_starts_where_it_always_has() -> None:
    result = build_graded("grade_9_secondary", topics=[("t-none", ""), ("t-also-none", "")])
    assert recommended(result) == [by_start("t-none-s1")]


def test_a_star_in_progress_comes_before_the_year() -> None:
    states = {
        "t6-s1": judged("t6-s1", IN_PROGRESS),
        "t7-s1": judged("t7-s1", READY),
        "t9a-s1": judged("t9a-s1", READY),
        "t9b-s1": judged("t9b-s1", READY),
    }
    assert [item for item, _ in recommended(build_graded("grade_9_secondary", states=states))] == ["t6-s1"]
    assert recommended(build_graded("grade_9_secondary", states=states)) == recommended(
        build_graded(None, states=states)
    )


def test_a_lighting_comes_before_the_year() -> None:
    states = {
        "t6-s1": judged("t6-s1", LIT),
        "t7-s1": judged("t7-s1", READY),
        "t9a-s1": judged("t9a-s1", READY),
        "t9b-s1": judged("t9b-s1", READY),
    }
    facts = [fact("t6-s1", "2026-11-01T10:00:00+00:00")]
    with_year = recommended(build_graded("grade_9_secondary", states=states, facts=facts))
    assert with_year == [("t7-s1", {"source": "system", "reason": "after_lit", "relatedUnitId": "t6-s1"})]
    assert with_year == recommended(build_graded(None, states=states, facts=facts))
