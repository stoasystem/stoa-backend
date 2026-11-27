"""German as a first language goes into the knowledge base with stars written for STOA.

stoa-backend#545 (#498): German has no upstream. Its stars are written final in its
source.json, with their prerequisites, and go into the star file before any of their
practice exists; the other subjects' stars and small stars stay as they are, byte for
byte. Its practice comes in four batches over one source: a knowledge point is one
grade band of a star, its stage is fixed by that band, and a batch's manifests hold
only its own practice sets, so a later batch adds sets beside the published ones and
changes none of them.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from scripts import knowledge_base_import as kb
from scripts import seed_practice
from stoa.db import table as db_table
from stoa.db.repositories import practice_repo
from stoa.services import answer_judging, knowledge_base_catalog
from test_curriculum_publish_projection import install_seeded_table
from test_knowledge_base_import import _publish_all, _register


def _star(unit: str, de: str, grades: list[int], prerequisites: list[str] = ()) -> dict[str, Any]:
    topic = unit.rsplit("-", 1)[0]
    return {
        "unitId": unit, "topicId": topic,
        "titles": {"de": de, "en": f"{de} (en)", "fr": f"{de} (fr)", "it": f"{de} (it)"},
        "description": f"{de} erkennen und bilden.",
        "grades": grades, "prerequisites": list(prerequisites),
    }


def _point(pid: str, star: str, grade: int, stage: int, batch: str) -> dict[str, Any]:
    return {"id": pid, "sourceId": pid, "subject": "german", "domain": "Grammatik", "grade": grade,
            "kind": "conceptual", "name": pid, "description": pid, "mastery": [f"{pid} können"],
            "unit": star, "stage": stage, "batch": batch}


def _choice(eid: str, point: str, question_type: str, prompt: str, options: list[str], answer: int) -> dict:
    return {"id": eid, "sourceId": eid, "point": point, "difficulty": "standard", "type": "choice",
            "questionType": question_type, "prompt": prompt, "choices": options, "answerIndex": answer,
            "explanation": "Weil es so ist."}


def _source() -> dict[str, Any]:
    nomen, pronomen = "deutsch-woerter-nomen", "deutsch-woerter-pronomen"
    exercises = [
        *(_choice(f"kb-d-nomen-1-q{i}", "kb-d-nomen-1", "bestimmen", f"Welches Wort ist ein Nomen? ({i})",
                  ["Hund", "laufen", "schnell"], 0) for i in range(1, 4)),
        *(_choice(f"kb-d-nomen-2-q{i}", "kb-d-nomen-2", "bestimmen", f"Welches Wort ist ein Nomen? ({i})",
                  ["Freundschaft", "freundlich", "befreunden"], 0) for i in range(1, 5)),
        *(_choice(f"kb-d-pronomen-2-q{i}", "kb-d-pronomen-2", "bestimmen", f"Welches Wort ist ein Pronomen? ({i})",
                  ["sie", "Sonne", "sonnig"], 0) for i in range(1, 4)),
    ]
    return {
        "schema": kb.SOURCE_SCHEMA,
        "upstream": {"repository": "written for STOA", "licence": "STOA"},
        "leftBehind": {"fields": [], "files": []},
        "stars": [_star(nomen, "Nomen", [2, 6]), _star(pronomen, "Pronomen", [5, 9], [nomen])],
        "points": [
            _point("kb-d-nomen-1", nomen, 2, 1, "B4"),
            _point("kb-d-nomen-2", nomen, 4, 2, "B1"),
            _point("kb-d-pronomen-2", pronomen, 5, 2, "B1"),
        ],
        "exercises": exercises,
        "prerequisites": [{"point": "kb-d-nomen-2", "requires": "kb-d-nomen-1", "strength": "hard"}],
        "skipped": [],
    }


def _translate(batch: dict[str, Any]) -> dict[str, Any]:
    """The German material stays German in every locale; only the explanation is translated."""
    # A German point is written under its star: the translator does not file it.
    points = {
        point["id"]: {locale: {"name": point["name"], "description": point["description"],
                               "mastery": list(point["mastery"])} for locale in kb.LOCALES}
        for point in batch["points"]
    }
    exercises = {
        exercise["id"]: {locale: {"prompt": exercise["prompt"], "choices": list(exercise["choices"]),
                                  "explanation": f"{locale}: {exercise['explanation']}"} for locale in kb.LOCALES}
        for exercise in batch["exercises"]
    }
    return {"batch": batch["batch"], "points": points, "exercises": exercises}


def _translated() -> dict[str, Any]:
    source = _source()
    return kb.merge(source, [_translate(batch) for batch in kb.batches(source)])


def _built() -> dict[str, Any]:
    return kb.authored_structure(_source(), _translated())


# ── structure ────────────────────────────────────────────────────────────────


def test_the_written_stars_are_taken_as_they_are() -> None:
    translated = _translated()
    built = _built()

    assert translated["problems"] == [] and built["problems"] == []
    nomen = built["stars"]["deutsch-woerter-nomen"]
    assert nomen["subject_id"] == "german" and nomen["topic_id"] == "deutsch-woerter"
    assert nomen["titles"]["fr"] == "Nomen (fr)" and nomen["order"] == 1
    assert nomen["points"] == ["kb-d-nomen-1", "kb-d-nomen-2"]
    assert built["stars"]["deutsch-woerter-pronomen"]["prerequisites"] == ["deutsch-woerter-nomen"]
    assert built["exercises"]["kb-d-pronomen-2-q1"] == "bestimmen"
    # The points keep their stage and batch through the translation.
    assert {p["id"]: (p["stage"], p["batch"]) for p in translated["points"]}["kb-d-nomen-1"] == (1, "B4")


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda s: s["stars"][1].update(grades=[1, 9]), "after this star's grade 1"),
        (lambda s: s["stars"][1].update(prerequisites=["deutsch-woerter-verb"]), "is not another star"),
        (lambda s: s["stars"][1].update(prerequisites=["brueche-u1"]), "is not another star"),
        (lambda s: s["stars"][0].update(unitId="deutsch-formen-nomen"), "is not its nebula's id"),
        (lambda s: s["stars"][0].update(topicId="brueche", unitId="brueche-nomen"), "not one of an authored subject"),
        (lambda s: s["stars"][0].update(grades=[6, 2]), "are not [first, last]"),
        (lambda s: s["stars"][0]["titles"].update(fr=""), "fr: no title"),
        (lambda s: s["stars"][0].update(questionTypes=["kopfrechnen"]), "is not one of"),
    ],
)
def test_a_written_star_that_breaks_a_rule_is_refused(change: Any, problem: str) -> None:
    source = _source()
    change(source)
    built = kb.authored_structure(source, {"points": [], "exercises": []})

    assert any(problem in text for row in built["problems"] for text in row["problems"]), built["problems"]


def test_a_point_outside_its_stars_grades_or_without_a_stage_is_refused() -> None:
    translated = _translated()
    translated["points"][0]["grade"] = 8
    del translated["points"][1]["stage"]
    built = kb.authored_structure(_source(), translated)

    problems = {row["id"]: row["problems"] for row in built["problems"]}
    assert "grade 8 is outside" in problems["kb-d-nomen-1"][0]
    assert problems["kb-d-nomen-2"] == ["no stage"]


def test_two_stars_needing_each_other_are_refused() -> None:
    source = _source()
    source["stars"][0]["prerequisites"] = ["deutsch-woerter-pronomen"]
    source["stars"][0]["grades"] = [5, 9]
    built = kb.authored_structure(source, {"points": [], "exercises": []})

    assert any("lead back" in text for row in built["problems"] for text in row["problems"])


# ── manifest ─────────────────────────────────────────────────────────────────


def test_every_written_star_is_drawn_before_its_practice_comes() -> None:
    source = {**_source(), "points": [], "exercises": [], "prerequisites": []}
    translated = kb.merge(source, [])
    made, report, stars_file, vocabulary = kb.manifests(
        translated, kb.authored_structure(source, translated), "abc"
    )

    assert made == [] and vocabulary["skills"] == {}
    assert set(stars_file["stars"]) == {"deutsch-woerter-nomen", "deutsch-woerter-pronomen"}
    assert stars_file["stars"]["deutsch-woerter-pronomen"]["prerequisites"] == ["deutsch-woerter-nomen"]
    assert report["summary"]["stars"] == 2


def test_a_stage_is_its_grade_band_and_a_batch_holds_only_its_own_sets() -> None:
    translated = _translated()
    made, _report, stars_file, vocabulary = kb.manifests(translated, _built(), "abc", batch="B1")

    rows = {row["publicLessonId"]: row for manifest in made for row in manifest["lessons"]}
    # B1 brings stage 2; the grade 2 band (stage 1) waits for B4 and is not in the manifests.
    assert set(rows) == {"deutsch-woerter-nomen--bestimmen--2", "deutsch-woerter-pronomen--bestimmen--2"}
    nomen = rows["deutsch-woerter-nomen--bestimmen--2"]["lesson"]
    assert nomen["title"] == "Bestimmen · Stufe 2"
    assert nomen["subjectId"] == "german" and nomen["gradeLevel"] == "grade_4_primary"
    assert nomen["requiresPoints"] == ["kb-d-nomen-1"]
    # A stage alone still says which it is, so a later band changes no title.
    assert rows["deutsch-woerter-pronomen--bestimmen--2"]["lesson"]["title"] == "Bestimmen · Stufe 2"
    assert all("stoa-backend#498" in manifest["operatorNote"] for manifest in made)
    # The vocabulary names every set, so B4 later adds stage 1 beside the published stage 2.
    assert "deutsch-woerter-nomen--bestimmen--1" in vocabulary["practiceSets"]
    assert vocabulary["skills"]["deutsch-woerter-nomen--bestimmen"]["extension"] is False
    later, *_ = kb.manifests(translated, _built(), "abc", batch="B4")
    assert [row["publicLessonId"] for m in later for row in m["lessons"]] == ["deutsch-woerter-nomen--bestimmen--1"]


def test_the_german_material_stays_german_in_every_language() -> None:
    made, *_ = kb.manifests(_translated(), _built(), "abc", batch="B1")
    exercise = made[0]["lessons"][0]["exercises"][0]

    assert all(t["options"] == exercise["options"] for t in exercise["translations"].values())
    assert exercise["translations"]["fr"]["explanation"].startswith("fr:")


def test_writing_one_subject_keeps_every_other_subjects_entries() -> None:
    old_stars = json.loads(knowledge_base_catalog.STARS_FILE.read_text(encoding="utf-8"))
    old_vocabulary = json.loads(knowledge_base_catalog.SKILLS_FILE.read_text(encoding="utf-8"))
    _made, _report, stars_file, vocabulary = kb.manifests(_translated(), _built(), "abc")

    stars, skills = kb.with_other_subjects(old_stars, old_vocabulary, stars_file, vocabulary, "german")

    others = {u: s for u, s in stars["stars"].items() if s["subject_id"] != "german"}
    before = {u: s for u, s in old_stars["stars"].items() if s["subject_id"] != "german"}
    assert json.dumps(others, ensure_ascii=False) == json.dumps(before, ensure_ascii=False)
    assert list(stars["stars"])[-2:] == ["deutsch-woerter-nomen", "deutsch-woerter-pronomen"]
    assert {k: s for k, s in skills["skills"].items() if s["subject"] != "german"} == {
        k: s for k, s in old_vocabulary["skills"].items() if s["subject"] != "german"
    }
    assert "deutsch-woerter-nomen--bestimmen--2" in skills["practiceSets"]
    # A run over the upstream's subjects alone leaves the German stars where they are.
    upstream_only = {**stars_file, "stars": {u: s for u, s in others.items()}}
    upstream_vocabulary = {
        **old_vocabulary,
        "skills": {k: s for k, s in old_vocabulary["skills"].items() if s["subject"] != "german"},
    }
    again, _vocabulary = kb.with_other_subjects(stars, skills, upstream_only, upstream_vocabulary, None)
    assert list(again["stars"])[-2:] == ["deutsch-woerter-nomen", "deutsch-woerter-pronomen"]


# ── the committed stars and the seed ─────────────────────────────────────────


def test_the_committed_german_stars_are_the_written_ones() -> None:
    german = [unit for unit in knowledge_base_catalog.units() if unit["subject_id"] == "german"]
    nebulae = {topic for topic, _titles in knowledge_base_catalog.GERMAN_TOPICS}

    assert len(german) == 52
    assert {unit["topic_id"] for unit in german} == nebulae
    by_id = {unit["unit_id"]: unit for unit in german}
    for unit in german:
        assert unit["unit_id"].startswith(f"{unit['topic_id']}-")
        assert set(unit["titles"]) == set(knowledge_base_catalog.LOCALES)
        assert "ß" not in unit["titles"]["de"] + unit["description"]
        assert set(unit["prerequisites"]) <= set(by_id)
    assert knowledge_base_catalog.subject_of_topic("deutsch-literatur") == "german"
    assert "deutsch-saetze-komma" in knowledge_base_catalog.unit_choices("german")
    named = {row.get("unit_id") or row["topic_id"]: row["titles"] for row in [
        *knowledge_base_catalog.topics(), *knowledge_base_catalog.units()
    ]}
    assert named["deutsch-rechtschreibung"]["it"] == "Ortografia"


def test_the_bare_live_flag_writes_german_live_with_its_subject_row() -> None:
    """#547: once B1 was published, German went live with the others, so a seed run
    no longer names `mathematics english physics` to keep it in preview."""
    mode = seed_practice.parse_args(["--knowledge-base-live"]).knowledge_base
    subjects, topics, units = seed_practice.knowledge_base_rows(
        live=seed_practice.knowledge_base_live_subjects(mode)
    )

    assert mode == "live"
    assert [s["subject_id"] for s in subjects] == ["english", "physics", "german"]
    german = [row for row in (*topics, *units) if row["subject_id"] == "german"]
    assert len(german) == 8 + 52 and {row["rollout_state"] for row in german} == {"active"}
    assert {row["rollout_state"] for row in (*topics, *units)} == {"active"}


# ── through the curriculum workflow ──────────────────────────────────────────


@pytest.fixture
def imported(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    made, _report, stars_file, vocabulary = kb.manifests(_translated(), _built(), "abc", batch="B1")
    _register(monkeypatch, stars_file, vocabulary)
    table = install_seeded_table(monkeypatch)
    db_table.install(table)
    _subjects, topics, units = seed_practice.knowledge_base_rows(live=False)
    table.seed(
        *({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics),
        *({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units),
    )
    return copy.deepcopy(made)


def test_a_german_batch_publishes_and_judges_its_german_answer(imported: list[dict[str, Any]]) -> None:
    _publish_all(imported)
    row = practice_repo.get_challenge("kb-d-nomen-2-q1")

    assert row is not None
    assert answer_judging.judge_challenge("Freundschaft", row)
    assert not answer_judging.judge_challenge("freundlich", row)
    assert practice_repo.get_challenge("kb-d-nomen-1-q1") is None
