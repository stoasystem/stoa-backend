"""An editorial batch becomes a dry-run manifest that the migration accepts as drafts.

The batch here is made up in the shape of the #106 ZAP fractions batch
(`stoa-editorial-1.0`); the real one carries source text whose permissions are not
settled, so it is not copied into the repository. The last tests send the converted
manifest through the real dry run and apply against the seeded table double and
then through review and publish, which is the path a real batch takes.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import editorial_batch_to_migration as converter
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.routers import admin
from stoa.services import answer_judging, curriculum_migration_service, curriculum_ops_service
from test_curriculum_publish_projection import install_seeded_table


OPERATOR = {
    "sub": "operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
    },
}


def _card(knowledge_id: str, skill_id: str | None, proposed: str | None = None) -> dict[str, Any]:
    return {
        "knowledge_id": knowledge_id,
        "title": {"de": f"Karte {knowledge_id}", "zh": "卡片"},
        "learning_objective": "Einen Bruchteil berechnen.",
        "content_language": "de",
        "scope": {"subject": "math", "grade_level": "grade_6_primary"},
        "platform_refs": {
            "subject_id": "math",
            "topic_id": "brueche",
            "unit_id": "brueche-u2",
            "skill_id": skill_id,
            "proposed_skill_id": proposed,
        },
        "status": "mapped",
    }


def _question(exercise_id: str, knowledge_id: str = "KP-ANTEIL", **extra: Any) -> dict[str, Any]:
    record = {
        "exercise_id": exercise_id,
        "revision": 1,
        "record_type": "question",
        "status": "mapped",
        "response_type": "short_answer",
        "prompt": "Bestimme $\\frac{3}{4}$ von $24$.",
        "options": [],
        "assets": [],
        "parent_id": None,
        "shared_material_id": None,
        "answer": {"canonical": "18", "accepted_answers": ["18", " 18 Stück ", "18 Stück"]},
        "solution": [
            {"step": 2, "text": "$6\\cdot 3=18$."},
            {"step": 1, "text": "Ein Viertel von $24$ ist $6$."},
        ],
        "hints": [{"level": 1, "text": "Zuerst ein Viertel."}],
        "grading": {"max_points": 1},
        "source_refs": [
            {"source_id": "D0001", "role": "question", "pdf_page": 3, "question_label": "1a"}
        ],
        "_knowledge": knowledge_id,
    }
    record.update(extra)
    return record


def _batch(
    *exercises: dict[str, Any], shared: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    records = [copy.deepcopy(item) for item in exercises]
    mappings = [
        {
            "exercise_id": item["exercise_id"],
            "knowledge_id": item.pop("_knowledge"),
            "relation": "primary",
        }
        for item in records
        if "_knowledge" in item
    ]
    return {
        "schema_version": "stoa-editorial-1.0",
        "batch_id": "test-fractions-batch",
        "revision": 3,
        "sources": [{"source_id": "D0001", "rights_status": "link_only"}],
        "knowledge": [
            _card("KP-ANTEIL", "brueche-anteil-einer-menge"),
            _card("KP-GANZES", None, proposed="brueche-ganzes-bestimmen"),
            _card("KP-UNBEKANNT", None, proposed="brueche-gibt-es-nicht"),
            _card("KP-FREMD", "gleichungen-einstufig"),
        ],
        "exercises": records,
        "shared_materials": shared or [],
        "mappings": mappings,
    }


def _report_row(report: dict[str, Any], exercise_id: str) -> dict[str, Any]:
    return next(row for row in report["exercises"] if row["editorialExerciseId"] == exercise_id)


def test_the_limits_are_the_authoring_request_limits() -> None:
    def limit(model: type, field: str, kind: str) -> int:
        metadata = model.model_fields[field].metadata
        return next(getattr(item, kind) for item in metadata if hasattr(item, kind))

    assert converter.MAX_TITLE == limit(admin.CurriculumLessonDraftRequest, "title", "max_length")
    assert converter.MAX_OBJECTIVE == limit(
        admin.CurriculumLessonDraftRequest, "objective", "max_length"
    )
    assert converter.MAX_TEXT == limit(admin.CurriculumExerciseDraftRequest, "prompt", "max_length")
    assert converter.MAX_TEXT == limit(
        admin.CurriculumExerciseDraftRequest, "answer_key", "max_length"
    )
    assert converter.MAX_TEXT == limit(
        admin.CurriculumExerciseDraftRequest, "explanation", "max_length"
    )
    assert converter.MAX_ID == limit(
        admin.CurriculumExerciseDraftRequest, "exercise_id", "max_length"
    )


def test_one_lesson_per_card_and_never_a_publish_intent() -> None:
    manifest, report = converter.convert(
        _batch(
            _question("EX-D0001-1A"), _question("EX-D0001-1B"), _question("EX-D0002-4", "KP-GANZES")
        )
    )

    assert manifest["source"] == {
        "sourceId": "test-fractions-batch",
        "sourceVersion": "revision-3",
        "sourceType": "editorial_batch",
    }
    assert "link_only" in manifest["operatorNote"]
    assert [lesson["publicLessonId"] for lesson in manifest["lessons"]] == [
        "zap-anteil",
        "zap-ganzes",
    ]
    assert all(lesson["publish"] is False for lesson in manifest["lessons"])

    anteil = manifest["lessons"][0]
    assert anteil["lesson"]["title"] == "Karte KP-ANTEIL"
    assert anteil["lesson"]["unitId"] == "brueche-u2"
    assert anteil["lesson"]["gradeLevel"] == "grade_6_primary"
    first = anteil["exercises"][0]
    assert first == {
        "exerciseId": "zap-d0001-1a",
        "type": "text_input",
        "prompt": "Bestimme $\\frac{3}{4}$ von $24$.",
        "answerKey": "18",
        "acceptedAnswers": ["18 Stück"],
        "explanation": "Ein Viertel von $24$ ist $6$.\n$6\\cdot 3=18$.",
        "difficulty": "practice",
        "order": 1,
        "skills": ["brueche-anteil-einer-menge"],
    }
    assert anteil["exercises"][1]["order"] == 2
    assert manifest["lessons"][1]["exercises"][0]["skills"] == ["brueche-ganzes-bestimmen"]

    row = _report_row(report, "EX-D0001-1A")
    assert row["status"] == "converted"
    assert row["exerciseId"] == "zap-d0001-1a"
    assert row["sources"][0]["rightsStatus"] == "link_only"
    assert {"hints", "grading", "source_refs"} <= set(row["notCarried"])
    assert report["counts"] == {"exercises": 3, "converted": 3, "skipped": 0, "lessons": 2}


@pytest.mark.parametrize(
    ("exercise", "reason"),
    [
        (
            _question("EX-B", status="blocked", blocked_reason="no rubric"),
            "status blocked: no rubric",
        ),
        (_question("EX-E", status="extracted"), "status extracted"),
        (_question("EX-C", record_type="container"), "not an answerable question"),
        (_question("EX-D", response_type="construction"), "response type construction"),
        (_question("EX-O", options=[{"id": "a", "text": "1/2"}]), "choice options"),
        (_question("EX-F", assets=[{"path": "figure.png"}]), "figures"),
        (_question("EX-U", "KP-UNBEKANNT"), "not registered"),
        (_question("EX-W", "KP-FREMD"), "belongs to gleichungen-u1"),
        (_question("EX-N", answer={"canonical": " "}), "no canonical answer"),
        (_question("EX-S", solution=[]), "no solution steps"),
        (_question("EX-L", prompt="x" * 2001), "prompt is 2001 characters"),
        (_question("EX-M", shared_material_id="CTX-1"), "shared material CTX-1 is missing"),
    ],
)
def test_what_the_platform_cannot_show_or_judge_is_skipped_with_its_reason(
    exercise: dict[str, Any], reason: str
) -> None:
    manifest, report = converter.convert(_batch(exercise, _question("EX-OK")))

    row = _report_row(report, exercise["exercise_id"])
    assert row["status"] == "skipped"
    assert reason in row["reason"]
    assert [item["exerciseId"] for item in manifest["lessons"][0]["exercises"]] == ["zap-ok"]


def test_a_child_question_must_carry_its_shared_material() -> None:
    shared = [
        {
            "exercise_id": "CTX-1",
            "record_type": "container",
            "prompt": "Ein Laden senkt alle Preise.",
        }
    ]
    with_material = _question(
        "EX-3A", shared_material_id="CTX-1", prompt="Ein Laden senkt alle Preise.\n\nWie viel?"
    )
    without = _question("EX-3B", shared_material_id="CTX-1", prompt="Wie viel?")

    _manifest, report = converter.convert(_batch(with_material, without, shared=shared))

    assert _report_row(report, "EX-3A")["status"] == "converted"
    assert "does not contain shared material CTX-1" in _report_row(report, "EX-3B")["reason"]


def test_another_schema_is_refused() -> None:
    batch = _batch(_question("EX-1"))
    batch["schema_version"] = "stoa-editorial-2.0"
    with pytest.raises(ValueError, match="stoa-editorial-1.0"):
        converter.convert(batch)


def test_the_command_writes_both_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "batch.json"
    source.write_text(
        json.dumps(_batch(_question("EX-1"), _question("EX-2", status="blocked"))), encoding="utf-8"
    )

    code = converter.main(
        [str(source), "--manifest", str(tmp_path / "m.json"), "--report", str(tmp_path / "r.json")]
    )

    assert code == 0
    assert (
        json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["lessons"][0]["publish"]
        is False
    )
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["counts"]["skipped"] == 1
    assert "1 of 2 exercises" in capsys.readouterr().out
    assert converter.main([str(tmp_path / "missing.json"), "--manifest", "m", "--report", "r"]) == 1


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def test_the_manifest_dry_runs_clean_and_applies_as_drafts_only(table: FakeTable) -> None:
    manifest, _report = converter.convert(
        _batch(_question("EX-D0001-1A"), _question("EX-D0002-4", "KP-GANZES"))
    )

    preview = curriculum_migration_service.dry_run(manifest, OPERATOR)
    assert preview["summary"]["errors"] == 0 and preview["summary"]["conflicts"] == 0
    assert [row["action"] for row in preview["rows"]] == ["create", "create"]
    assert all(row["publishIntent"] is False for row in preview["rows"])

    curriculum_migration_service.apply_migration(
        preview["migrationId"], manifest, preview["confirmationToken"], OPERATOR
    )

    for lesson in manifest["lessons"]:
        pointer = curriculum_ops_repo.get_pointer(lesson["publicLessonId"]) or {}
        assert "published_version_id" not in pointer
        assert practice_repo.get_challenges(lesson["publicLessonId"]) == []


def test_a_converted_draft_goes_through_review_and_judges_its_listed_answers(
    table: FakeTable,
) -> None:
    manifest, _report = converter.convert(_batch(_question("EX-D0001-1A")))
    preview = curriculum_migration_service.dry_run(manifest, OPERATOR)
    applied = curriculum_migration_service.apply_migration(
        preview["migrationId"], manifest, preview["confirmationToken"], OPERATOR
    )
    version_id = applied["rows"][0]["versionId"]

    curriculum_ops_service.submit_review("zap-anteil", version_id, OPERATOR)
    curriculum_ops_service.approve("zap-anteil", version_id, OPERATOR)
    curriculum_ops_service.publish(
        "zap-anteil", version_id, OPERATOR, expected_published_version_id=None
    )

    challenge = practice_repo.get_challenge("zap-d0001-1a")
    assert challenge is not None
    assert answer_judging.judge_challenge("18 stück", challenge)
    assert not answer_judging.judge_challenge("24", challenge)
