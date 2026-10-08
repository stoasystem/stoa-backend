"""Skill points: the vocabulary, its unit ownership, and lighting (#58).

stoa-frontend#9 point 12 decided a skill point is an exercise's skill and that
every skill hangs under exactly one knowledge point. Both halves are checked
here: the seeded exercises must carry skills, and no skill may be reachable
from two units, because a skill drawn under two stars is two stars claiming the
same evidence.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from fakes.dynamodb import FakeTable
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from scripts import backfill_exercise_skills as backfill
from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.routers import admin
from stoa.services import curriculum_ops_service, curriculum_service, curriculum_translations
from stoa.services import knowledge_mastery_service as mastery


def _seeded() -> tuple[list[dict], list[dict], list[dict]]:
    units: list[dict] = []
    lessons: list[dict] = []
    challenges: list[dict] = []
    for build in [
        seed_practice._brueche_data,
        seed_practice._gleichungen_data,
        seed_practice._geometrie_data,
        seed_practice._prozent_data,
        seed_practice._textaufgaben_data,
    ]:
        _topic, topic_units, topic_lessons, topic_challenges = build()
        units.extend(topic_units)
        lessons.extend(topic_lessons)
        challenges.extend(topic_challenges)
    return units, lessons, challenges


# ── The vocabulary and the seeded exercises ───────────────────────────────


def test_every_seeded_exercise_carries_at_least_one_skill() -> None:
    _units, _lessons, challenges = _seeded()

    assert len(challenges) == 60
    without = [item["challenge_id"] for item in challenges if not item.get("skills")]
    assert without == []


def test_every_skill_belongs_to_exactly_one_unit() -> None:
    owners = curriculum_service.skill_unit_ids()
    units, _lessons, _challenges = _seeded()
    unit_ids = {unit["unit_id"] for unit in units}

    assert owners
    assert all(isinstance(owner, str) and owner for owner in owners.values())
    assert set(owners.values()) <= unit_ids


def test_a_skill_declared_under_two_units_is_refused_rather_than_resolved() -> None:
    """Merging the per-subject maps would silently keep the last owner, and the
    star map would draw the same skill point under two stars."""
    owners: dict[str, set[str]] = {}
    for skills in curriculum_translations.SKILL_UNITS.values():
        for skill_id, unit_id in skills.items():
            owners.setdefault(skill_id, set()).add(unit_id)
    assert [skill for skill, found in owners.items() if len(found) > 1] == []

    clashing = dict(curriculum_translations.SKILL_UNITS)
    clashing["physics"] = {"brueche-kuerzen": "physics-u1"}
    with mock.patch.object(curriculum_translations, "SKILL_UNITS", clashing):
        with pytest.raises(ValueError):
            curriculum_service.skill_unit_ids()


def test_a_seeded_exercise_only_carries_skills_of_its_own_unit() -> None:
    owners = curriculum_service.skill_unit_ids()
    _units, _lessons, challenges = _seeded()

    stray = [
        (item["challenge_id"], skill)
        for item in challenges
        for skill in item.get("skills") or []
        if owners.get(skill) != item["unit_id"]
    ]
    assert stray == []


def test_every_skill_in_the_vocabulary_is_named_in_four_languages() -> None:
    for locale in ["de", "en", "fr", "it"]:
        listed = curriculum_service.list_skills(locale=locale)
        assert listed["count"] == len(curriculum_service.skill_unit_ids())
        unnamed = [item["id"] for item in listed["items"] if not item["name"]]
        assert unnamed == []
    german = {item["id"]: item["name"] for item in curriculum_service.list_skills()["items"]}
    english = {
        item["id"]: item["name"] for item in curriculum_service.list_skills(locale="en")["items"]
    }
    assert all(german[key] != english[key] for key in german)


# ── Draft validation ──────────────────────────────────────────────────────


def _app_for_user(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    return app


def _author_client() -> TestClient:
    return TestClient(
        _app_for_user(
            {
                "sub": "author-1",
                "role": "teacher",
                "capabilities": {curriculum_ops_service.AUTHOR_CAPABILITY: "granted"},
            }
        )
    )


def _draft_payload(skills: list[str] | None = None) -> dict:
    exercise: dict[str, Any] = {
        "exerciseId": "exercise-brueche-1",
        "prompt": "Kürze 6/8.",
        "answerKey": "3/4",
        "explanation": "ggT(6,8) = 2.",
        "difficulty": "standard",
        "order": 1,
    }
    if skills is not None:
        exercise["skills"] = skills
    return {
        "publicLessonId": "lesson-brueche-kuerzen",
        "title": "Brüche kürzen",
        "objective": "Brüche auf die einfachste Form bringen.",
        "subjectId": "math",
        "topicId": "brueche",
        "unitId": "brueche-u1",
        "gradeLevel": "grade_6_primary",
        "exercises": [exercise],
    }


def _create_draft(client: TestClient) -> str:
    created = client.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    assert created.status_code == 200
    return created.json()["versionId"]


def _patch(client: TestClient, version_id: str, skills: list[str]):
    return client.patch(
        f"/admin/curriculum/lessons/lesson-brueche-kuerzen/drafts/{version_id}",
        json={"exercises": [dict(_draft_payload(skills)["exercises"][0])]},
    )


def test_a_draft_patched_with_a_skill_of_its_own_unit_is_accepted(monkeypatch) -> None:
    from test_curriculum_ops import _install_curriculum_ops_repo

    _install_curriculum_ops_repo(monkeypatch)
    client = _author_client()
    version_id = _create_draft(client)

    response = _patch(client, version_id, ["brueche-kuerzen"])

    assert response.status_code == 200
    assert response.json()["exercises"][0]["skills"] == ["brueche-kuerzen"]


def test_a_draft_patched_with_an_unknown_skill_is_refused(monkeypatch) -> None:
    from test_curriculum_ops import _install_curriculum_ops_repo

    _install_curriculum_ops_repo(monkeypatch)
    client = _author_client()
    version_id = _create_draft(client)

    response = _patch(client, version_id, ["brueche-telepathie"])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_failed"
    assert response.json()["detail"]["fields"] == ["exercises[0].skills"]


def test_an_unknown_skill_is_refused_before_a_unit_has_been_chosen(monkeypatch) -> None:
    """The vocabulary has to be checked on its own: a draft that has not named
    its unit yet has nothing for the ownership rule to compare against, and
    without this an invented skill would walk straight into the draft."""
    from test_curriculum_ops import _install_curriculum_ops_repo

    _install_curriculum_ops_repo(monkeypatch)
    client = _author_client()
    payload = _draft_payload()
    payload.pop("unitId")
    created = client.post("/admin/curriculum/lessons/drafts", json=payload)
    version_id = created.json()["versionId"]

    response = client.patch(
        f"/admin/curriculum/lessons/lesson-brueche-kuerzen/drafts/{version_id}",
        json={"exercises": [dict(_draft_payload(["brueche-telepathie"])["exercises"][0])]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == ["exercises[0].skills"]


def test_a_draft_patched_with_a_skill_of_another_unit_is_refused(monkeypatch) -> None:
    """#9 point 12: the skill must belong to the unit the exercise sits in.

    `brueche-multiplizieren` is a real skill, but it hangs under brueche-u2 and
    this lesson is in brueche-u1. Accepting it would put the same skill under
    two stars, which is the one thing the decision rules out.
    """
    from test_curriculum_ops import _install_curriculum_ops_repo

    _install_curriculum_ops_repo(monkeypatch)
    client = _author_client()
    version_id = _create_draft(client)

    response = _patch(client, version_id, ["brueche-multiplizieren"])

    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == ["exercises[0].skills"]


def test_validation_preview_reports_the_stray_skill_rather_than_hiding_it(monkeypatch) -> None:
    from test_curriculum_ops import _install_curriculum_ops_repo

    state = _install_curriculum_ops_repo(monkeypatch)
    client = _author_client()
    version_id = _create_draft(client)
    version = state["versions"][("lesson-brueche-kuerzen", version_id)]
    version["exercises"][0]["skills"] = ["brueche-multiplizieren"]

    preview = client.post(
        f"/admin/curriculum/lessons/lesson-brueche-kuerzen/drafts/{version_id}/validation-preview"
    )

    assert preview.status_code == 200
    assert preview.json()["publishReady"] is False
    assert any(issue["field"] == "exercises[0].skills" for issue in preview.json()["issues"])


# ── Lighting ──────────────────────────────────────────────────────────────


def test_one_right_answer_lights_a_skill() -> None:
    result = mastery.judge_skills(
        unit_id="u1",
        skill_ids=["s1", "s2"],
        skills_by_exercise={"e1": ["s1"], "e2": ["s1"], "e3": ["s2"]},
        exercises_answered_right=frozenset({"e2"}),
    )

    assert {item.skill_id: item.lit for item in result} == {"s1": True, "s2": False}
    assert all(item.unit_id == "u1" for item in result)


def test_a_skill_nobody_has_answered_is_not_lit() -> None:
    result = mastery.judge_skills(
        unit_id="u1",
        skill_ids=["s1"],
        skills_by_exercise={"e1": ["s1"]},
        exercises_answered_right=frozenset(),
    )

    assert [item.lit for item in result] == [False]


def test_a_lit_skill_stays_lit_when_its_last_exercise_leaves_the_unit() -> None:
    """Only forwards. A skill lit once is evidence the student produced, and
    content moving under them must not take it back."""
    result = mastery.judge_skills(
        unit_id="u1",
        skill_ids=["s1"],
        skills_by_exercise={},
        exercises_answered_right=frozenset(),
        already_lit=frozenset({"s1"}),
    )

    assert [item.lit for item in result] == [True]


def test_a_wrong_answer_after_a_right_one_does_not_put_a_skill_out(monkeypatch) -> None:
    table = FakeTable()
    table.seed_active_account("student-1")
    table.seed(
        {
            "PK": "ATTEMPTS#student-1",
            "SK": "ATTEMPT#0001",
            "student_id": "student-1",
            "challenge_id": "brueche-l1-c1",
            "lesson_id": "brueche-l1",
            "correct": True,
        },
        {
            "PK": "ATTEMPTS#student-1",
            "SK": "ATTEMPT#0002",
            "student_id": "student-1",
            "challenge_id": "brueche-l1-c1",
            "lesson_id": "brueche-l1",
            "correct": False,
        },
    )
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(
        mastery.practice_repo,
        "get_challenges",
        lambda lesson_id: (
            [{"challenge_id": "brueche-l1-c1", "skills": ["brueche-kuerzen"], "status": "active"}]
            if lesson_id == "brueche-l1"
            else []
        ),
    )
    catalog = {
        "units": [{"id": "brueche-u1", "topicId": "brueche", "subjectId": "math"}],
        "lessons": [{"id": "brueche-l1", "unitId": "brueche-u1"}],
    }

    states = mastery.skill_states("student-1", catalog=catalog)

    assert states["brueche-kuerzen"].lit is True


# ── The backfill ──────────────────────────────────────────────────────────


def test_the_backfill_reissues_the_version_and_the_hint_decision() -> None:
    """`skills` is content, so writing it moves the hash. A row that got the
    skills alone would be refused by every catalog read."""
    seeded = seed_practice.prepare_challenge_items(_seeded()[2][:1])[0]
    stale = dict(seeded)
    stale.pop("skills")
    stale = practice_repo.version_challenge(stale)
    stale["hint_non_derivability_decision"] = {
        **dict(seeded["hint_non_derivability_decision"]),
        "challenge_version": stale["challenge_version"],
        "content_hash": stale["challenge_content_hash"],
    }

    skills, reason = backfill.planned_skills(stale)
    canonical, pointer = backfill.rewritten(stale, skills)

    assert reason is None and skills == seeded["skills"]
    assert canonical["challenge_version"] == seeded["challenge_version"]
    assert canonical["hint_non_derivability_decision"]["content_hash"] == (
        canonical["challenge_content_hash"]
    )
    assert pointer["challenge_version"] == canonical["challenge_version"]


def test_the_backfill_refuses_a_row_whose_skill_is_not_its_units() -> None:
    row = dict(_seeded()[2][0])
    row["unit_id"] = "geometrie-u2"

    _skills, reason = backfill.planned_skills(row)

    assert reason is not None and "geometrie-u2" in reason


def test_the_backfill_reads_past_the_first_page_of_the_table() -> None:
    """A filtered scan's Limit bounds rows read, not rows kept (#95)."""
    table = FakeTable(page_item_cap=2)
    table.seed(
        *[
            {"PK": "PRACTICE", "SK": f"CHALLENGE#lesson-1#c{index}", "challenge_id": f"c{index}"}
            for index in range(5)
        ],
        *[{"PK": "PRACTICE", "SK": f"LESSON#l{index}"} for index in range(5)],
    )

    found = backfill.stored_challenges(table)

    assert len(found) == 5


def test_a_knowledge_points_own_state_does_not_read_the_skill_points() -> None:
    """#9: the unit's learning state is judged from lessons and answers only."""
    lit_skills = mastery.judge_unit(
        unit={"id": "u1", "topicId": "t1", "subjectId": "math"},
        lessons=[{"id": "l1", "unitId": "u1"}],
        exercises_by_lesson={"l1": ["e1", "e2"]},
        completed_lesson_ids=frozenset({"l1"}),
        exercises_answered_right=frozenset({"e1"}),
    )

    assert lit_skills.state is mastery.LearningState.IN_PROGRESS
