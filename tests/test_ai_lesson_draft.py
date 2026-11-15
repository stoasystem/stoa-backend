"""The AI lesson draft (#441): outline, confirmation, blocks, blind check, manifest, dry run.

The model is a stand-in that answers by the schema it is given; nothing calls Bedrock.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts import ai_lesson_draft as draft

STAR = "physik-mechanik-masse-dichte-und-gewichtskraft"


def _text_exercise(slot: int, key: str = "5", accepted: list[str] | None = None) -> dict[str, Any]:
    accepted = ["5 N", "5 Newton"] if accepted is None else accepted
    return {"slot": slot, "type": "text_input", **{
        locale: {"prompt": f"Wie gross ist die Gewichtskraft in N? ({locale} {slot})", "correctAnswer": key,
                 "acceptedAnswers": accepted, "explanation": "F = m · g = 0.5 kg · 10 N/kg = 5 N."}
        for locale in draft.LOCALES
    }}


def _choice_exercise(slot: int) -> dict[str, Any]:
    return {"slot": slot, "type": "multiple_choice", **{
        locale: {"prompt": f"Welche Einheit hat die Dichte? ({locale})", "options": ["kg/m³", "N", "m/s"],
                 "correctAnswer": "kg/m³", "explanation": "Dichte ist Masse durch Volumen."}
        for locale in draft.LOCALES
    }}


class FakeModel:
    """Answers by schema; `broken` slots come back wrong the first time."""

    def __init__(self, broken: set[int] | None = None) -> None:
        self.calls: list[str] = []
        self.broken = set(broken or ())

    def __call__(self, system: str, user: str, schema: Mapping[str, Any], max_tokens: int) -> draft.Reply:
        if schema is draft.OUTLINE_SCHEMA:
            kind, data = "outline", {
                "cards": [{"title": "Masse", "explains": "Was Masse ist", "formulas": ["F = m · g"]},
                          {"title": "Dichte", "explains": "Masse pro Volumen", "formulas": ["ρ = m / V"]}],
                "exercises": [{"questionType": t, "format": f, "difficulty": "basic", "tests": "x",
                               "answerShape": "Zahl in N"}
                              for t, f in [("rechnen", "short")] * 4 + [("begriffe", "choice")] * 2
                              + [("diagramme", "short")]],
            }
        elif schema is draft.CARDS_SCHEMA:
            kind, data = "cards", {"cards": [
                {locale: {"title": f"Karte {i}", "body": "F = m · g"} for locale in draft.LOCALES} for i in (1, 2)
            ]}
        elif schema is draft.EXERCISES_SCHEMA:
            kind = "exercises"
            planned = json.loads(user.split("wie geplant; \"choice\" heisst multiple_choice, \"short\" heisst "
                                            "text_input):\n", 1)[1].split("\n\n", 1)[0])
            items = []
            for p in planned:
                slot = p["slot"]
                if slot in self.broken:
                    self.broken.discard(slot)
                    items.append(_text_exercise(slot, accepted=[]))
                elif p["format"] == "choice":
                    items.append(_choice_exercise(slot))
                else:
                    items.append(_text_exercise(slot))
            data = {"exercises": items}
        else:
            kind = "check"
            ids = [item["id"] for item in json.loads(user.split("Aufgaben:\n", 1)[1].split("\n\n", 1)[0])]
            data = {"verdicts": [{"id": i, "verdict": "pass", "failed": []} for i in ids]}
        self.calls.append(kind)
        return draft.Reply(data, 1000, 500, 1.5, draft.DEFAULT_MODEL)


def _imported(tmp_path: Path) -> Path:
    folder = tmp_path / "imported"
    folder.mkdir()
    row = {"publicLessonId": f"{STAR}--rechnen--1", "publish": False,
           "lesson": {"unitId": STAR, "gradeLevel": "grade_8_secondary", "subjectId": "physics"},
           "exercises": [{"exerciseId": f"kb-p-001-q{n}", "type": "text_input", "prompt": "1 + 1 in N?",
                          "answerKey": "2", "explanation": "2.", "translations": {
                              loc: {"prompt": "1 + 1?", "correctAnswer": "2", "acceptedAnswers": [],
                                    "explanation": "2."} for loc in ("en", "fr", "it")}} for n in (1, 2, 3)]}
    (folder / "manifest-001.json").write_text(json.dumps({"lessons": [row]}), encoding="utf-8")
    return folder


def _run(model: FakeModel, work: Path, *args: str) -> int:
    return draft.main([*args, "--work", str(work), "--confirm-cost"], model=model)


def test_a_numeric_answer_needs_its_spellings_and_never_another_value() -> None:
    assert draft.exercise_problems(_text_exercise(1)) == []
    assert any("no other spelling" in p for p in draft.exercise_problems(_text_exercise(1, accepted=[])))
    assert any("another value" in p for p in draft.exercise_problems(_text_exercise(1, accepted=["5 N", "50 N"])))


def test_a_choice_has_one_right_option_at_the_same_place_in_every_language() -> None:
    exercise = _choice_exercise(1)
    assert draft.exercise_problems(exercise) == []
    exercise["fr"]["options"] = ["N", "kg/m³", "m/s"]
    assert any("another place" in p for p in draft.exercise_problems(exercise))
    exercise = _choice_exercise(1)
    exercise["de"]["prompt"] += " Siehe Abbildung 2."
    assert any("figure" in p for p in draft.exercise_problems(exercise))


def test_buckets_are_those_of_422() -> None:
    v = lambda verdict: {"verdict": verdict}  # noqa: E731
    assert draft.bucket(v("pass"), v("pass")) == "pass"
    assert draft.bucket(v("missing_equivalents"), v("missing_equivalents")) == "missing_equivalents"
    assert draft.bucket(v("reject"), v("reject")) == "reject"
    assert draft.bucket(v("pass"), v("missing_equivalents")) == "doubtful"


def test_spellings_the_judge_already_accepts_are_not_missing() -> None:
    item = {"de": {"correctAnswer": "0.5", "acceptedAnswers": ["0.5 m"]}}
    asked = {"verdict": "missing_equivalents", "failed": ["equivalents"], "suggestedAccepted": ["0,5", "0.5m", "0.5"]}
    assert draft.judge_covered(asked, item)["verdict"] == "pass"
    asked["suggestedAccepted"] = ["0,5", "50 cm"]
    assert draft.judge_covered(asked, item)["suggestedAccepted"] == ["50 cm"]
    wrong = {"verdict": "doubtful", "failed": ["answer", "equivalents"], "suggestedAccepted": []}
    assert draft.judge_covered(wrong, item)["verdict"] == "doubtful"


def test_the_pool_is_blind() -> None:
    pool, key = draft.blind_pool([("ai-1", {"star": STAR, "x": 1})], [("kb-1", {"star": STAR, "x": 2})], seed=1)
    assert {item["id"] for item in pool} == set(key)
    assert all("origin" not in item and "ref" not in item for item in pool)
    assert sorted(entry["origin"] for entry in key.values()) == ["drafted", "imported"]


def test_generation_waits_for_a_confirmed_and_unchanged_outline(tmp_path: Path) -> None:
    work, model = tmp_path / "work", FakeModel()
    assert _run(model, work, "outline", "--star", STAR, "--imported", str(_imported(tmp_path))) == 0
    record = json.loads((work / "outline" / f"{STAR}.json").read_text(encoding="utf-8"))
    # diagramme is not one of this star's question types: dropped, not forced.
    assert [d["planned"]["questionType"] for d in record["outline"]["dropped"]] == ["diagramme"]
    assert "Masse" in (work / "review-outlines.md").read_text(encoding="utf-8")
    with pytest.raises(draft.DraftError, match="not confirmed"):
        _run(model, work, "generate")
    assert draft.main(["confirm", "--work", str(work), "--by", "owner"]) == 0
    record["outline"]["cards"][0]["title"] = "Masse und Gewicht"
    (work / "outline" / f"{STAR}.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(draft.DraftError, match="changed after it was confirmed"):
        _run(model, work, "generate")


def test_a_failed_block_is_redone_alone_and_the_whole_line_dry_runs_clean(tmp_path: Path) -> None:
    work, model = tmp_path / "work", FakeModel(broken={2})
    imported = str(_imported(tmp_path))
    _run(model, work, "outline", "--star", STAR, "--imported", imported)
    draft.main(["confirm", "--work", str(work), "--by", "owner"])

    assert _run(model, work, "generate", "--fail", "03-exercises") == 1
    blocks = work / "blocks" / STAR
    assert sorted(p.stem for p in blocks.glob("*.json")) == ["01-cards", "02-exercises"]
    # Slot 2 came back without its spellings once and was redone inside its block.
    assert json.loads((blocks / "02-exercises.json").read_text(encoding="utf-8"))["leftOut"] == []
    model.calls.clear()
    assert _run(model, work, "generate") == 0
    assert model.calls == ["exercises"]  # only the block that failed

    assert _run(model, work, "check", "--imported", imported) == 0
    verdicts = json.loads((work / "check" / "verdicts.json").read_text(encoding="utf-8"))
    assert sorted({v["origin"] for v in verdicts}) == ["drafted", "imported"]
    assert sum(v["origin"] == "drafted" for v in verdicts) == 6

    assert _run(model, work, "manifest") == 0
    manifest = json.loads((work / "manifests" / "manifest-001.json").read_text(encoding="utf-8"))
    assert all(row["publish"] is False for row in manifest["lessons"])
    assert manifest["lessons"][0]["lesson"]["sections"][0]["translations"]["it"]["title"] == "Karte 1"
    assert _run(model, work, "dry-run") == 0
    result = json.loads((work / "dry-run.json").read_text(encoding="utf-8"))[0]
    assert result["summary"]["errors"] == 0 and result["summary"]["conflicts"] == 0
    assert _run(model, work, "report") == 0
    assert "AI 起草（核对者原判） | 6 |" in (work / "report.md").read_text(encoding="utf-8")


def test_a_run_that_calls_the_model_needs_the_operators_yes(tmp_path: Path) -> None:
    with pytest.raises(draft.DraftError, match="--confirm-cost"):
        draft.main(["outline", "--work", str(tmp_path), "--star", STAR], model=FakeModel())
    with pytest.raises(draft.DraftError, match="--max-calls"):
        draft.main(["outline", "--work", str(tmp_path), "--star", STAR, "--confirm-cost", "--max-calls", "0"],
                   model=FakeModel())
