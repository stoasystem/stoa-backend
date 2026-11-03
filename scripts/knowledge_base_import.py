#!/usr/bin/env python3
"""Bring the cn-math-taxonomy knowledge base into the curriculum, in four languages.

The upstream repository (github.com/xiaoyang111222/cn-math-taxonomy, CC BY-NC
4.0) holds knowledge points for mathematics, English and physics, the
prerequisite edges between them and a question bank, written in Chinese and
filed by Chinese textbook chapter and curriculum standard. These steps take it
to curriculum migration manifests:

    extract            upstream data/ → source.json: knowledge points, exercises
                       and prerequisites, with every textbook record left behind
                       (chapter, semester, curriculum-standard ids, edition
                       mappings, aliases, review logs) and ids that do not name it
    batches            source.json → batches a translator fills in de/en/fr/it,
                       filing each point under a coarse star
    merge              source.json + filled batches → translated.json, checked
    structure-batches  translated.json → batches a structurer fills: each coarse
                       star split into knowledge-point stars, each exercise
                       tagged with its question type
    merge-batches      translated.json + structure.json → per nebula, batches a
                       structurer fills: the stars joined into stars of 6 to 12
                       points, overlapping stars made one
    structure          translated.json + filled batches (+ --merges) →
                       structure.json, checked, with the stars' prerequisites
    manifest           translated.json + structure.json → the star file and the
                       skill vocabulary the platform reads, manifests for
                       POST /admin/curriculum/migrations/dry-run of practice sets
                       - one per small star, every one "publish": false - and a
                       report of what became of each record

The source text and its translations stay out of the repository: the licence
does not allow commercial use without the author's permission, which publishing
waits for. Only the star file and the vocabulary (names) are committed. The
operator steps are in docs/knowledge-base-import.md.
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
STRUCTURE_SCHEMA = "stoa-knowledge-base-structure-1"
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
        if exercise.get("pictureOptions"):
            # The options are their pictures; their words would give the answer
            # away, so each is shown under a letter.
            choices = [chr(ord("A") + index) for index in range(len(choices))]
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
        "skills": [exercise["point"]] if exercise.get("point") else [],
        "translations": {
            locale: _locale_exercise(exercise, exercise["text"][locale])
            for locale in LOCALES if locale != "de"
        },
    }
    if "options" in german:
        row["options"] = german["options"]
    if german.get("acceptedAnswers"):
        row["acceptedAnswers"] = german["acceptedAnswers"]
    # A figure is drawn once, in German; a locale whose figure carries translated
    # words has its own, the others show the German one.
    base = exercise["text"]["de"]
    if _text(base.get("figure")):
        row["figure"] = base["figure"]
    if any(_text(f) for f in base.get("choiceFigures") or []):
        row["optionFigures"] = [_text(f) for f in base["choiceFigures"]]
    for locale, translation in row["translations"].items():
        text = exercise["text"][locale]
        if _text(text.get("figure")) and text["figure"] != base.get("figure"):
            translation["figure"] = text["figure"]
        if any(_text(f) for f in text.get("choiceFigures") or []) and text["choiceFigures"] != base.get("choiceFigures"):
            translation["optionFigures"] = [_text(f) for f in text["choiceFigures"]]
    return row


def _star_problems(star: Mapping[str, Any]) -> list[str]:
    problems = []
    if not STAR_SLUG.fullmatch(_text(star.get("slug"))):
        problems.append(f"slug {star.get('slug')!r} is not lower-case words joined by hyphens")
    titles = star.get("titles")
    if not isinstance(titles, Mapping):
        return [*problems, "no titles"]
    for locale in LOCALES:
        title = _text(titles.get(locale))
        if not title or len(title) > MAX_STAR_TITLE:
            problems.append(f"{locale}: no title or one longer than {MAX_STAR_TITLE} characters")
        elif CJK.search(title):
            problems.append(f"{locale}: Chinese left in the title")
    description = _text(star.get("description"))
    if not description or len(description) > MAX_OBJECTIVE or CJK.search(description):
        problems.append("no German description, or one too long or with Chinese in it")
    if len(star.get("points") or []) > catalog.MAX_POINTS_PER_STAR:
        problems.append(f"more than {catalog.MAX_POINTS_PER_STAR} knowledge points")
    return problems


# ── structure ────────────────────────────────────────────────────────────────
#
# The translation files each knowledge point under a coarse star. Structuring
# splits every coarse star into knowledge-point stars of at most
# MAX_POINTS_PER_STAR upstream points, and tags every exercise with the question
# type it practises: the small star it trains.

#: Exercises per structuring batch: a coarse star is never split across batches.
EXERCISES_PER_STRUCTURE_BATCH = 250
STAR_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_STAR_SLUG = 48
MAX_STAR_TITLE = 80
PROMPT_PREVIEW = 220


def structure_batches(
    translated: Mapping[str, Any], size: int = EXERCISES_PER_STRUCTURE_BATCH
) -> list[dict[str, Any]]:
    """Coarse stars with their points and exercises, packed into batches per subject."""
    by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for exercise in translated["exercises"]:
        by_point[exercise["point"]].append(exercise)
    titles = {unit["unit_id"]: unit["titles"]["de"] for unit in catalog.grouping_units()}
    out: list[dict[str, Any]] = []
    for subject in ("mathematics", "english", "physics"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for point in sorted(translated["points"], key=lambda p: (p["grade"], p["sourceId"])):
            if point["subject"] == subject:
                groups[point["unit"]].append(point)
        batch: list[dict[str, Any]] = []
        count = 0
        for group_id, points in groups.items():
            exercises = [
                {
                    "id": e["id"],
                    "point": e["point"],
                    "kind": e["type"],
                    "prompt": _text(e["text"]["de"]["prompt"])[:PROMPT_PREVIEW],
                    **({"options": e["text"]["de"]["choices"]} if e["type"] == "choice" else {}),
                }
                for point in points for e in by_point.get(point["id"], [])
            ]
            if batch and count + len(exercises) > size:
                out.append(_structure_batch(subject, len(out), batch))
                batch, count = [], 0
            batch.append({
                "group": group_id,
                "nebula": catalog.topic_of_group(group_id),
                "title": titles.get(group_id) or catalog.ZAP_UNITS.get(group_id, group_id),
                "points": [
                    {"id": p["id"], "grade": p["grade"], "name": _text(p["text"]["de"]["name"]),
                     "description": _text(p["text"]["de"]["description"])}
                    for p in points
                ],
                "exercises": exercises,
            })
            count += len(exercises)
        if batch:
            out.append(_structure_batch(subject, len(out), batch))
    return out


def _structure_batch(subject: str, index: int, groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "batch": f"structure-{subject}-{index + 1:03d}",
        "subject": subject,
        "maxPointsPerStar": catalog.MAX_POINTS_PER_STAR,
        "questionTypes": catalog.question_types(subject),
        "groups": groups,
    }


def _closes_cycle(graph: Mapping[str, set[str]], start: str, target: str) -> bool:
    """Whether `target` already leads back to `start`."""
    seen, pending = set(), [target]
    while pending:
        node = pending.pop()
        if node == start:
            return True
        if node not in seen:
            seen.add(node)
            pending.extend(graph.get(node, ()))
    return False


def star_prerequisites(
    point_star: Mapping[str, str], edges: Iterable[Mapping[str, Any]]
) -> dict[str, list[str]]:
    """Star-level prerequisites from the upstream hard edges between knowledge points.

    An edge between points of two stars becomes an edge between the stars; the
    heaviest links are kept first, and a link that would close a cycle is left out."""
    weights: dict[tuple[str, str], int] = defaultdict(int)
    for edge in edges:
        if edge["strength"] != "hard":
            continue
        star, requires = point_star.get(edge["point"]), point_star.get(edge["requires"])
        if star and requires and star != requires:
            weights[(star, requires)] += 1
    graph: dict[str, set[str]] = defaultdict(set)
    for (star, requires), _weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
        if not _closes_cycle(graph, star, requires):
            graph[star].add(requires)
    return {star: sorted(requires) for star, requires in graph.items()}


def structure(
    translated: Mapping[str, Any],
    filled: Iterable[Mapping[str, Any]],
    merges: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Knowledge-point stars and question types, checked; with the problems found.

    `merges` are filled merge batches: per nebula, the stars of the first pass
    joined into stars of MIN_MERGED_POINTS to MAX_POINTS_PER_STAR points."""
    points = {p["id"]: p for p in translated["points"]}
    subject_of = {p["id"]: p["subject"] for p in translated["points"]}
    groups: dict[str, list[str]] = defaultdict(list)
    for point in translated["points"]:
        groups[point["unit"]].append(point["id"])

    stars_by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    types: dict[str, str] = {}
    for batch in filled:
        for star in batch.get("stars") or []:
            stars_by_group[_text(star.get("group"))].append(star)
        types.update(batch.get("exercises") or {})

    problems: list[dict[str, Any]] = []
    stars: dict[str, dict[str, Any]] = {}
    point_star: dict[str, str] = {}
    for group_id, members in groups.items():
        offered = stars_by_group.get(group_id, [])
        placed = [pid for star in offered for pid in star.get("points") or []]
        if sorted(placed) != sorted(members):
            missing, extra = set(members) - set(placed), set(placed) - set(members)
            repeated = {pid for pid in placed if placed.count(pid) > 1}
            problems.append({"id": group_id, "problems": [
                f"points not in exactly one star: missing {sorted(missing)}, "
                f"not of this group {sorted(extra)}, repeated {sorted(repeated)}"
            ]})
            continue
        nebula = catalog.topic_of_group(group_id)
        for star in offered:
            found = _star_problems(star)
            if found:
                problems.append({"id": f"{group_id}/{star.get('slug')}", "problems": found})
                continue
            base = f"{nebula}-{_text(star['slug'])}"[: len(nebula) + 1 + MAX_STAR_SLUG]
            unit_id, n = base, 2
            while unit_id in stars or unit_id in catalog.ZAP_UNITS:
                unit_id, n = f"{base}-{n}", n + 1
            grades = [points[pid]["grade"] for pid in star["points"]]
            stars[unit_id] = {
                "topic_id": nebula,
                "subject_id": subject_of[star["points"][0]],
                "titles": {locale: _text(star["titles"][locale]) for locale in LOCALES},
                "description": _text(star["description"]),
                "points": list(star["points"]),
                "grades": [min(grades), max(grades)],
            }
            point_star.update({pid: unit_id for pid in star["points"]})

    for exercise in translated["exercises"]:
        offered_types = catalog.question_types(subject_of[exercise["point"]])
        if types.get(exercise["id"]) not in offered_types:
            problems.append({"id": exercise["id"], "problems": [
                f"question type {types.get(exercise['id'])!r} is not one of {sorted(offered_types)}"
            ]})

    merges = list(merges)
    if merges:
        stars, point_star, found = apply_merges(stars, merges, points)
        problems.extend(found)

    # Map order: within a nebula, after its ZAP stars, by the youngest grade first.
    by_nebula: dict[str, list[str]] = defaultdict(list)
    for unit_id, star in stars.items():
        by_nebula[star["topic_id"]].append(unit_id)
    for nebula, unit_ids in by_nebula.items():
        first = 1 + sum(1 for zap in catalog.ZAP_UNITS if zap.startswith(f"{nebula}-"))
        ordered = sorted(unit_ids, key=lambda u: (stars[u]["grades"][0], stars[u]["grades"][1], u))
        for order, unit_id in enumerate(ordered, start=first):
            stars[unit_id]["order"] = order
    prerequisites = star_prerequisites(point_star, translated["prerequisites"])
    for unit_id, star in stars.items():
        star["prerequisites"] = prerequisites.get(unit_id, [])
    return {
        "schema": STRUCTURE_SCHEMA,
        "stars": dict(sorted(stars.items(), key=lambda item: (item[1]["topic_id"], item[1].get("order", 0)))),
        "points": point_star,
        "exercises": {e["id"]: types.get(e["id"]) for e in translated["exercises"]},
        "problems": problems,
    }


# ── manifest ─────────────────────────────────────────────────────────────────

# ── merge stars ──────────────────────────────────────────────────────────────
#
# The first pass names a star for every knowledge point a teacher would name, and
# makes them small: most hold two to four upstream points. The merge pass joins
# the stars of one nebula into stars of MIN_MERGED_POINTS to MAX_POINTS_PER_STAR
# points, and makes one star of two that overlap.

MIN_MERGED_POINTS = 6


def merge_batches(translated: Mapping[str, Any], built: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One batch per nebula: its stars, with their points named."""
    names = {p["id"]: _text(p["text"]["de"]["name"]) for p in translated["points"]}
    by_nebula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit_id, star in built["stars"].items():
        by_nebula[star["topic_id"]].append({
            "id": unit_id,
            "title": star["titles"]["de"],
            "description": star["description"],
            "grades": star["grades"],
            "points": [{"id": pid, "name": names[pid]} for pid in star["points"]],
        })
    return [
        {
            "batch": f"merge-{nebula}",
            "nebula": nebula,
            "subject": catalog.subject_of_topic(nebula),
            "minPoints": MIN_MERGED_POINTS,
            "maxPoints": catalog.MAX_POINTS_PER_STAR,
            "stars": sorted(stars, key=lambda s: (s["grades"][0], s["id"])),
        }
        for nebula, stars in sorted(by_nebula.items())
    ]


def apply_merges(
    stars: Mapping[str, dict[str, Any]],
    merges: Iterable[Mapping[str, Any]],
    points: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    """The stars after the merge pass; a nebula without a merge keeps its stars."""
    by_nebula: dict[str, list[str]] = defaultdict(list)
    for unit_id, star in stars.items():
        by_nebula[star["topic_id"]].append(unit_id)
    merged: dict[str, dict[str, Any]] = {}
    problems: list[dict[str, Any]] = []
    done: set[str] = set()
    for batch in merges:
        nebula = _text(batch.get("nebula"))
        old = by_nebula.get(nebula, [])
        new_stars = batch.get("stars") or []
        taken = [u for star in new_stars for u in star.get("from") or []]
        if sorted(taken) != sorted(old):
            problems.append({"id": f"merge-{nebula}", "problems": [
                f"stars not in exactly one merged star: missing {sorted(set(old) - set(taken))}, "
                f"unknown {sorted(set(taken) - set(old))}, "
                f"repeated {sorted({u for u in taken if taken.count(u) > 1})}"
            ]})
            continue
        total = sum(len(stars[u]["points"]) for u in old)
        floor = min(MIN_MERGED_POINTS - 1, total)
        for star in new_stars:
            joined = [pid for u in star["from"] for pid in stars[u]["points"]]
            candidate = {**star, "points": joined}
            found = _star_problems(candidate)
            if len(joined) < floor:
                found.append(f"fewer than {floor} knowledge points")
            if found:
                problems.append({"id": f"merge-{nebula}/{star.get('slug')}", "problems": found})
                continue
            base = f"{nebula}-{_text(star['slug'])}"[: len(nebula) + 1 + MAX_STAR_SLUG]
            unit_id, n = base, 2
            while unit_id in merged or unit_id in catalog.ZAP_UNITS:
                unit_id, n = f"{base}-{n}", n + 1
            joined.sort(key=lambda pid: (points[pid]["grade"], points[pid]["sourceId"]))
            grades = [points[pid]["grade"] for pid in joined]
            merged[unit_id] = {
                "topic_id": nebula,
                "subject_id": stars[star["from"][0]]["subject_id"],
                "titles": {locale: _text(star["titles"][locale]) for locale in LOCALES},
                "description": _text(star["description"]),
                "points": joined,
                "grades": [min(grades), max(grades)],
            }
        done.add(nebula)
    for unit_id, star in stars.items():
        if star["topic_id"] not in done:
            merged[unit_id] = star
    point_star = {pid: unit_id for unit_id, star in merged.items() for pid in star["points"]}
    return merged, point_star, problems


#: A small star's exercises are cut into practice sets of at most this many.
EXERCISES_PER_SET = 10
#: A stage of a small star with fewer exercises than this joins the next one (or,
#: when it is the last, the one before), so a practice set is more than a question.
MIN_EXERCISES_PER_SET = 3
PART = {"de": "Teil", "en": "Part", "fr": "Partie", "it": "Parte"}
STAGE = {"de": "Stufe", "en": "Level", "fr": "Niveau", "it": "Livello"}
#: Inside a star its knowledge points are layered by the upstream edges between
#: them; deeper chains share the last layer.
MAX_LAYERS = 4


def point_layers(
    star_points: Sequence[str], edges: Iterable[Mapping[str, Any]]
) -> dict[str, int]:
    """Each knowledge point's layer inside its star: 1 when nothing in the star
    comes before it, else one more than the deepest point it needs."""
    mine = set(star_points)
    graph: dict[str, set[str]] = defaultdict(set)
    # In the upstream's own order: where two edges close a cycle, the later one goes.
    for edge in edges:
        point, requires = edge["point"], edge["requires"]
        if edge["strength"] == "hard" and point in mine and requires in mine and point != requires:
            if not _closes_cycle(graph, point, requires):
                graph[point].add(requires)
    layers: dict[str, int] = {}

    def layer(point: str) -> int:
        if point not in layers:
            layers[point] = 1 + max((layer(r) for r in graph.get(point, ())), default=0)
        return layers[point]

    return {point: min(layer(point), MAX_LAYERS) for point in star_points}


def stages(by_layer: Mapping[int, Sequence[Any]]) -> list[tuple[int, int, list[Any]]]:
    """A small star's layers as stages (first layer, last layer, exercises): in
    layer order, a stage under MIN_EXERCISES_PER_SET takes in the next layer, and
    a thin last stage joins the one before it."""
    out: list[tuple[int, int, list[Any]]] = []
    for layer, exercises in sorted(by_layer.items()):
        if out and len(out[-1][2]) < MIN_EXERCISES_PER_SET:
            first, _last, held = out[-1]
            out[-1] = (first, layer, [*held, *exercises])
        else:
            out.append((layer, layer, list(exercises)))
    if len(out) > 1 and len(out[-1][2]) < MIN_EXERCISES_PER_SET:
        _first, last, held = out.pop()
        first, _last, before = out[-1]
        out[-1] = (first, last, [*before, *held])
    return out


def parts(exercises: Sequence[Any]) -> list[list[Any]]:
    """Exercises cut into as few practice sets of at most EXERCISES_PER_SET as
    they need, of even size, so no part is a leftover question or two."""
    count = -(-len(exercises) // EXERCISES_PER_SET)
    size = -(-len(exercises) // count) if count else 0
    return [list(exercises[i:i + size]) for i in range(0, len(exercises), size)] if size else []


def _requires(edges: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Every knowledge point's hard prerequisites, in any star of its subject."""
    out: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge["strength"] == "hard":
            out[edge["point"]].add(edge["requires"])
    return out


def _exercise_order(points: Mapping[str, Mapping[str, Any]]):
    def key(exercise: Mapping[str, Any]) -> tuple:
        point = points[exercise["point"]]
        number = int(re.sub(r"\D", "", exercise["id"].rsplit("-q", 1)[1]) or 0)
        return point["grade"], point["sourceId"], number
    return key


def figure_exercises(
    staging: Mapping[str, Any], filled: Iterable[Mapping[str, Any]], translated: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """The knowledge base's exercises with a figure, translated: in the shape of
    translated.json, with their question types, the dropped ones and the problems.

    A figure whose labels needed no translation is not repeated per locale: the
    source figure is the German one, and every locale shows it."""
    done: dict[str, Any] = {}
    for batch in filled:
        done.update(batch.get("exercises") or {})
    points = {p["id"] for p in translated["points"]}
    kept, types, dropped, problems = [], {}, [], []
    for item in staging["exercises"]:
        entry = done.get(item["id"])
        if not isinstance(entry, Mapping):
            problems.append({"id": item["id"], "problems": ["not translated"]})
            continue
        if "drop" in entry:
            dropped.append({"sourceId": item["sourceId"], "reason": f"translator: {entry['drop']}"})
            continue
        if item["point"] not in points:
            dropped.append({"sourceId": item["sourceId"], "reason": "its knowledge point was not translated"})
            continue
        found = [] if entry.get("type") in catalog.question_types(item["subject"]) else ["no question type"]
        text = {}
        for locale in LOCALES:
            given = entry.get(locale)
            if not isinstance(given, Mapping):
                found.append(f"{locale}: no text")
                continue
            text[locale] = dict(given)
            if locale == "de":
                text[locale].setdefault("figure", item.get("figure") or "")
                if item.get("choiceFigures"):
                    text[locale].setdefault("choiceFigures", list(item["choiceFigures"]))
        if found:
            problems.append({"id": item["id"], "problems": found})
            continue
        exercise = {k: item[k] for k in ("id", "sourceId", "point", "difficulty", "type")}
        if item["type"] == "choice":
            exercise["answerIndex"] = item["answerIndex"]
            if item.get("hideChoiceText"):
                exercise["pictureOptions"] = True
        exercise["text"] = text
        kept.append(exercise)
        types[item["id"]] = entry["type"]
    return kept, types, dropped, problems


def with_figures(
    translated: Mapping[str, Any], figured: Iterable[Mapping[str, Any]], dropped: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """translated.json with the figure exercises in it. A choice exercise whose
    options are pictures was translated once without them; its figure version
    takes its place, so no lesson holds the same exercise twice."""
    figured = list(figured)
    ids = {exercise["id"] for exercise in figured}
    return {
        **translated,
        "exercises": [*(e for e in translated["exercises"] if e["id"] not in ids), *figured],
        "skipped": [*(row for row in translated["skipped"] if "figure" not in row["reason"]), *dropped],
    }


def zap_exercises(
    staging: Mapping[str, Any], filled: Iterable[Mapping[str, Any]], built: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The adapted ZAP exercises (#106) as filed and translated: each under a
    mathematics star with its question type; with the dropped ones and the problems."""
    done: dict[str, Any] = {}
    for batch in filled:
        done.update(batch.get("exercises") or {})
    stars = {u for u, star in built["stars"].items() if star["subject_id"] == "mathematics"}
    types = catalog.question_types("mathematics")
    kept, dropped, problems = [], [], []
    for item in staging["exercises"]:
        entry = done.get(item["id"])
        if not isinstance(entry, Mapping):
            problems.append({"id": item["id"], "problems": ["not filed"]})
            continue
        if "drop" in entry:
            dropped.append({"sourceId": item["editorialId"], "reason": f"ZAP: {entry['drop']}"})
            continue
        found = []
        if entry.get("star") not in stars:
            found.append(f"star {entry.get('star')!r} is not a mathematics star")
        if entry.get("type") not in types:
            found.append(f"type {entry.get('type')!r} is not a mathematics question type")
        for locale in LOCALES:
            text = entry.get(locale)
            if not isinstance(text, Mapping) or not all(_text(text.get(k)) for k in ("prompt", "answer", "explanation")):
                found.append(f"{locale}: prompt, answer and explanation are all needed")
            elif CJK.search(json.dumps(text, ensure_ascii=False)):
                found.append(f"{locale}: Chinese left in the text")
        if found:
            problems.append({"id": item["id"], "problems": found})
            continue
        kept.append({
            "id": item["id"],
            "sourceId": item["editorialId"],
            "original": item["original"],
            "star": entry["star"],
            "questionType": entry["type"],
            "type": "numeric",
            "difficulty": "zap",
            "text": {locale: dict(entry[locale]) for locale in LOCALES},
        })
    return kept, dropped, problems


def manifests(
    translated: Mapping[str, Any],
    built: Mapping[str, Any],
    source_version: str,
    zap: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Draft practice sets - one per small star and stage of layers, cut in parts - with the
    report, the star file and the skill vocabulary the platform reads.

    A set says which knowledge points come before it (`requiresPoints`): the
    star map tells a student which ones are not mastered yet instead of locking
    the set. A set of an extension question type does not count for lighting
    its star (`extension`)."""
    points = {p["id"]: p for p in translated["points"]}
    requires = _requires(translated["prerequisites"])
    skipped = list(translated["skipped"])
    by_set: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for exercise in translated["exercises"]:
        reason = next(filter(None, (_too_long(exercise["text"][locale]) for locale in LOCALES)), None)
        if reason:
            skipped.append({"sourceId": exercise["sourceId"], "reason": reason})
            continue
        unit_id = built["points"][exercise["point"]]
        by_set[(unit_id, built["exercises"][exercise["id"]])].append(exercise)

    rows: list[dict[str, Any]] = []
    skills: dict[str, dict[str, Any]] = {}
    practice_sets: dict[str, dict[str, str]] = {}
    report_exercises: list[dict[str, Any]] = []
    for unit_id, star in built["stars"].items():
        subject = star["subject_id"]
        layer_of = point_layers(star["points"], translated["prerequisites"])
        for type_index, (slug, _titles, _scope) in enumerate(catalog.QUESTION_TYPES[subject]):
            exercises = sorted(by_set.get((unit_id, slug), []), key=_exercise_order(points))
            if not exercises:
                continue
            skill = catalog.skill_id(unit_id, slug)
            type_titles = catalog.question_type_titles(subject, slug)
            extension = catalog.is_extension(subject, slug)
            skills[skill] = {"subject": subject, "unit": unit_id, "titles": dict(type_titles),
                             "extension": extension}
            by_layer: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for exercise in exercises:
                by_layer[layer_of[exercise["point"]]].append(exercise)
            staged = stages(by_layer)
            for layer, last_layer, layered in staged:
                cut = parts(layered)
                for part_index, part in enumerate(cut, start=1):
                    lesson_id = f"{skill}--{layer}" + (f"-{part_index}" if len(cut) > 1 else "")
                    titles = {}
                    for locale in LOCALES:
                        title = type_titles[locale]
                        if len(staged) > 1:
                            span = f"{layer}" if layer == last_layer else f"{layer}–{last_layer}"
                            title = f"{title} · {STAGE[locale]} {span}"
                        if len(cut) > 1:
                            title = f"{title} · {PART[locale]} {part_index}"
                        titles[locale] = title
                    practice_sets[lesson_id] = titles
                    grade = min(points[e["point"]]["grade"] for e in part)
                    covered = {e["point"] for e in part}
                    needed = sorted(set().union(*(requires.get(pid, set()) for pid in covered)) - covered)
                    rows.append({
                        "publicLessonId": lesson_id,
                        "publish": False,
                        "lesson": {
                            "title": titles["de"],
                            "objective": star["description"],
                            "description": star["description"],
                            "subjectId": subject,
                            "topicId": star["topic_id"],
                            "unitId": unit_id,
                            "gradeLevel": catalog.grade_level(grade),
                            "difficulty": "practice",
                            "estimatedMinutes": max(5, MINUTES_PER_EXERCISE * len(part)),
                            "language": "de",
                            # Layer first, so a star is worked through from what needs
                            # nothing before it; then the question types in map order.
                            "order": layer * 100 + type_index * 10 + part_index,
                            "extension": extension,
                            "requiresPoints": needed,
                        },
                        "exercises": [
                            {**_manifest_exercise(e, order), "skills": [skill], "knowledgePoint": e["point"]}
                            for order, e in enumerate(part, start=1)
                        ],
                    })
                    report_exercises.extend(
                        {"sourceId": e["sourceId"], "exercise": e["id"], "star": unit_id,
                         "questionType": slug, "layer": layer_of[e["point"]], "practiceSet": lesson_id}
                        for e in part
                    )

    # The adapted ZAP tasks: practice of the same small star, after the star's own,
    # tagged so exam preparation can pick them out. They deepen the knowledge
    # point rather than make it, so they do not count for lighting it.
    by_zap_set: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for exercise in zap:
        reason = next(filter(None, (_too_long(exercise["text"][locale]) for locale in LOCALES)), None)
        if reason:
            skipped.append({"sourceId": exercise["sourceId"], "reason": reason})
        else:
            by_zap_set[(exercise["star"], exercise["questionType"])].append(exercise)
    for (unit_id, slug), exercises in sorted(by_zap_set.items()):
        star = built["stars"][unit_id]
        type_index = [t for t, _titles, _scope in catalog.QUESTION_TYPES["mathematics"]].index(slug)
        skill = catalog.skill_id(unit_id, slug)
        type_titles = catalog.question_type_titles("mathematics", slug)
        skills.setdefault(skill, {"subject": "mathematics", "unit": unit_id, "titles": dict(type_titles),
                                  "extension": catalog.is_extension("mathematics", slug)})
        exercises = sorted(exercises, key=lambda e: e["id"])
        cut = parts(exercises)
        for part_index, part in enumerate(cut, start=1):
            lesson_id = f"{skill}--zap" + (f"-{part_index}" if len(cut) > 1 else "")
            titles = {
                locale: f"{type_titles[locale]} · ZAP" + (f" · {PART[locale]} {part_index}" if len(cut) > 1 else "")
                for locale in LOCALES
            }
            practice_sets[lesson_id] = titles
            rows.append({
                "publicLessonId": lesson_id,
                "publish": False,
                "lesson": {
                    "title": titles["de"],
                    "objective": star["description"],
                    "description": star["description"],
                    "subjectId": "mathematics",
                    "topicId": star["topic_id"],
                    "unitId": unit_id,
                    "gradeLevel": catalog.GRADE_LEVELS[6],
                    "difficulty": "practice",
                    "estimatedMinutes": max(5, MINUTES_PER_EXERCISE * len(part)),
                    "language": "de",
                    "order": 500 + type_index * 10 + part_index,
                    "extension": True,
                    "requiresPoints": [],
                    "tags": ["zap"],
                },
                "exercises": [
                    {**_manifest_exercise(e, order), "skills": [skill], "tags": ["zap", e["original"]]}
                    for order, e in enumerate(part, start=1)
                ],
            })
            report_exercises.extend(
                {"sourceId": e["sourceId"], "exercise": e["id"], "star": unit_id, "questionType": slug,
                 "practiceSet": lesson_id, "zap": e["original"]}
                for e in part
            )

    trained = {skill["unit"] for skill in skills.values()}
    stars_file = {
        "source": {"repository": UPSTREAM, "licence": LICENCE},
        "stars": {
            unit_id: {key: star[key] for key in ("topic_id", "subject_id", "titles", "description", "order")}
            | {"prerequisites": [u for u in star["prerequisites"] if u in trained]}
            for unit_id, star in built["stars"].items() if unit_id in trained
        },
    }
    vocabulary = {
        "source": {"repository": UPSTREAM, "licence": LICENCE},
        "skills": dict(sorted(skills.items())),
        "practiceSets": dict(sorted(practice_sets.items())),
    }
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
            "stars": len(stars_file["stars"]),
            "smallStars": len(skills),
            "practiceSets": len(rows),
            "exercises": len(report_exercises),
            "skipped": len(skipped),
            "manifests": len(out),
            "starPrerequisites": sum(len(s["prerequisites"]) for s in stars_file["stars"].values()),
        },
        "points": [
            {"sourceId": points[pid]["sourceId"], "star": unit_id}
            for pid, unit_id in sorted(built["points"].items())
        ],
        "exercises": report_exercises,
        "skipped": skipped,
    }
    return out, report, stars_file, vocabulary


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
    p = commands.add_parser("structure-batches")
    p.add_argument("translated", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p = commands.add_parser("structure")
    p.add_argument("translated", type=Path)
    p.add_argument("filled_dir", type=Path)
    p.add_argument("--merges", type=Path, help="filled merge batches to apply")
    p.add_argument("--out", type=Path, required=True)
    p = commands.add_parser("merge-batches")
    p.add_argument("translated", type=Path)
    p.add_argument("structure", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p = commands.add_parser("manifest")
    p.add_argument("translated", type=Path)
    p.add_argument("structure", type=Path)
    p.add_argument("--out-dir", type=Path, required=True, help="manifest-NNN.json files and report.json")
    p.add_argument("--vocabulary", type=Path, default=catalog.SKILLS_FILE)
    p.add_argument("--stars", type=Path, default=catalog.STARS_FILE)
    p.add_argument("--zap", type=Path, nargs="*", default=[],
                   help="ZAP staging files; their filled batches lie next to them")
    p.add_argument("--figures", type=Path, help="the figure staging file; its filled batches lie next to it")
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
    elif args.command == "structure-batches":
        made = structure_batches(_read(args.translated))
        for batch in made:
            _write(args.out_dir / f"{batch['batch']}.json", batch)
        print(f"{len(made)} structuring batches in {args.out_dir}")
    elif args.command == "structure":
        filled = [_read(path) for path in sorted(args.filled_dir.glob("*.out.json"))]
        merges = [_read(path) for path in sorted(args.merges.glob("*.out.json"))] if args.merges else []
        built = structure(_read(args.translated), filled, merges)
        _write(args.out, built)
        print(f"{len(built['stars'])} stars, {len(built['problems'])} records with problems")
        return 1 if built["problems"] else 0
    elif args.command == "merge-batches":
        made = merge_batches(_read(args.translated), _read(args.structure))
        for batch in made:
            _write(args.out_dir / f"{batch['batch']}.json", batch)
        print(f"{len(made)} merge batches in {args.out_dir}")
    elif args.command == "manifest":
        translated, built = _read(args.translated), _read(args.structure)
        if translated["problems"] or built["problems"]:
            print("records still have problems; fix them and merge or structure again")
            return 1
        zap: list[dict[str, Any]] = []
        if args.figures:
            filled = [_read(path) for path in sorted(args.figures.parent.glob("*.out.json"))]
            figured, types, figure_dropped, figure_problems = figure_exercises(
                _read(args.figures), filled, translated
            )
            if figure_problems:
                print(f"{len(figure_problems)} figure exercises still have problems: {figure_problems[:3]}")
                return 1
            translated = with_figures(translated, figured, figure_dropped)
            built = {**built, "exercises": {**built["exercises"], **types}}
        if args.zap:
            staging = {"exercises": [item for path in args.zap for item in _read(path)["exercises"]]}
            folders = {path.parent for path in args.zap}
            filled = [_read(out) for folder in sorted(folders) for out in sorted(folder.glob("*.out.json"))]
            zap, zap_dropped, zap_problems = zap_exercises(staging, filled, built)
            if zap_problems:
                print(f"{len(zap_problems)} ZAP exercises still have problems: {zap_problems[:3]}")
                return 1
            translated = {**translated, "skipped": [*translated["skipped"], *zap_dropped]}
        made, report, stars_file, vocabulary = manifests(translated, built, args.source_version, zap)
        for old in args.out_dir.glob("manifest-*.json"):
            old.unlink()
        for index, manifest in enumerate(made, start=1):
            _write(args.out_dir / f"manifest-{index:03d}.json", manifest)
        _write(args.out_dir / "report.json", report)
        _write(args.stars, stars_file)
        _write(args.vocabulary, vocabulary)
        print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
