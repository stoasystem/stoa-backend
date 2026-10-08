"""Unit and lesson prerequisite relations, and the attribution they have to agree with.

A planet locks a knowledge point only from an explicit `prerequisite_unit_ids`
list, so the list has to exist on every unit, stay inside one subject, point at
units that are really there, and never close a loop. The lesson layer carries the
same relation one level down, plus the rule that a lesson belongs to the unit it
names: same topic, same subject. stoasystem/stoa-backend#56.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.routers import admin
from stoa.services import curriculum_ops_service, curriculum_service


def _seed_units() -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for build in (
        seed_practice._brueche_data,
        seed_practice._gleichungen_data,
        seed_practice._geometrie_data,
        seed_practice._prozent_data,
        seed_practice._textaufgaben_data,
    ):
        units.extend(build()[1])
    return units


def _app_for_user(user: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    return app


def _operator_user(*capabilities: str, role: str = "teacher", sub: str = "operator-1") -> dict[str, Any]:
    return {
        "sub": sub,
        "role": role,
        "capabilities": {capability: "granted" for capability in capabilities},
    }


UNITS = [
    {
        "unit_id": "u-base",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "grade_level": "grade_6_primary",
        "title": "Base",
        "order": 1,
        "prerequisite_unit_ids": [],
    },
    {
        "unit_id": "u-next",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "grade_level": "grade_6_primary",
        "title": "Next",
        "order": 2,
        "prerequisite_unit_ids": ["u-base"],
    },
    {
        "unit_id": "u-other-subject",
        "topic_id": "topic-b",
        "subject_id": "german",
        "grade_level": "grade_6_primary",
        "title": "Other subject",
        "order": 1,
        "prerequisite_unit_ids": [],
    },
]

TOPICS = [
    {
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "grade_level": "grade_6_primary",
        "title": "Topic A",
        "order": 1,
        "status": "available",
    },
    {
        "topic_id": "topic-b",
        "subject_id": "german",
        "grade_level": "grade_6_primary",
        "title": "Topic B",
        "order": 2,
        "status": "available",
    },
]

SUBJECTS = [
    {"subject_id": "mathematics", "name": "Mathematik", "order": 1},
    {"subject_id": "german", "name": "Deutsch", "order": 2},
]

LESSONS = [
    {
        "lesson_id": "lesson-base-1",
        "unit_id": "u-base",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "grade_level": "grade_6_primary",
        "title": "Base one",
        "order": 1,
    },
    {
        "lesson_id": "lesson-next-1",
        "unit_id": "u-next",
        "topic_id": "topic-a",
        "subject_id": "mathematics",
        "grade_level": "grade_6_primary",
        "title": "Next one",
        "order": 2,
        "prerequisite_lesson_ids": ["lesson-base-1"],
    },
    {
        "lesson_id": "lesson-foreign",
        "unit_id": "u-other-subject",
        "topic_id": "topic-b",
        "subject_id": "german",
        "grade_level": "grade_6_primary",
        "title": "Foreign",
        "order": 1,
    },
]


def _content_table(monkeypatch: pytest.MonkeyPatch, *extra: dict[str, Any]) -> FakeTable:
    table = FakeTable()
    table.seed(
        *[{"PK": "PRACTICE", "SK": f"SUBJECT#{s['subject_id']}", **s} for s in SUBJECTS],
        *[{"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in TOPICS],
        *[{"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in UNITS],
        *[{"PK": "PRACTICE", "SK": f"LESSON#{item['lesson_id']}", **item} for item in LESSONS],
        *extra,
    )
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(curriculum_ops_repo, "get_table", lambda: table)
    return table


# ── Seed ──────────────────────────────────────────────────────────────────


def test_seeded_units_all_carry_an_acyclic_same_subject_prerequisite_list() -> None:
    units = _seed_units()
    by_id = {unit["unit_id"]: unit for unit in units}

    for unit in units:
        assert "prerequisite_unit_ids" in unit
        for reference in unit["prerequisite_unit_ids"]:
            assert reference in by_id
            assert by_id[reference]["subject_id"] == unit["subject_id"]

    colour: dict[str, int] = {}

    def visit(unit_id: str) -> None:
        colour[unit_id] = 1
        for reference in by_id[unit_id]["prerequisite_unit_ids"]:
            assert colour.get(reference) != 1, f"cycle through {reference}"
            if reference not in colour:
                visit(reference)
        colour[unit_id] = 2

    for unit_id in by_id:
        if unit_id not in colour:
            visit(unit_id)

    assert any(unit["prerequisite_unit_ids"] for unit in units)


# ── Read model ────────────────────────────────────────────────────────────


def test_catalog_units_carry_their_prerequisite_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    catalog = curriculum_service.list_catalog(subject_id="mathematics")

    units = {unit["id"]: unit for unit in catalog["units"]}
    assert units["u-base"]["prerequisiteUnitIds"] == []
    assert units["u-next"]["prerequisiteUnitIds"] == ["u-base"]


def test_get_prerequisites_returns_one_map_per_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    assert curriculum_service.get_prerequisites("math") == {
        "u-base": [],
        "u-next": ["u-base"],
    }
    assert curriculum_service.get_prerequisites("german") == {"u-other-subject": []}


# ── Admin unit prerequisite maintenance ───────────────────────────────────


def _patch(client: TestClient, unit_id: str, references: list[str]):
    return client.patch(
        f"/admin/curriculum/units/{unit_id}",
        json={"prerequisiteUnitIds": references},
    )


def test_unit_prerequisites_patch_replaces_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    response = _patch(client, "u-next", [])

    assert response.status_code == 200
    assert response.json()["prerequisiteUnitIds"] == []
    assert table.rows[("PRACTICE", "UNIT#u-next")]["prerequisite_unit_ids"] == []


def test_unit_prerequisites_patch_refuses_a_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    response = _patch(client, "u-base", ["u-next"])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_failed"


def test_unit_prerequisites_patch_refuses_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    assert _patch(client, "u-base", ["u-base"]).status_code == 422


def test_unit_prerequisites_patch_refuses_another_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    assert _patch(client, "u-next", ["u-other-subject"]).status_code == 422


def test_unit_prerequisites_patch_refuses_an_unknown_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    assert _patch(client, "u-next", ["u-missing"]).status_code == 422


def test_unit_prerequisites_patch_does_not_create_units(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _content_table(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY))
    )

    response = _patch(client, "u-unknown", [])

    assert response.status_code == 404
    assert ("PRACTICE", "UNIT#u-unknown") not in table.rows


def test_unit_prerequisites_patch_requires_the_author_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    assert _patch(client, "u-next", []).status_code == 403


# ── Lesson draft attribution and prerequisites ────────────────────────────


def _draft_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "publicLessonId": "lesson-draft-1",
        "title": "Draft one",
        "objective": "Practise the base unit.",
        "subjectId": "math",
        "topicId": "topic-a",
        "unitId": "u-base",
        "gradeLevel": "grade_6_primary",
        "exercises": [],
    }
    payload.update(overrides)
    return payload


def _author_client() -> TestClient:
    return TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )


def test_lesson_draft_accepts_a_consistent_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    response = _author_client().post("/admin/curriculum/lessons/drafts", json=_draft_payload())

    assert response.status_code == 200
    assert response.json()["lesson"]["unit_id"] == "u-base"


def test_lesson_draft_requires_a_unit_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts", json=_draft_payload(unitId=None)
    )

    assert response.status_code == 422
    assert "unit_id" in response.json()["detail"]["fields"]


def test_lesson_draft_refuses_an_unknown_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts", json=_draft_payload(unitId="u-missing")
    )

    assert response.status_code == 422
    assert "unit_id" in response.json()["detail"]["fields"]


def test_lesson_draft_refuses_a_topic_the_unit_does_not_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts", json=_draft_payload(topicId="topic-b")
    )

    assert response.status_code == 422
    assert "topic_id" in response.json()["detail"]["fields"]


def test_lesson_draft_refuses_a_subject_the_unit_does_not_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts", json=_draft_payload(subjectId="german")
    )

    assert response.status_code == 422
    assert "subject_id" in response.json()["detail"]["fields"]


def test_lesson_draft_keeps_prerequisites_under_their_own_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts",
        json=_draft_payload(prerequisites=["lesson-base-1"]),
    )

    assert response.status_code == 200
    assert response.json()["lesson"]["prerequisite_lesson_ids"] == ["lesson-base-1"]
    assert "prerequisites" not in response.json()["lesson"]


def test_lesson_draft_refuses_an_unknown_prerequisite_lesson(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts",
        json=_draft_payload(prerequisiteLessonIds=["lesson-missing"]),
    )

    assert response.status_code == 422
    assert "prerequisite_lesson_ids" in response.json()["detail"]["fields"]


def test_lesson_draft_refuses_a_prerequisite_outside_its_unit_and_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts",
        json=_draft_payload(prerequisiteLessonIds=["lesson-foreign"]),
    )

    assert response.status_code == 422
    assert "prerequisite_lesson_ids" in response.json()["detail"]["fields"]


def test_lesson_draft_refuses_a_prerequisite_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    _content_table(monkeypatch)

    response = _author_client().post(
        "/admin/curriculum/lessons/drafts",
        json=_draft_payload(
            publicLessonId="lesson-base-1",
            unitId="u-next",
            topicId="topic-a",
            prerequisiteLessonIds=["lesson-next-1"],
        ),
    )

    assert response.status_code == 422
    assert "prerequisite_lesson_ids" in response.json()["detail"]["fields"]
