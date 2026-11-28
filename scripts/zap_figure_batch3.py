#!/usr/bin/env python3
"""Build the migration manifest of ZAP figure tasks, batch 3 (#596).

Seventeen ZAP1 originals of "Form und Raum" that were skipped because the
answer is drawn or ticked in the figure become eighteen `multi_select`
exercises whose options are hotspots in the figure (#593): eleven "which marked
points lie in the region" tasks (`zap_figure_batch3_locus`) and seven picked in
a solid, a net or a set of shapes (`zap_figure_batch3_figures`). The originals
were not at hand, only a one-line summary of each: the adaptation takes the
kind of task and nothing else, and every figure, number and situation is new
(the adaptation rule of 2026-11-12 in #106).

No key is written down. Each is computed here from the same description the
figure is drawn from, with exact arithmetic, and each text is filled in from
the computed key. `tests/test_zap_figure_batch3.py` works every key out again
from the finished manifest by another way.

    python scripts/zap_figure_batch3.py            # write the manifest
    python scripts/zap_figure_batch3.py --check    # fail if the file is not what this builds
    python scripts/zap_figure_batch3.py --report   # how each key was decided

The manifest is for `dry_run_curriculum_migration`; every lesson is
`"publish": false`. Nothing here reads or writes a table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import zap_figure_batch3_figures as figures  # noqa: E402
from scripts import zap_figure_batch3_locus as locus  # noqa: E402
from scripts.zap_figure_batch3_texts import LOCALES, TEXTS, finish, listing  # noqa: E402

MANIFEST = ROOT / "tests" / "fixtures" / "zap_figure_batch3_596.json"
SKILLS = ROOT / "src" / "stoa" / "services" / "knowledge_base_skills.json"
STARS = ROOT / "src" / "stoa" / "services" / "knowledge_base_stars.json"
#: A ZAP1 paper is nine tasks of two to four parts in sixty minutes.
MINUTES_PER_EXERCISE = 3
#: The question types of mathematics in map order: a ZAP practice set's place
#: among its star's lessons is 500 + 10 * (its type's place) + its part.
QUESTION_TYPES = ("kopfrechnen", "rechnen", "begriffe", "darstellen", "vergleichen", "sachaufgaben", "schliessen")

#: practice set -> (star, question type, part in the lesson order, task keys easiest first)
LESSONS: dict[str, tuple[str, str, int, tuple[str, ...]]] = {
    "geometrie-strecken-geraden-senkrechte-und-parallelen--darstellen--zap-1": (
        "geometrie-strecken-geraden-senkrechte-und-parallelen", "darstellen", 1,
        ("rastplaetze", "zwei-geraden", "kreis-und-geraden", "koordinaten", "zeltplatz", "tram"),
    ),
    "geometrie-strecken-geraden-senkrechte-und-parallelen--darstellen--zap-2": (
        "geometrie-strecken-geraden-senkrechte-und-parallelen", "darstellen", 2,
        ("kreislinie", "schatz", "angeln", "kabel", "pony"),
    ),
    "geometrie-koerper-ansichten-und-netze--darstellen--zap-4": (
        "geometrie-koerper-ansichten-und-netze", "darstellen", 4,
        ("wuerfel", "netz-kanten", "netz-ecken", "keil-kanten", "keil-ecken"),
    ),
    "geometrie-ebene-figuren-und-vielecke--schliessen--zap": (
        "geometrie-ebene-figuren-und-vielecke", "schliessen", 1,
        ("winkelstuecke", "t-stueck"),
    ),
}


def _math(name: str) -> str:
    return f"${name}$"


def _task(key: str, original: str, figure: str, options: list[str], correct: list[int],
          fills: dict[str, list[str]], facts: dict[str, object]) -> dict[str, Any]:
    """One task ready for the manifest: its key and its four texts filled in."""
    if len(correct) < 2:
        raise ValueError(f"{key}: a choose-several task with a single right option")
    if len(correct) == len(options):
        raise ValueError(f"{key}: every option is right")
    texts = {}
    for locale in LOCALES:
        prompt, explanation = TEXTS[key][locale]
        filled = {name: listing(items, locale) for name, items in fills.items()}
        texts[locale] = {
            "prompt": finish(prompt, locale),
            "explanation": finish(explanation.format(**filled, **facts), locale),
        }
    return {"key": key, "original": original, "figure": figure, "options": options,
            "correct": correct, "texts": texts}


def locus_task(task: locus.LocusTask) -> dict[str, Any]:
    solved = locus.solve(task)
    if locus.hotspot_gap(task) < locus.MIN_HOTSPOT_GAP:
        raise ValueError(f"{task.key}: two candidates are too close to tap apart")
    names = [_math(item.name) for item in solved]
    fills = {
        "ok": [name for name, item in zip(names, solved, strict=True) if item.inside],
        "no": [name for name, item in zip(names, solved, strict=True) if not item.inside],
    }
    for index, condition in enumerate(task.conditions, start=1):
        meeting = [name for name, item in zip(names, solved, strict=True) if item.holds[index - 1]]
        if len(meeting) == len(solved):
            raise ValueError(f"{task.key}: '{condition.name}' rules out no candidate")
        fills[f"c{index}"] = meeting
    return _task(task.key, task.original, task.figure, names,
                 [index for index, item in enumerate(solved) if item.inside], fills, {})


def figure_task(task: figures.FigureTask) -> dict[str, Any]:
    if task.hotspot_gap() < figures.MIN_HOTSPOT_GAP:
        raise ValueError(f"{task.key}: two hotspots are too close to tap apart")
    lettered = task.options[0].isalpha()
    names = [_math(option) if lettered else option for option in task.options]
    fills = {
        "ok": [names[index] for index in task.correct],
        "no": [name for index, name in enumerate(names) if index not in task.correct],
    }
    facts = {name: value for name, value in task.facts.items() if name in ("k", "m")}
    if "painted" in task.facts:
        painted = task.facts["painted"]
        assert isinstance(painted, list)
        fills["three"] = [name for name, count in zip(names, painted, strict=True) if count == 3]
        fills["five"] = [name for name, count in zip(names, painted, strict=True) if count == 5]
        if sorted({3, 4, 5}) != sorted(set(painted)):
            raise ValueError("the cube text speaks of three, four and five painted faces only")
    return _task(task.key, task.original, task.figure, names, list(task.correct), fills, facts)


def all_tasks() -> dict[str, dict[str, Any]]:
    tasks = [locus_task(task) for task in locus.tasks()]
    tasks += [figure_task(task) for task in figures.tasks()]
    return {task["key"]: task for task in tasks}


def _exercise(task: dict[str, Any], exercise_id: str, order: int, skill: str) -> dict[str, Any]:
    year, _, number = task["original"].partition("-")
    return {
        "exerciseId": exercise_id,
        "type": "multi_select",
        "difficulty": "zap",
        "order": order,
        "prompt": task["texts"]["de"]["prompt"],
        "figure": task["figure"],
        "options": task["options"],
        "correctOptions": task["correct"],
        "explanation": task["texts"]["de"]["explanation"],
        "skills": [skill],
        "tags": ["zap", f"ZAP1 {year} · {number}"],
        "translations": {
            locale: {
                "prompt": task["texts"][locale]["prompt"],
                "options": task["options"],
                "explanation": task["texts"][locale]["explanation"],
            }
            for locale in LOCALES if locale != "de"
        },
    }


def build() -> dict[str, Any]:
    tasks = all_tasks()
    skills = json.loads(SKILLS.read_text(encoding="utf-8"))
    stars = json.loads(STARS.read_text(encoding="utf-8"))["stars"]
    used: dict[str, int] = {}
    lessons = []
    for lesson_id, (unit_id, question_type, part, keys) in LESSONS.items():
        skill = f"{unit_id}--{question_type}"
        if skills["skills"][skill]["unit"] != unit_id:
            raise ValueError(f"{skill} is not a skill of {unit_id}")
        titles = skills["practiceSets"][lesson_id]
        star = stars[unit_id]
        exercises = []
        for order, key in enumerate(keys, start=1):
            original = tasks[key]["original"]
            used[original] = used.get(original, 0) + 1
            exercise_id = f"kb-zap-stoa-zap1-{original}-v{used[original]}"
            exercises.append(_exercise(tasks[key], exercise_id, order, skill))
        lessons.append({
            "publicLessonId": lesson_id,
            "publish": False,
            "lesson": {
                "title": titles["de"],
                "titles": dict(titles),
                "objective": star["description"],
                "description": star["description"],
                "subjectId": star["subject_id"],
                "topicId": star["topic_id"],
                "unitId": unit_id,
                "gradeLevel": "grade_6_primary",
                "difficulty": "practice",
                "estimatedMinutes": max(5, MINUTES_PER_EXERCISE * len(exercises)),
                "language": "de",
                "order": 500 + QUESTION_TYPES.index(question_type) * 10 + part,
                "extension": True,
                "requiresPoints": [],
                "tags": ["zap"],
            },
            "exercises": exercises,
        })
    placed = [key for _unit, _type, _part, keys in LESSONS.values() for key in keys]
    if sorted(placed) != sorted(tasks):
        raise ValueError("every task belongs to exactly one practice set")
    return {
        "source": {
            "sourceId": "zap1-figure-tasks-batch-3",
            "sourceVersion": "2026-11-28",
            "sourceType": "manifest",
        },
        "operatorNote": (
            "ZAP1 figure tasks, batch 3 (#596): 17 originals of Form und Raum adapted as 18 "
            "choose-several exercises with hotspots in the figure; new figures and numbers, keys "
            "computed by scripts/zap_figure_batch3.py. Drafts for review: every lesson is publish false."
        ),
        "lessons": lessons,
    }


def rendered() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def report() -> str:
    """How each key was decided, for a reader checking the batch."""
    lines = [
        f"Locus tasks: every inequality of every condition holds or fails by at least "
        f"{locus.MIN_MARGIN} grid square at every candidate (exact arithmetic).",
        "",
    ]
    for task in locus.tasks():
        solved = locus.solve(task)
        lines.append(
            f"{task.original:8} {task.key}: right {', '.join(s.name for s in solved if s.inside)} "
            f"of {len(solved)}; smallest margin {float(min(s.margin for s in solved)):.3f} squares; "
            f"hotspots at least {float(locus.hotspot_gap(task)):.0f} apart"
        )
        for index, condition in enumerate(task.conditions):
            lines.append(
                f"           {condition.name}: "
                f"{', '.join(s.name for s in solved if s.holds[index]) or '-'}"
            )
        for item in solved:
            marks = "".join("+" if hold else "-" for hold in item.holds)
            lines.append(
                f"           {item.name} ({item.at[0]}/{item.at[1]}) {marks} "
                f"margin {float(item.margin):.3f}"
            )
    lines.append("")
    for task in figures.tasks():
        lines.append(
            f"{task.original:8} {task.key}: right {', '.join(task.options[i] for i in task.correct)} "
            f"of {len(task.options)}; hotspots at least {task.hotspot_gap():.0f} apart; {task.facts}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the manifest file is out of date")
    parser.add_argument("--report", action="store_true", help="print how each key was decided")
    args = parser.parse_args(argv)
    if args.report:
        sys.stdout.write(report())
        return 0
    text = rendered()
    if args.check:
        if not MANIFEST.exists() or MANIFEST.read_text(encoding="utf-8") != text:
            print(f"{MANIFEST.relative_to(ROOT)} is not what scripts/zap_figure_batch3.py builds")
            return 1
        return 0
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}: {sum(len(lesson["exercises"]) for lesson in build()["lessons"])} exercises")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
