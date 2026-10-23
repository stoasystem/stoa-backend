#!/usr/bin/env python3
"""Bring the cn-math-taxonomy knowledge base into the curriculum, in four languages.

The upstream repository (github.com/xiaoyang111222/cn-math-taxonomy, CC BY-NC
4.0) holds knowledge points for mathematics, English and physics, the
prerequisite edges between them and a question bank, written in Chinese and
filed by Chinese textbook chapter and curriculum standard. Four steps take it to
a curriculum migration manifest:

    extract   upstream data/ → source.json: knowledge points, exercises and
              prerequisites, with every textbook record left behind (chapter,
              semester, curriculum-standard ids, edition mappings, aliases, review
              logs) and new ids that do not name the source
    batches   source.json → batch files a translator fills in de/en/fr/it
    merge     source.json + filled batches → translated.json, checked
    manifest  translated.json → the skill vocabulary the platform reads, a
              manifest for POST /admin/curriculum/migrations/dry-run with every
              lesson "publish": false, and a report of what became of each record

The source text and its translations stay out of the repository: the licence
does not allow commercial use without the author's permission, which publishing
waits for. Only the skill vocabulary (knowledge point names) is committed.

    uv run python scripts/knowledge_base_import.py extract UPSTREAM/data --out source.json
    uv run python scripts/knowledge_base_import.py batches source.json --out-dir batches/
    uv run python scripts/knowledge_base_import.py merge source.json batches/ --out translated.json
    uv run python scripts/knowledge_base_import.py manifest translated.json \\
        --manifest manifest.json --report report.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import permutations
import json
from pathlib import Path
import re
import sys
from typing import Any

from stoa.services import answer_judging, knowledge_base_catalog as catalog

SOURCE_SCHEMA = "stoa-knowledge-base-source-1"
TRANSLATED_SCHEMA = "stoa-knowledge-base-translated-1"
UPSTREAM = "https://github.com/xiaoyang111222/cn-math-taxonomy"
LICENCE = "CC BY-NC 4.0"
LOCALES = catalog.LOCALES

SUBJECTS = {None: ("mathematics", "m"), "english": ("english", "e"), "physics": ("physics", "p")}
#: Upstream fields that record the Chinese textbook or curriculum, never carried.
TEXTBOOK_FIELDS = ("chapter", "semester", "standards", "root_reason", "external", "mathLinks")
#: Upstream files that are textbook or upstream-process records, never read.
TEXTBOOK_FILES = (
    "cn-curriculum-standards.json", "id-aliases.json", "mappings/", "_qbatches/",
    "_second_pass/", "second_pass_log.json", "verification_report.json",
    "_distractor_changelog.json",
)
#: Wording that points at a textbook, an edition or the upstream map; the
#: translator rewrites it as a plain convention and the merge checks it is gone.
TEXTBOOK_WORDS = re.compile(r"教材|课本|教科书|人教|课标|课程标准|本图谱|本单元|本章|第[一二三四五六七八九十\d]+单元")
CJK = re.compile(r"[㐀-鿿！-～　-〿]")
LETTERS = re.compile(r"[^\W\d_]")
POINTS_PER_BATCH = 12
MAX_UNORDERED_PARTS = 3


# ── extract ──────────────────────────────────────────────────────────────────


def point_id(source_id: str) -> str:
    prefix, _, rest = source_id.partition("_")
    letter = {"cnm": "m", "cne": "e", "cnp": "p"}.get(prefix)
    if letter is None or not rest:
        raise ValueError(f"unexpected knowledge point id {source_id!r}")
    return f"kb-{letter}-{rest.lower()}"


def exercise_id(source_id: str) -> str:
    point, _, number = source_id.rpartition("_")
    if not number.startswith("q") or not point:
        raise ValueError(f"unexpected question id {source_id!r}")
    return f"{point_id(point)}-{number}"


def _text(value: object) -> str:
    return str(value or "").strip()


def _plain_answer(value: object) -> str:
    """An upstream answer with Chinese list commas written the way the judge reads them."""
    return re.sub(r"\s*[，、]\s*", ", ", _text(value))


def _unordered_alternatives(answer: str) -> list[str]:
    parts = [part.strip() for part in answer.split(",") if part.strip()]
    if not 1 < len(parts) <= MAX_UNORDERED_PARTS:
        return []
    return [", ".join(order) for order in permutations(parts) if list(order) != parts]


def _exercise(raw: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    kind = raw.get("type")
    if raw.get("figure"):
        return None, "has a figure, and practice shows no figures yet"
    if kind not in {"choice", "numeric", "short"}:
        return None, f"question type {kind!r} is a self-assessment, not an answerable question"
    item: dict[str, Any] = {
        "id": exercise_id(raw["id"]),
        "sourceId": raw["id"],
        "point": point_id(raw["topicId"]),
        "difficulty": _text(raw.get("difficulty")) or "standard",
        "type": kind,
        "prompt": _text(raw.get("prompt")),
        "explanation": _text(raw.get("explanation")),
    }
    if kind == "choice":
        choices = [c for c in raw.get("choices") or [] if isinstance(c, Mapping)]
        keys = [_text(c.get("key")) for c in choices]
        if len(choices) < 2 or raw.get("answer") not in keys:
            return None, "choice question without its options or with an answer that is no option"
        item["choices"] = [_text(c.get("text")) for c in choices]
        item["answerIndex"] = keys.index(raw["answer"])
    else:
        answer = _plain_answer(raw.get("answer"))
        if not answer:
            return None, "no answer"
        accepted = [_plain_answer(a) for a in raw.get("accept") or [] if _text(a)]
        if raw.get("unordered"):
            accepted += _unordered_alternatives(answer)
        item["answer"] = answer
        item["accepted"] = [a for a in dict.fromkeys(accepted) if a != answer]
    if not item["prompt"] or not item["explanation"]:
        return None, "no prompt or no explanation"
    if TEXTBOOK_WORDS.search(json.dumps(item, ensure_ascii=False)):
        item["mentionsTextbook"] = True
    return item, None


def extract(data_dir: Path) -> dict[str, Any]:
    topics = json.loads((data_dir / "topics.json").read_text(encoding="utf-8"))
    questions = json.loads((data_dir / "questions.json").read_text(encoding="utf-8"))
    dependencies = json.loads((data_dir / "dependencies.json").read_text(encoding="utf-8"))

    points: list[dict[str, Any]] = []
    for raw in topics:
        subject, _ = SUBJECTS[raw.get("subject")]
        points.append({
            "id": point_id(raw["id"]),
            "sourceId": raw["id"],
            "subject": subject,
            "domain": raw["domain"],
            "grade": int(raw["grade"]),
            "kind": raw.get("type") or "conceptual",
            "name": _text(raw.get("name")),
            "description": _text(raw.get("description")),
            "mastery": [_text(m) for m in raw.get("mastery_criteria") or [] if _text(m)],
        })
    known = {p["id"] for p in points}

    exercises: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for raw in questions:
        item, reason = _exercise(raw)
        if item is None:
            skipped.append({"sourceId": raw.get("id", ""), "reason": str(reason)})
        elif item["point"] not in known:
            skipped.append({"sourceId": raw["id"], "reason": "its knowledge point is not in the map"})
        else:
            exercises.append(item)

    subject_of = {p["id"]: p["subject"] for p in points}
    prerequisites = []
    for edge in dependencies:
        point, requires = point_id(edge["topicId"]), point_id(edge["prerequisiteId"])
        if point in known and requires in known and subject_of[point] == subject_of[requires]:
            prerequisites.append({"point": point, "requires": requires, "strength": edge["strength"]})

    return {
        "schema": SOURCE_SCHEMA,
        "upstream": {"repository": UPSTREAM, "licence": LICENCE},
        "leftBehind": {"fields": list(TEXTBOOK_FIELDS), "files": list(TEXTBOOK_FILES)},
        "points": points,
        "exercises": exercises,
        "prerequisites": prerequisites,
        "skipped": skipped,
    }


# ── batches ──────────────────────────────────────────────────────────────────


def _batch_point(point: Mapping[str, Any]) -> dict[str, Any]:
    return {k: point[k] for k in ("id", "domain", "grade", "name", "description", "mastery")}


def _batch_exercise(exercise: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("id", "point", "type", "prompt", "choices", "answerIndex", "answer", "accepted",
            "explanation", "mentionsTextbook")
    return {k: exercise[k] for k in keys if k in exercise}


def batches(source: Mapping[str, Any], size: int = POINTS_PER_BATCH) -> list[dict[str, Any]]:
    by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for exercise in source["exercises"]:
        by_point[exercise["point"]].append(exercise)
    out: list[dict[str, Any]] = []
    for subject in ("mathematics", "english", "physics"):
        points = [p for p in source["points"] if p["subject"] == subject]
        for start in range(0, len(points), size):
            chunk = points[start:start + size]
            out.append({
                "batch": f"{subject}-{start // size + 1:03d}",
                "subject": subject,
                "units": catalog.unit_choices(subject),
                "points": [_batch_point(p) for p in chunk],
                "exercises": [_batch_exercise(e) for p in chunk for e in by_point[p["id"]]],
            })
    return out


# ── merge ────────────────────────────────────────────────────────────────────


def _has_letters_or_cjk(value: str) -> bool:
    return bool(CJK.search(value) or LETTERS.search(value))


def _check_point(point: Mapping[str, Any], done: object, units: Mapping[str, str]) -> list[str]:
    if not isinstance(done, Mapping):
        return ["no translation"]
    problems = []
    if units and done.get("unit") not in units:
        problems.append(f"unit {done.get('unit')!r} is not one of the stars offered")
    for locale in LOCALES:
        text = done.get(locale)
        if not isinstance(text, Mapping) or not _text(text.get("name")):
            problems.append(f"{locale}: no name")
            continue
        if len(text.get("mastery") or []) != len(point["mastery"]):
            problems.append(f"{locale}: {len(point['mastery'])} mastery criteria expected")
        if CJK.search(json.dumps(text, ensure_ascii=False)):
            problems.append(f"{locale}: Chinese left in the text")
    return problems


def _check_exercise(exercise: Mapping[str, Any], done: object) -> list[str]:
    if not isinstance(done, Mapping):
        return ["no translation"]
    if "drop" in done:
        return [] if _text(done["drop"]) else ["dropped without a reason"]
    problems = []
    for locale in LOCALES:
        text = done.get(locale)
        if not isinstance(text, Mapping) or not _text(text.get("prompt")) or not _text(text.get("explanation")):
            problems.append(f"{locale}: no prompt or explanation")
            continue
        if exercise["type"] == "choice":
            choices = text.get("choices") or []
            if len(choices) != len(exercise["choices"]) or not all(_text(c) for c in choices):
                problems.append(f"{locale}: {len(exercise['choices'])} options expected")
            elif len({answer_judging.normalize_answer(c) for c in choices}) != len(choices):
                problems.append(f"{locale}: two options read the same")
        else:
            answer = _text(text.get("answer"))
            if not answer:
                problems.append(f"{locale}: no answer")
            elif not _has_letters_or_cjk(exercise["answer"]) and not answer_judging.judge(
                answer, exercise["answer"]
            ):
                problems.append(f"{locale}: the answer {answer!r} is not the value {exercise['answer']!r}")
        if CJK.search(json.dumps(text, ensure_ascii=False)):
            problems.append(f"{locale}: Chinese left in the text")
        if TEXTBOOK_WORDS.search(json.dumps(text, ensure_ascii=False)):
            problems.append(f"{locale}: still points at a textbook")
    return problems


def merge(source: Mapping[str, Any], filled: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    point_texts: dict[str, Any] = {}
    exercise_texts: dict[str, Any] = {}
    for batch in filled:
        point_texts.update(batch.get("points") or {})
        exercise_texts.update(batch.get("exercises") or {})

    problems: list[dict[str, Any]] = []
    points = []
    for point in source["points"]:
        done = point_texts.get(point["id"])
        units = catalog.unit_choices(point["subject"])
        found = _check_point(point, done, units)
        if found:
            problems.append({"id": point["id"], "problems": found})
            continue
        points.append({
            **{k: point[k] for k in ("id", "sourceId", "subject", "grade", "kind")},
            "unit": done["unit"],
            "text": {locale: dict(done[locale]) for locale in LOCALES},
        })
    kept = {p["id"] for p in points}

    exercises, dropped = [], []
    for exercise in source["exercises"]:
        done = exercise_texts.get(exercise["id"])
        found = _check_exercise(exercise, done)
        if found:
            problems.append({"id": exercise["id"], "problems": found})
        elif "drop" in done:
            dropped.append({"sourceId": exercise["sourceId"], "reason": f"translator: {done['drop']}"})
        elif exercise["point"] not in kept:
            dropped.append({"sourceId": exercise["sourceId"], "reason": "its knowledge point was not translated"})
        else:
            item = {k: exercise[k] for k in ("id", "sourceId", "point", "difficulty", "type")}
            if exercise["type"] == "choice":
                item["answerIndex"] = exercise["answerIndex"]
            item["text"] = {locale: dict(done[locale]) for locale in LOCALES}
            exercises.append(item)

    prerequisites = [
        edge for edge in source["prerequisites"] if edge["point"] in kept and edge["requires"] in kept
    ]
    return {
        "schema": TRANSLATED_SCHEMA,
        "upstream": source["upstream"],
        "points": points,
        "exercises": exercises,
        "prerequisites": prerequisites,
        "skipped": [*source["skipped"], *dropped],
        "problems": problems,
    }


# ── manifest ─────────────────────────────────────────────────────────────────

#: The authoring limits of CurriculumLessonDraftRequest / CurriculumExerciseDraftRequest,
#: as scripts/editorial_batch_to_migration.py applies them: a migration row does not
#: pass through those request models. A text over its limit is skipped, never shortened.
MAX_TITLE = 300
MAX_OBJECTIVE = 1000
MAX_TEXT = 2000
MAX_OPTION = 500
#: As the editorial converter estimates a lesson, and numbers it after the seeded ones.
MINUTES_PER_EXERCISE = 3
FIRST_IMPORTED_ORDER = 101
#: Lessons per manifest file: one dry run per file keeps each request small.
LESSONS_PER_MANIFEST = 40
SOURCE_ID = "knowledge-base"
OPERATOR_NOTE = (
    "Knowledge base adapted from cn-math-taxonomy (CC BY-NC 4.0; commercial use needs the "
    "author's written permission before anything is published). AI-written source, "
    "machine-translated into de/en/fr/it: every lesson is a draft for a teacher's review."
)


def _exercise_type(kind: str) -> str:
    return "multiple_choice" if kind == "choice" else "text_input"


def _too_long(text: Mapping[str, Any]) -> str | None:
    for field, limit in (("prompt", MAX_TEXT), ("explanation", MAX_TEXT), ("answer", MAX_TEXT)):
        if len(_text(text.get(field))) > limit:
            return f"{field} is longer than {limit} characters"
    if any(len(_text(c)) > MAX_OPTION for c in text.get("choices") or []):
        return f"an option is longer than {MAX_OPTION} characters"
    accepted = text.get("accepted") or []
    if len(accepted) > answer_judging.MAX_ACCEPTED_ANSWERS or any(
        len(_text(a)) > answer_judging.MAX_ACCEPTED_ANSWER_LENGTH for a in accepted
    ):
        return "too many or too long accepted answers"
    return None


def _locale_exercise(exercise: Mapping[str, Any], text: Mapping[str, Any]) -> dict[str, Any]:
    if exercise["type"] == "choice":
        choices = [_text(c) for c in text["choices"]]
        return {"prompt": _text(text["prompt"]), "options": choices,
                "correctAnswer": choices[exercise["answerIndex"]],
                "explanation": _text(text["explanation"])}
    answer = _text(text["answer"])
    accepted = [a for a in dict.fromkeys(_text(a) for a in text.get("accepted") or []) if a and a != answer]
    return {"prompt": _text(text["prompt"]), "correctAnswer": answer, "acceptedAnswers": accepted,
            "explanation": _text(text["explanation"])}


def _manifest_exercise(exercise: Mapping[str, Any], order: int) -> dict[str, Any]:
    german = _locale_exercise(exercise, exercise["text"]["de"])
    row = {
        "exerciseId": exercise["id"],
        "type": _exercise_type(exercise["type"]),
        "difficulty": exercise["difficulty"],
        "order": order,
        "prompt": german["prompt"],
        "answerKey": german["correctAnswer"],
        "explanation": german["explanation"],
        "skills": [exercise["point"]],
        "translations": {
            locale: _locale_exercise(exercise, exercise["text"][locale])
            for locale in LOCALES if locale != "de"
        },
    }
    if "options" in german:
        row["options"] = german["options"]
    if german.get("acceptedAnswers"):
        row["acceptedAnswers"] = german["acceptedAnswers"]
    return row


def _lesson_problem(point: Mapping[str, Any]) -> str | None:
    german = point["text"]["de"]
    if len(_text(german.get("name"))) > MAX_TITLE:
        return f"name is longer than {MAX_TITLE} characters"
    if len(_text(german.get("description"))) > MAX_OBJECTIVE:
        return f"description is longer than {MAX_OBJECTIVE} characters"
    return None


def skill_vocabulary(translated: Mapping[str, Any]) -> dict[str, Any]:
    """The file knowledge_base_catalog reads: each knowledge point's skill, star and names."""
    return {
        "source": {"repository": UPSTREAM, "licence": LICENCE},
        "skills": {
            point["id"]: {
                "subject": point["subject"],
                "unit": point["unit"],
                "titles": {locale: _text(point["text"][locale]["name"]) for locale in LOCALES},
            }
            for point in sorted(translated["points"], key=lambda p: p["id"])
        },
    }


def manifests(
    translated: Mapping[str, Any], source_version: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Migration manifests of draft lessons, one lesson per knowledge point, and the report."""
    units = {unit["unit_id"]: unit for unit in catalog.units()}
    zap_topics = {unit_id: unit_id.rsplit("-u", 1)[0] for unit_id in catalog.ZAP_UNITS}
    by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for exercise in translated["exercises"]:
        by_point[exercise["point"]].append(exercise)

    report_points, report_exercises = [], []
    skipped = list(translated["skipped"])
    rows_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in sorted(translated["points"], key=lambda p: (p["grade"], p["sourceId"])):
        unit_id = point["unit"]
        topic_id = units[unit_id]["topic_id"] if unit_id in units else zap_topics[unit_id]
        problem = _lesson_problem(point)
        carried = []
        for exercise in by_point.get(point["id"], []):
            reason = next(filter(None, (_too_long(exercise["text"][locale]) for locale in LOCALES)), None)
            if reason:
                skipped.append({"sourceId": exercise["sourceId"], "reason": reason})
            else:
                carried.append(exercise)
        if problem or not carried:
            reason = problem or "no exercise of it could be carried over"
            report_points.append({"sourceId": point["sourceId"], "skill": point["id"], "lesson": None,
                                  "reason": reason})
            continue
        german = point["text"]["de"]
        rows_by_unit[unit_id].append({
            "publicLessonId": point["id"],
            "publish": False,
            "lesson": {
                "title": _text(german["name"]),
                "objective": _text(german["description"]) or _text(german["name"]),
                "description": _text(german["description"]),
                "objectives": [_text(m) for m in german.get("mastery") or []],
                "subjectId": point["subject"],
                "topicId": topic_id,
                "unitId": unit_id,
                "gradeLevel": catalog.grade_level(point["grade"]),
                "difficulty": "practice",
                "estimatedMinutes": max(5, MINUTES_PER_EXERCISE * len(carried)),
                "language": "de",
            },
            "exercises": [_manifest_exercise(e, order) for order, e in enumerate(carried, start=1)],
        })
        report_points.append({"sourceId": point["sourceId"], "skill": point["id"], "lesson": point["id"],
                              "unit": unit_id})
        report_exercises.extend(
            {"sourceId": e["sourceId"], "exercise": e["id"], "lesson": point["id"]} for e in carried
        )

    rows: list[dict[str, Any]] = []
    for unit_rows in rows_by_unit.values():
        for order, row in enumerate(unit_rows, start=FIRST_IMPORTED_ORDER):
            row["lesson"]["order"] = order
            rows.append(row)
    rows.sort(key=lambda row: (row["lesson"]["subjectId"], row["lesson"]["unitId"], row["lesson"]["order"]))

    lessons = {row["publicLessonId"]: row["lesson"] for row in rows}
    later_prerequisites = [
        edge for edge in translated["prerequisites"]
        if edge["point"] in lessons and edge["requires"] in lessons
        and (lessons[edge["point"]]["unitId"] == lessons[edge["requires"]]["unitId"]
             or lessons[edge["point"]]["topicId"] == lessons[edge["requires"]]["topicId"])
    ]
    out = [
        {
            "source": {"sourceId": SOURCE_ID, "sourceVersion": source_version, "sourceType": "knowledge_base"},
            "operatorNote": OPERATOR_NOTE,
            "lessons": rows[start:start + LESSONS_PER_MANIFEST],
        }
        for start in range(0, len(rows), LESSONS_PER_MANIFEST)
    ]
    report = {
        "upstream": translated["upstream"],
        "sourceVersion": source_version,
        "leftBehind": {
            "fields": list(TEXTBOOK_FIELDS),
            "files": list(TEXTBOOK_FILES),
            "note": "chapter, semester and curriculum-standard records of the Chinese textbooks are not carried",
        },
        "summary": {
            "lessons": len(rows),
            "exercises": len(report_exercises),
            "skipped": len(skipped),
            "manifests": len(out),
            "prerequisitesForLater": len(later_prerequisites),
        },
        "points": report_points,
        "exercises": report_exercises,
        "skipped": skipped,
        # Lesson prerequisites must name lessons that already exist, so they are set
        # once these lessons are published (PATCH the draft's prerequisiteLessonIds).
        "prerequisitesForLater": later_prerequisites,
    }
    return out, report


# ── command line ─────────────────────────────────────────────────────────────


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("extract")
    p.add_argument("data_dir", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("batches")
    p.add_argument("source", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--size", type=int, default=POINTS_PER_BATCH)
    p = commands.add_parser("merge")
    p.add_argument("source", type=Path)
    p.add_argument("filled_dir", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("manifest")
    p.add_argument("translated", type=Path)
    p.add_argument("--out-dir", type=Path, required=True, help="manifest-NNN.json files and report.json")
    p.add_argument("--vocabulary", type=Path, default=catalog.SKILLS_FILE)
    p.add_argument("--source-version", required=True, help="the upstream commit translated")
    args = parser.parse_args(argv)

    if args.command == "extract":
        source = extract(args.data_dir)
        _write(args.out, source)
        print(f"{len(source['points'])} knowledge points, {len(source['exercises'])} exercises, "
              f"{len(source['prerequisites'])} prerequisites, {len(source['skipped'])} skipped")
    elif args.command == "batches":
        made = batches(_read(args.source), args.size)
        for batch in made:
            _write(args.out_dir / f"{batch['batch']}.json", batch)
        print(f"{len(made)} batches in {args.out_dir}")
    elif args.command == "merge":
        filled = [_read(path) for path in sorted(args.filled_dir.glob("*.out.json"))]
        merged = merge(_read(args.source), filled)
        _write(args.out, merged)
        print(f"{len(merged['points'])} knowledge points, {len(merged['exercises'])} exercises, "
              f"{len(merged['problems'])} records with problems")
        return 1 if merged["problems"] else 0
    elif args.command == "manifest":
        translated = _read(args.translated)
        if translated["problems"]:
            print(f"{len(translated['problems'])} records still have problems; fix them and merge again")
            return 1
        made, report = manifests(translated, args.source_version)
        for index, manifest in enumerate(made, start=1):
            _write(args.out_dir / f"manifest-{index:03d}.json", manifest)
        _write(args.out_dir / "report.json", report)
        _write(args.vocabulary, skill_vocabulary(translated))
        print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
