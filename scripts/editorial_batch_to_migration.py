#!/usr/bin/env python3
"""Turn an editorial question batch into a curriculum migration manifest for a dry run.

The input is one `stoa-editorial-1.0` batch file - the format of the ZAP fractions
batch in #106: sources, knowledge cards, exercises, shared materials and the
knowledge links between them. The output is two files:

- a manifest for `POST /admin/curriculum/migrations/dry-run`, one lesson per
  knowledge card, every lesson `"publish": false`;
- a report of what became of every editorial record: which lesson and exercise
  id it became, or why it was left out, with its sources and their rights status.

Nothing here reads or writes the table, and nothing it writes can publish. A dry
run, an apply and a teacher's review in the curriculum workflow come after it.
Apply with `publish: false` creates drafts only; publishing stays a person's step
in that workflow, which is where the sources' permissions are checked.

An exercise is carried over only when the current platform can show and judge it
as written: a short answer, no figure, a registered skill owned by its knowledge
card's unit, and every text within the authoring limits. Anything else is listed
in the report with the reason, never shortened or approximated. Editorial hints
are left out on purpose: a student hint is a reviewed template, not free text.

    uv run python scripts/editorial_batch_to_migration.py BATCH.json \\
        --manifest manifest.json --report report.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import re
import sys
from typing import Any

from stoa.services import answer_judging, curriculum_service


SCHEMA_VERSION = "stoa-editorial-1.0"
# The authoring limits of CurriculumLessonDraftRequest / CurriculumExerciseDraftRequest.
# A migration row does not pass through those request models, so they are applied
# here; tests/test_editorial_batch_to_migration.py holds the two in step.
MAX_TITLE = 300
MAX_OBJECTIVE = 1000
MAX_TEXT = 2000
MAX_ID = 200
#: A knowledge card with more exercises than this becomes several lessons of
#: near-equal size, easiest first. A 26-exercise lesson reads as a test.
MAX_EXERCISES_PER_LESSON = 8
#: A ZAP1 paper is nine tasks of two to four parts in sixty minutes.
MINUTES_PER_EXERCISE = 3
#: Imported lessons follow the seeded lessons of their star, which number theirs from 1.
FIRST_IMPORTED_ORDER = 101
PART_SUFFIX = " · Teil {part}"

#: Statuses an editorial record must have reached to become a draft (work guide:
#: draft → extracted → mapped → reviewed → ready_for_adapter; blocked is a stop).
CONVERTIBLE_STATUSES = frozenset({"mapped", "reviewed", "ready_for_adapter"})
#: Editorial response types the text input control answers and the judge can mark.
TEXT_RESPONSE_TYPES = frozenset({"short_answer", "short_answer_with_working"})
#: Editorial fields the platform has no place for; named in the report per exercise.
NOT_CARRIED = ("hints", "grading", "source_refs", "knowledge_links", "review", "provenance")


def _platform_id(prefix: str, editorial_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", editorial_id.lower()).strip("-")
    return f"{prefix}-{slug}"


def lesson_id_for(knowledge_id: str) -> str:
    return _platform_id("zap", knowledge_id.removeprefix("KP-"))


def exercise_id_for(exercise_id: str) -> str:
    return _platform_id("zap", exercise_id.removeprefix("EX-"))


def _records(batch: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = batch.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"batch field {key!r} is not a list of records")
    return value


def _german(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("de") or "").strip()
    return str(value or "").strip()


def _explanation(solution: object) -> str:
    if not isinstance(solution, list):
        return ""
    steps = sorted(
        (
            step
            for step in solution
            if isinstance(step, Mapping) and str(step.get("text") or "").strip()
        ),
        key=lambda step: int(step.get("step") or 0),
    )
    return "\n".join(str(step["text"]).strip() for step in steps)


def _primary_knowledge(
    exercise: Mapping[str, Any], links: Sequence[Mapping[str, Any]]
) -> list[str]:
    exercise_id = exercise["exercise_id"]
    return [
        str(link["knowledge_id"])
        for link in links
        if link.get("exercise_id") == exercise_id and link.get("relation") == "primary"
    ]


def _registered_skill(
    card: Mapping[str, Any], owners: Mapping[str, str]
) -> tuple[str | None, str | None]:
    refs = card.get("platform_refs") or {}
    unit_id = str(refs.get("unit_id") or "")
    for candidate in (refs.get("skill_id"), refs.get("proposed_skill_id")):
        if not candidate:
            continue
        owner = owners.get(str(candidate))
        if owner is None:
            continue
        if owner != unit_id:
            return None, f"skill {candidate} belongs to {owner}, not to the card's unit {unit_id}"
        return str(candidate), None
    return None, "the card's skill is not registered in the vocabulary"


def _exercise_problem(
    exercise: Mapping[str, Any], shared: Mapping[str, Mapping[str, Any]]
) -> str | None:
    if exercise.get("record_type") != "question":
        return "not an answerable question"
    status = exercise.get("status")
    if status not in CONVERTIBLE_STATUSES:
        reason = exercise.get("blocked_reason") or exercise.get("missing_fields")
        return f"status {status}" + (f": {reason}" if reason else "")
    if exercise.get("response_type") not in TEXT_RESPONSE_TYPES:
        return f"response type {exercise.get('response_type')} has no matching control and judge"
    if exercise.get("options"):
        return "choice options are not carried by the authoring conversion"
    if exercise.get("assets"):
        return "figures and other assets are not shown with exercises"
    material_id = exercise.get("shared_material_id")
    if material_id:
        material = shared.get(str(material_id))
        if material is None:
            return f"shared material {material_id} is missing from the batch"
        if str(material.get("prompt") or "").strip() not in str(exercise.get("prompt") or ""):
            return f"the prompt does not contain shared material {material_id}"
    answer = exercise.get("answer") or {}
    if not str(answer.get("canonical") or "").strip():
        return "no canonical answer"
    return None


def _length_problem(fields: Mapping[str, str], limits: Mapping[str, int]) -> str | None:
    for name, limit in limits.items():
        if len(fields[name]) > limit:
            return f"{name} is {len(fields[name])} characters, the limit is {limit}"
    return None


def _split(lesson: dict[str, Any], max_exercises: int) -> list[dict[str, Any]]:
    """One card's lesson as parts of at most `max_exercises`, easiest first.

    Easiest is read off the work shown: fewer solution steps, then a shorter prompt.
    It is a proxy, not a judgement, and the review can reorder."""
    exercises = sorted(
        lesson["exercises"], key=lambda item: (item.pop("_steps"), len(item["prompt"]))
    )
    count = -(-len(exercises) // max_exercises)
    size, extra = divmod(len(exercises), count)
    parts, start = [], 0
    for index in range(count):
        end = start + size + (1 if index < extra else 0)
        chunk = exercises[start:end]
        start = end
        part = {**lesson, "lesson": dict(lesson["lesson"]), "exercises": chunk}
        if count > 1:
            part["publicLessonId"] = f"{lesson['publicLessonId']}-{index + 1}"
            part["lesson"]["title"] += PART_SUFFIX.format(part=index + 1)
        part["lesson"]["estimatedMinutes"] = max(5, MINUTES_PER_EXERCISE * len(chunk))
        for order, exercise in enumerate(chunk, start=1):
            exercise["order"] = order
        parts.append(part)
    return parts


def convert(
    batch: Mapping[str, Any], *, max_exercises: int = MAX_EXERCISES_PER_LESSON
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The dry-run manifest and the report for one editorial batch."""
    if max_exercises < 1:
        raise ValueError("a lesson holds at least one exercise")
    if batch.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"expected schema {SCHEMA_VERSION}, got {batch.get('schema_version')!r}")
    batch_id = str(batch.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("the batch has no batch_id")

    cards = {str(card["knowledge_id"]): card for card in _records(batch, "knowledge")}
    sources = {str(source["source_id"]): source for source in _records(batch, "sources")}
    shared = {str(item["exercise_id"]): item for item in _records(batch, "shared_materials")}
    links = _records(batch, "mappings")
    owners = curriculum_service.skill_unit_ids()

    lessons: dict[str, dict[str, Any]] = {}
    report_rows: list[dict[str, Any]] = []
    for exercise in _records(batch, "exercises"):
        editorial_id = str(exercise["exercise_id"])
        row: dict[str, Any] = {
            "editorialExerciseId": editorial_id,
            "revision": exercise.get("revision"),
            "sources": [
                {
                    "sourceId": ref.get("source_id"),
                    "role": ref.get("role"),
                    "pdfPage": ref.get("pdf_page"),
                    "questionLabel": ref.get("question_label"),
                    "rightsStatus": (sources.get(str(ref.get("source_id"))) or {}).get(
                        "rights_status"
                    ),
                }
                for ref in exercise.get("source_refs") or []
                if isinstance(ref, Mapping)
            ],
        }
        report_rows.append(row)

        problem = _exercise_problem(exercise, shared)
        primary = _primary_knowledge(exercise, links)
        if problem is None and len(primary) != 1:
            problem = f"{len(primary)} primary knowledge links, exactly one is needed"
        card = cards.get(primary[0]) if problem is None else None
        if problem is None and card is None:
            problem = f"knowledge card {primary[0]} is missing from the batch"
        skill = None
        if problem is None and card is not None:
            skill, problem = _registered_skill(card, owners)
        if problem is not None or card is None or skill is None:
            row["status"] = "skipped"
            row["reason"] = problem
            continue

        answer = exercise["answer"]
        canonical = str(answer["canonical"]).strip()
        accepted = [
            text
            for text in dict.fromkeys(
                str(item).strip() for item in answer.get("accepted_answers") or []
            )
            if text and text != canonical
        ][: answer_judging.MAX_ACCEPTED_ANSWERS]
        fields = {
            "prompt": str(exercise.get("prompt") or "").strip(),
            "answerKey": canonical,
            "explanation": _explanation(exercise.get("solution")),
            "exerciseId": exercise_id_for(editorial_id),
        }
        problem = _length_problem(
            fields,
            {
                "prompt": MAX_TEXT,
                "answerKey": MAX_TEXT,
                "explanation": MAX_TEXT,
                "exerciseId": MAX_ID,
            },
        ) or next(
            (
                f"an accepted answer is longer than {answer_judging.MAX_ACCEPTED_ANSWER_LENGTH}"
                for text in accepted
                if len(text) > answer_judging.MAX_ACCEPTED_ANSWER_LENGTH
            ),
            None,
        )
        if problem is None and not fields["explanation"]:
            problem = "no solution steps to explain the answer"
        if problem is not None:
            row["status"] = "skipped"
            row["reason"] = problem
            continue

        knowledge_id = str(card["knowledge_id"])
        lesson = lessons.get(knowledge_id)
        if lesson is None:
            refs = card.get("platform_refs") or {}
            scope = card.get("scope") or {}
            lesson = {
                "publicLessonId": lesson_id_for(knowledge_id),
                "publish": False,
                "lesson": {
                    "title": _german(card.get("title")),
                    "objective": str(card.get("learning_objective") or "").strip(),
                    "subjectId": refs.get("subject_id"),
                    "topicId": refs.get("topic_id"),
                    "unitId": refs.get("unit_id"),
                    "gradeLevel": scope.get("grade_level"),
                    "language": card.get("content_language") or "de",
                    "difficulty": "practice",
                },
                "exercises": [],
            }
            problem = _length_problem(
                {"title": lesson["lesson"]["title"], "objective": lesson["lesson"]["objective"]},
                {"title": MAX_TITLE - len(PART_SUFFIX.format(part=99)), "objective": MAX_OBJECTIVE},
            )
            if problem is not None:
                row["status"] = "skipped"
                row["reason"] = f"knowledge card {knowledge_id}: {problem}"
                continue
            lessons[knowledge_id] = lesson

        exercise_payload: dict[str, Any] = {
            "exerciseId": fields["exerciseId"],
            "type": "text_input",
            "prompt": fields["prompt"],
            "answerKey": canonical,
            "explanation": fields["explanation"],
            "difficulty": "practice",
            "order": len(lesson["exercises"]) + 1,
            "skills": [skill],
            "_steps": len(fields["explanation"].splitlines()),
        }
        if accepted:
            exercise_payload["acceptedAnswers"] = accepted
        lesson["exercises"].append(exercise_payload)
        row.update(
            status="converted",
            exerciseId=fields["exerciseId"],
            knowledgeId=knowledge_id,
            skill=skill,
            notCarried=[name for name in NOT_CARRIED if exercise.get(name)],
        )

    final: list[dict[str, Any]] = []
    next_order: dict[str, int] = {}
    for lesson in lessons.values():
        for part in _split(lesson, max_exercises):
            unit_id = str(part["lesson"]["unitId"])
            part["lesson"]["order"] = next_order.setdefault(unit_id, FIRST_IMPORTED_ORDER)
            next_order[unit_id] += 1
            final.append(part)
    lesson_of = {
        e["exerciseId"]: part["publicLessonId"] for part in final for e in part["exercises"]
    }
    for row in report_rows:
        if row.get("status") == "converted":
            row["publicLessonId"] = lesson_of[row["exerciseId"]]

    rights = sorted(
        {
            str(source.get("rights_status"))
            for row in report_rows
            if row.get("status") == "converted"
            for ref in row["sources"]
            if (source := sources.get(str(ref["sourceId"]))) is not None
        }
    )
    manifest = {
        "source": {
            "sourceId": batch_id,
            "sourceVersion": f"revision-{batch.get('revision')}",
            "sourceType": "editorial_batch",
        },
        "operatorNote": (
            f"Drafts from editorial batch {batch_id}; not for publication before teacher review "
            f"and permission for every source (rights statuses: {', '.join(rights) or 'none'})."
        ),
        "lessons": final,
    }
    report = {
        "batchId": batch_id,
        "revision": batch.get("revision"),
        "counts": {
            "exercises": len(report_rows),
            "converted": sum(1 for row in report_rows if row["status"] == "converted"),
            "skipped": sum(1 for row in report_rows if row["status"] == "skipped"),
            "lessons": len(final),
        },
        "sourceRightsStatuses": rights,
        "exercises": report_rows,
    }
    return manifest, report


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batch", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-exercises", type=int, default=MAX_EXERCISES_PER_LESSON)
    args = parser.parse_args(argv)
    try:
        batch = json.loads(args.batch.read_text(encoding="utf-8"))
        manifest, report = convert(batch, max_exercises=args.max_exercises)
    except (OSError, ValueError, KeyError) as error:
        print(f"cannot convert {args.batch}: {error}", file=sys.stderr)
        return 1
    _write(args.manifest, manifest)
    _write(args.report, report)
    counts = report["counts"]
    print(
        f"{counts['converted']} of {counts['exercises']} exercises into {counts['lessons']} lessons; "
        f"{counts['skipped']} skipped (see {args.report})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
