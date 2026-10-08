"""What the map draws now that the data behind it exists (#56, #58, #60).

The sky had one shape to show: everything `ready`. Prerequisites were stored
but nobody read them, exercises carried no skills, and the coordinates were
made up on the way out. Nine of ten knowledge points looked identical, so the
legend promised six states and the map could draw one.
"""

from __future__ import annotations

from typing import Any

from stoa.services import knowledge_map_service, knowledge_mastery_service

LIT = knowledge_mastery_service.LearningState.LIT
READY = knowledge_mastery_service.LearningState.READY
LOCKED = knowledge_mastery_service.LearningState.LOCKED


def _unit(unit_id: str, *, order: int, before: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "id": unit_id,
        "subjectId": "math",
        "topicId": "brueche",
        "title": unit_id,
        "order": order,
        "prerequisiteUnitIds": before or [],
        **extra,
    }


def _catalog(*units: dict[str, Any]) -> dict[str, Any]:
    return {
        "subjects": [{"id": "math", "name": "Mathematik", "order": 1}],
        "topics": [{"id": "brueche", "subjectId": "math", "title": "Brüche", "order": 1}],
        "units": list(units),
        "lessons": [],
    }


def _mastery(unit_id: str, state: knowledge_mastery_service.LearningState) -> knowledge_mastery_service.UnitMastery:
    return knowledge_mastery_service.UnitMastery(
        unit_id, "brueche", "math", state, 1.0 if state is LIT else 0.0, 0, 1, 0, None
    )


def _map(units: list[dict[str, Any]], states: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return knowledge_map_service.build_map(
        subject_id="math",
        catalog=_catalog(*units),
        unit_states=states,
        review_due_by_unit={},
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset({"math"}),
        **extra,
    )


def test_what_has_to_come_first_is_drawn_as_an_edge() -> None:
    units = [_unit("u1", order=1), _unit("u2", order=2, before=["u1"])]

    result = _map(units, {"u1": _mastery("u1", LIT), "u2": _mastery("u2", READY)})

    assert result["prerequisites"] == [{"from": "u1", "to": "u2"}]


def test_an_edge_to_a_unit_this_map_does_not_hold_is_not_drawn() -> None:
    # A line to nowhere is worse than no line: the student would read it as a
    # point they have not found yet.
    units = [_unit("u1", order=1, before=["archived-unit"])]

    result = _map(units, {"u1": _mastery("u1", READY)})

    assert result["prerequisites"] == []


def test_a_unit_is_not_its_own_prerequisite() -> None:
    units = [_unit("u1", order=1, before=["u1"])]

    result = _map(units, {"u1": _mastery("u1", READY)})

    assert result["prerequisites"] == []


def test_a_skill_point_reaches_the_star_it_belongs_to() -> None:
    units = [_unit("u1", order=1)]
    skills = {
        "brueche-kuerzen": knowledge_mastery_service.SkillMastery("brueche-kuerzen", "u1", True),
        "brueche-erweitern": knowledge_mastery_service.SkillMastery("brueche-erweitern", "u1", False),
        "elsewhere": knowledge_mastery_service.SkillMastery("elsewhere", "u2", True),
    }

    result = _map(units, {"u1": _mastery("u1", READY)}, skill_states=skills)

    star = result["stars"][0]
    assert [skill["skillId"] for skill in star["skills"]] == ["brueche-erweitern", "brueche-kuerzen"]
    assert [skill["lit"] for skill in star["skills"]] == [False, True]
    assert all(skill["name"] for skill in star["skills"])


def test_a_star_with_no_skills_says_so_rather_than_breaking() -> None:
    result = _map([_unit("u1", order=1)], {"u1": _mastery("u1", READY)})

    assert result["stars"][0]["skills"] == []


def test_the_offline_coordinates_are_used_when_the_row_has_them() -> None:
    # Until #60's script runs, the map arranges the stars itself. Once a row
    # has been laid out, that arrangement must not override it.
    units = [_unit("u1", order=1, x=0.25, y=0.75)]

    result = _map(units, {"u1": _mastery("u1", READY)})

    assert (result["stars"][0]["x"], result["stars"][0]["y"]) == (0.25, 0.75)


def test_a_row_without_coordinates_still_gets_a_place() -> None:
    result = _map([_unit("u1", order=1)], {"u1": _mastery("u1", READY)})

    star = result["stars"][0]
    assert 0.0 <= star["x"] <= 1.0 and 0.0 <= star["y"] <= 1.0


# ── the lock itself ────────────────────────────────────────────────────────


def _lesson(lesson_id: str, unit_id: str) -> dict[str, Any]:
    return {"id": lesson_id, "unitId": unit_id, "subjectId": "math", "topicId": "brueche"}


def _states(monkeypatch, *, done: set[str], right: set[str]) -> dict[str, Any]:
    catalog = _catalog(_unit("u1", order=1), _unit("u2", order=2, before=["u1"]))
    catalog["lessons"] = [_lesson("l1", "u1"), _lesson("l2", "u2")]
    monkeypatch.setattr(knowledge_mastery_service, "_active_exercise_ids", lambda lesson_id: [f"{lesson_id}-c1"])
    monkeypatch.setattr(knowledge_mastery_service, "_completed_lesson_ids", lambda *a, **k: frozenset(done))
    monkeypatch.setattr(knowledge_mastery_service, "_exercises_answered_right", lambda *a, **k: frozenset(right))
    return knowledge_mastery_service.unit_states("student-1", catalog=catalog)


def test_a_knowledge_point_waits_for_the_one_before_it(monkeypatch) -> None:
    # The whole reason #56 exists. Before it the map had nothing to lock on,
    # so every point said "ready" and the four states were one state.
    states = _states(monkeypatch, done=set(), right=set())

    assert states["u1"].state is READY
    assert states["u2"].state is LOCKED


def test_finishing_the_one_before_it_opens_the_next(monkeypatch) -> None:
    states = _states(monkeypatch, done={"l1"}, right={"l1-c1"})

    assert states["u1"].state is LIT
    assert states["u2"].state is READY


def test_lighting_does_not_wait_for_a_lock(monkeypatch) -> None:
    # A student who finished a point before anything was wired must not have
    # it put out by a prerequisite appearing afterwards.
    states = _states(monkeypatch, done={"l1", "l2"}, right={"l1-c1", "l2-c1"})

    assert states["u1"].state is LIT
    assert states["u2"].state is LIT


def test_a_point_with_nothing_before_it_is_never_locked(monkeypatch) -> None:
    # Locking comes only from a stated relation, never from position in an
    # order (stoa-frontend#9).
    states = _states(monkeypatch, done=set(), right=set())

    assert states["u1"].state is not LOCKED


# ── the catalog has to carry the coordinates for the map to use them ───────


def test_the_catalog_carries_a_unit_s_coordinates() -> None:
    from decimal import Decimal

    from stoa.services import curriculum_service

    built = curriculum_service._build_unit(
        {
            "unit_id": "u1",
            "subject_id": "math",
            "topic_id": "brueche",
            "title": "u1",
            # The table hands numbers back as Decimal, which a float check
            # written against `float` alone would drop on the floor.
            "x": Decimal("0.25"),
            "y": Decimal("0.75"),
            "layout_version": "L3",
        }
    )

    assert (built["x"], built["y"]) == (0.25, 0.75)
    assert built["layoutVersion"] == "L3"


def test_the_catalog_carries_a_nebula_s_centre_and_radius() -> None:
    from stoa.services import curriculum_service

    built = curriculum_service._build_topic(
        {"topic_id": "brueche", "subject_id": "math", "title": "Brüche", "x": 0.4, "y": 0.6, "radius": 0.12}
    )

    assert (built["x"], built["y"], built["radius"]) == (0.4, 0.6, 0.12)


def test_a_row_that_has_not_been_laid_out_carries_no_coordinates() -> None:
    from stoa.services import curriculum_service

    built = curriculum_service._build_unit(
        {"unit_id": "u1", "subject_id": "math", "topic_id": "brueche", "title": "u1"}
    )

    assert "x" not in built and "y" not in built and "layoutVersion" not in built
