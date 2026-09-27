"""`math` and `mathematics` read the same practice content on every subject filter.

`math` is the canonical subject id: the curriculum responses, the rollout subjects,
learning profiles and question subjects all say it. The practice content is seeded
with `mathematics`, and a progress row copies its lesson's value. Subject filters
that compared raw values split the two apart: after stoasystem/stoa-backend#53,
production answered `/practice/curriculum/catalog?subjectId=math` with 0 topics,
0 units and 20 lessons against 5 / 10 / 20 for `mathematics`, while the catalog
itself answers with `subject.id` `math`. Exercises, completed lessons and the topic
roadmap had the same split. stoasystem/stoa-backend#62.

Everything goes through the real `practice_repo` against the shared table double,
seeded with the real seed builders.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from test_curriculum_catalog_shows_seeded_topics import _seeded_table
from stoa.db.repositories import account_deletion_repo, practice_repo
from stoa.routers import practice
from stoa.services import curriculum_service

SPELLINGS = ("math", "mathematics", "Mathematik")


def _ids(rows: list[dict]) -> list[str]:
    return sorted(row["id"] for row in rows)


def test_every_spelling_reads_the_same_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    _seeded_table(monkeypatch)

    catalogs = {spelling: curriculum_service.list_catalog(subject_id=spelling) for spelling in SPELLINGS}

    for spelling, catalog in catalogs.items():
        counts = (len(catalog["topics"]), len(catalog["units"]), len(catalog["lessons"]))
        assert counts == (5, 10, 20), spelling
        assert [subject["id"] for subject in catalog["subjects"]] == ["math"]
    for part in ("topics", "units", "lessons"):
        assert len({tuple(_ids(catalog[part])) for catalog in catalogs.values()}) == 1, part


def test_the_catalog_subject_id_finds_its_own_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """The id the catalog hands out is the id a client sends back."""
    _seeded_table(monkeypatch)

    whole = curriculum_service.list_catalog()
    [subject_id] = [subject["id"] for subject in whole["subjects"]]

    assert _ids(curriculum_service.list_catalog(subject_id=subject_id)["topics"]) == _ids(whole["topics"])


def test_every_spelling_reads_the_same_exercises(monkeypatch: pytest.MonkeyPatch) -> None:
    _seeded_table(monkeypatch)

    by_spelling = {
        spelling: _ids(curriculum_service.list_exercises(subject_id=spelling)["items"])
        for spelling in SPELLINGS
    }

    assert len(by_spelling["math"]) == len(_ids(curriculum_service.list_exercises()["items"])) > 0
    assert len(set(map(tuple, by_spelling.values()))) == 1


def test_a_completed_lesson_counts_under_every_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _seeded_table(
        monkeypatch,
        {**account_deletion_repo.account_fence_key("student-1"), "status": "active", "generation": 1},
    )
    lesson = next(row for (_pk, sk), row in table.rows.items() if sk.startswith("LESSON#"))
    assert lesson["subject_id"] == "mathematics"
    practice_repo.mark_lesson_completed("student-1", lesson)

    for spelling in SPELLINGS:
        assert [row["lesson_id"] for row in practice_repo.get_progress("student-1", spelling)] == [
            lesson["lesson_id"]
        ], spelling
        summary = curriculum_service.get_progress_summary("student-1", subject_id=spelling)
        assert summary["completedLessonIds"] == [lesson["lesson_id"]], spelling
    assert practice_repo.get_progress("student-1", "physics") == []


def test_the_topic_roadmap_answers_under_every_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _seeded_table(monkeypatch)
    topic_id = next(row["topic_id"] for (_pk, sk), row in table.rows.items() if sk.startswith("TOPIC#"))
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    client = TestClient(app)

    responses = {spelling: client.get(f"/practice/{spelling}/{topic_id}/roadmap") for spelling in SPELLINGS}

    for spelling, response in responses.items():
        assert response.status_code == 200, (spelling, response.text)
    assert len({tuple(unit["id"] for unit in response.json()["units"]) for response in responses.values()}) == 1
    assert client.get(f"/practice/physics/{topic_id}/roadmap").status_code == 404
