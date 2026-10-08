"""The judgement the star map draws a knowledge point by (stoa-frontend#9, #57).

Every test here runs against the pure core. No table double appears in this
file on purpose: the judgement is a function of facts, and a judgement tested
through a double is a judgement tested against whatever that double happens to
permit. Eight defects in this repository came in that way.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.services import knowledge_mastery_service as mastery


def unit(unit_id: str = "unit-1") -> dict[str, Any]:
    return {"id": unit_id, "topicId": "topic-1", "subjectId": "math"}


def lesson(lesson_id: str, title: str = "") -> dict[str, Any]:
    return {"id": lesson_id, "unitId": "unit-1", "title": title or lesson_id}


def judge(
    *,
    lessons: list[dict[str, Any]],
    exercises: dict[str, list[str]],
    completed: set[str] = frozenset(),
    right: set[str] = frozenset(),
    unlit_prerequisites: int = 0,
) -> mastery.UnitMastery:
    return mastery.judge_unit(
        unit=unit(),
        lessons=lessons,
        exercises_by_lesson=exercises,
        completed_lesson_ids=frozenset(completed),
        exercises_answered_right=frozenset(right),
        unlit_prerequisites=unlit_prerequisites,
    )


def test_a_unit_nobody_has_touched_is_ready() -> None:
    result = judge(lessons=[lesson("l1")], exercises={"l1": ["e1", "e2"]})

    assert result.state is mastery.LearningState.READY
    assert result.progress == 0.0
    assert result.unmet_exercises == 2
    assert result.next_lesson is not None and result.next_lesson.lesson_id == "l1"


def test_every_lesson_done_and_every_exercise_right_lights_it() -> None:
    result = judge(
        lessons=[lesson("l1"), lesson("l2")],
        exercises={"l1": ["e1"], "l2": ["e2"]},
        completed={"l1", "l2"},
        right={"e1", "e2"},
    )

    assert result.state is mastery.LearningState.LIT
    assert result.progress == 1.0
    assert result.unmet_exercises == 0
    assert result.next_lesson is None


def test_finishing_every_lesson_with_a_question_still_wrong_does_not_light_it() -> None:
    """The whole reason the judgement is two-part (#9).

    A lesson can be completed with a wrong answer. Lighting on lesson
    completion alone would claim knowledge the evidence does not support, and
    it is the half that is easy to drop by accident.
    """
    result = judge(
        lessons=[lesson("l1"), lesson("l2")],
        exercises={"l1": ["e1"], "l2": ["e2"]},
        completed={"l1", "l2"},
        right={"e1"},
    )

    assert result.state is mastery.LearningState.IN_PROGRESS
    assert result.progress == 1.0, "every lesson is done; it is the exercise that is unmet"
    assert result.unmet_exercises == 1


def test_answering_everything_right_without_finishing_the_lessons_does_not_light_it() -> None:
    """The mirror of the test above: the other half, dropped on its own."""
    result = judge(
        lessons=[lesson("l1"), lesson("l2")],
        exercises={"l1": ["e1"], "l2": ["e2"]},
        completed={"l1"},
        right={"e1", "e2"},
    )

    assert result.state is mastery.LearningState.IN_PROGRESS
    assert result.unmet_exercises == 0
    assert result.lessons_done == 1 and result.lesson_count == 2


def test_one_lesson_done_out_of_three_is_in_progress_at_a_third() -> None:
    result = judge(
        lessons=[lesson("l1"), lesson("l2"), lesson("l3")],
        exercises={"l1": ["e1"], "l2": ["e2"], "l3": ["e3"]},
        completed={"l1"},
        right={"e1"},
    )

    assert result.state is mastery.LearningState.IN_PROGRESS
    assert result.progress == pytest.approx(1 / 3)
    assert result.next_lesson is not None and result.next_lesson.lesson_id == "l2"


def test_an_unlit_prerequisite_locks_a_unit_nobody_has_started() -> None:
    result = judge(
        lessons=[lesson("l1")],
        exercises={"l1": ["e1"]},
        unlit_prerequisites=1,
    )

    assert result.state is mastery.LearningState.LOCKED


def test_a_prerequisite_appearing_later_does_not_strand_a_student_already_inside() -> None:
    """Locking someone out of what they have started would lose their place.

    Prerequisites are maintained by hand (stoa-backend#56), so one can appear
    above a unit a student is already working through.
    """
    result = judge(
        lessons=[lesson("l1"), lesson("l2")],
        exercises={"l1": ["e1"], "l2": ["e2"]},
        completed={"l1"},
        right={"e1"},
        unlit_prerequisites=1,
    )

    assert result.state is mastery.LearningState.IN_PROGRESS


def test_nothing_is_locked_while_no_prerequisites_are_stored() -> None:
    """#9 point 7: no prerequisite edge, no lock. True for the whole platform
    until stoa-backend#56 lands, so it is the state the first star map ships in."""
    result = judge(lessons=[lesson("l1")], exercises={"l1": ["e1"]}, unlit_prerequisites=0)

    assert result.state is not mastery.LearningState.LOCKED


def test_a_unit_with_no_active_lesson_is_never_lit() -> None:
    """Units with no active lesson are never sent to the map, but a judgement
    that lit them on an empty set would light every empty unit on the platform."""
    result = judge(lessons=[], exercises={})

    assert result.state is mastery.LearningState.READY
    assert result.progress == 0.0
    assert result.next_lesson is None


def test_a_lesson_with_no_exercises_lights_on_completion_alone() -> None:
    result = judge(lessons=[lesson("l1")], exercises={"l1": []}, completed={"l1"})

    assert result.state is mastery.LearningState.LIT


def test_exercises_answered_right_in_another_unit_do_not_count_here() -> None:
    result = judge(
        lessons=[lesson("l1")],
        exercises={"l1": ["e1"], "somewhere-else": ["e9"]},
        completed={"l1"},
        right={"e9"},
    )

    assert result.state is mastery.LearningState.IN_PROGRESS
    assert result.unmet_exercises == 1


def test_the_next_lesson_is_the_first_one_not_done_in_order() -> None:
    result = judge(
        lessons=[lesson("l1"), lesson("l2"), lesson("l3")],
        exercises={},
        completed={"l1", "l3"},
    )

    assert result.next_lesson is not None
    assert result.next_lesson.lesson_id == "l2"


def test_the_states_are_the_four_the_design_decided_on() -> None:
    """A fifth state, or a renamed one, silently changes what the map draws."""
    assert [state.value for state in mastery.LearningState] == [
        "lit",
        "in_progress",
        "ready",
        "locked",
    ]


def test_lit_unit_ids_names_only_the_lit_ones() -> None:
    states = [
        judge(lessons=[lesson("l1")], exercises={"l1": []}, completed={"l1"}),
        judge(lessons=[lesson("l1")], exercises={"l1": ["e1"]}),
    ]

    assert mastery.lit_unit_ids(states) == frozenset({"unit-1"})
