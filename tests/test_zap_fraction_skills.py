"""The three skills the ZAP fractions batch needs are registered, and stay out of sight
until an exercise trains them.

The batch (#106) maps three of its five knowledge cards to skills the vocabulary did
not have, so a lesson carrying them failed draft validation. They hang under
`brueche-u2`, the unit the batch maps all five cards to.

The star map draws a speck for every skill of a unit. Registered ahead of the
exercises, each new skill would have been a speck no student could light; a skill
point now appears once an active exercise trains it. Every skill registered before
these had exercises, so nothing already on the map moves.
"""

from __future__ import annotations

import pytest

from fakes.dynamodb import FakeTable
from stoa.services import curriculum_service, knowledge_mastery_service
from test_curriculum_publish_projection import (
    LESSON_ID,
    _exercise,
    _payload,
    _publish,
    install_seeded_table,
)


NEW_SKILLS = (
    "brueche-ganzes-bestimmen",
    "brueche-anteilsbruch-bestimmen",
    "brueche-rechenreihenfolge",
)


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def test_the_batch_skills_belong_to_the_unit_the_batch_maps_them_to() -> None:
    owners = curriculum_service.skill_unit_ids(subject_id="math")
    assert {skill: owners.get(skill) for skill in NEW_SKILLS} == dict.fromkeys(
        NEW_SKILLS, "brueche-u2"
    )
    for locale in ("de", "en", "fr", "it"):
        names = {
            item["id"]: item["name"]
            for item in curriculum_service.list_skills(locale=locale)["items"]
        }
        assert all(names[skill] and names[skill] != skill for skill in NEW_SKILLS)


def _skill_points(table: FakeTable) -> dict[str, bool]:
    states = knowledge_mastery_service.skill_states("student-1", subject_id="math")
    return {skill: state.lit for skill, state in states.items() if state.unit_id == "brueche-u2"}


def test_a_skill_point_appears_once_an_exercise_trains_it_and_lights_when_answered(
    table: FakeTable,
) -> None:
    before = _skill_points(table)
    assert "brueche-addieren" in before
    assert not set(NEW_SKILLS) & set(before)

    _publish(_payload(_exercise(1, skills=["brueche-ganzes-bestimmen"])))

    after = _skill_points(table)
    assert after["brueche-ganzes-bestimmen"] is False
    assert "brueche-rechenreihenfolge" not in after

    table.seed(
        {
            "PK": "ATTEMPTS#student-1",
            "SK": "ATTEMPT#0001",
            "student_id": "student-1",
            "challenge_id": f"{LESSON_ID}-q01",
            "lesson_id": LESSON_ID,
            "correct": True,
        }
    )
    assert _skill_points(table)["brueche-ganzes-bestimmen"] is True
