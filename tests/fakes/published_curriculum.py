"""A published curriculum of a chosen size, and a table that says who read it (#496).

`curriculum_rows(scale)` is what `scripts/seed_practice.py --knowledge-base-live`
writes - the subjects, nebulae and stars, the ZAP lessons and exercises - plus
the knowledge-base lessons and exercises the curriculum migrations published,
in the shape the seed gives its own: on 2026-11-17 production held 813
mathematics lessons with 3,582 exercises, 470 English with 2,864 and 254
physics with 1,070 (#422, #483, #484). `scale=1.0` is that size; a smaller
scale keeps the same shape with fewer rows, so a test can compare two sizes.

`ReadCountingTable` is the shared table double that also records, for every
`query`, `scan` and `get_item`, the code that asked and how many rows came
back. A read is attributed to the innermost `stoa` function on the stack and
the first function above it outside the repositories, which is what tells
"the curriculum catalog" apart from "the memory summary that read it".
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

from fakes.dynamodb import ConditionEvaluator, FakeTable, _object_condition_holds
from scripts import seed_practice
from stoa.db.repositories import practice_repo

#: Published knowledge-base lessons and exercises per subject on 2026-11-17.
PRODUCTION_SIZE = {
    "mathematics": (813, 3582),
    "english": (470, 2864),
    "physics": (254, 1070),
}


def _template() -> tuple[dict[str, Any], dict[str, Any]]:
    _topic, _units, lessons, challenges = seed_practice._brueche_data()
    return dict(lessons[0]), dict(challenges[0])


def curriculum_rows(scale: float = 1.0) -> list[dict[str, Any]]:
    """Every published curriculum row at `scale` times the production size."""
    rows = seed_practice.seed_rows(knowledge_base=seed_practice.KNOWLEDGE_BASE_LIVE)
    units_by_subject: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["PK"] == "PRACTICE" and str(row["SK"]).startswith("UNIT#"):
            units_by_subject.setdefault(str(row["subject_id"]), []).append(row)
    lesson_template, challenge_template = _template()
    lessons: list[dict[str, Any]] = []
    challenges: list[dict[str, Any]] = []
    for subject_id, (lesson_count, challenge_count) in PRODUCTION_SIZE.items():
        units = units_by_subject[subject_id]
        n_lessons = max(1, math.ceil(lesson_count * scale))
        n_challenges = max(1, math.ceil(challenge_count * scale))
        subject_lessons = []
        for index in range(n_lessons):
            unit = units[index % len(units)]
            lesson = {
                **lesson_template,
                "lesson_id": f"kb-{subject_id}-l{index}",
                "unit_id": unit["unit_id"],
                "topic_id": unit["topic_id"],
                "subject_id": subject_id,
                "grade_level": unit["grade_level"],
                "title": f"{unit['title']} {index}",
                "order": index,
                "rollout_state": "active",
            }
            subject_lessons.append(lesson)
        for index in range(n_challenges):
            lesson = subject_lessons[index % n_lessons]
            challenges.append(
                {
                    **challenge_template,
                    "challenge_id": f"{lesson['lesson_id']}-c{index}",
                    "lesson_id": lesson["lesson_id"],
                    "unit_id": lesson["unit_id"],
                    "topic_id": lesson["topic_id"],
                    "subject_id": subject_id,
                    "grade_level": lesson["grade_level"],
                    "order": index,
                    "skills": [],
                    "rollout_state": "active",
                }
            )
        lessons.extend(subject_lessons)
    by_lesson: dict[str, list[dict[str, Any]]] = {}
    for challenge in challenges:
        by_lesson.setdefault(challenge["lesson_id"], []).append(challenge)
    for lesson in lessons:
        own = by_lesson.get(lesson["lesson_id"], [])
        rows.append(
            {
                "PK": "PRACTICE",
                "SK": f"LESSON#{lesson['lesson_id']}",
                **lesson,
                "challenge_count": len(own),
                "exercise_index": practice_repo.exercise_index(own),
            }
        )
    rows.extend(seed_practice.prepare_challenge_items(challenges))
    return rows


# ── Who read what ───────────────────────────────────────────────────────────

_REPOSITORY_PARTS = ("stoa/db/", "stoa\\db\\")


def _caller() -> tuple[str, str]:
    """(innermost stoa function, first stoa function above the repositories)."""
    frame = sys._getframe(2)
    innermost = ""
    service = ""
    while frame is not None:
        filename = frame.f_code.co_filename
        if "stoa" in filename and ("src/stoa" in filename.replace("\\", "/")):
            module = filename.replace("\\", "/").split("src/stoa/", 1)[1].removesuffix(".py")
            name = f"{module}:{frame.f_code.co_name}"
            if not innermost:
                innermost = name
            if not service and not any(part in filename for part in _REPOSITORY_PARTS):
                service = name
                break
        frame = frame.f_back
    return innermost or "?", service or innermost or "?"


class ReadCountingTable(FakeTable):
    """The shared double, recording rows returned per reading call site.

    It also skips copying rows a key condition does not select, which keeps a
    production-sized table quick to query; what it returns is unchanged.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Calls, rows handed back (DynamoDB's ReturnedItemCount) and rows the
        # table had to read for them (ScannedCount: what a filter throws away
        # still costs the time), per call site.
        self.reads: Counter[tuple[str, str, str]] = Counter()
        self.items_read: Counter[tuple[str, str, str]] = Counter()
        self.rows_scanned: Counter[tuple[str, str, str]] = Counter()

    def reset_reads(self) -> None:
        self.reads.clear()
        self.items_read.clear()
        self.rows_scanned.clear()

    @property
    def total_items_read(self) -> int:
        return sum(self.items_read.values())

    @property
    def total_rows_scanned(self) -> int:
        return sum(self.rows_scanned.values())

    def _count(self, operation: str, returned: int, scanned: int) -> None:
        innermost, service = _caller()
        key = (operation, innermost, service)
        self.reads[key] += 1
        self.items_read[key] += returned
        self.rows_scanned[key] += scanned

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        response = super().get_item(**kwargs)
        found = 1 if "Item" in response else 0
        self._count("get_item", found, found)
        return response

    def query(self, **kwargs: Any) -> dict[str, Any]:
        response = super().query(**kwargs)
        self._count("query", int(response["Count"]), int(response["ScannedCount"]))
        return response

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        response = super().scan(**kwargs)
        self._count("scan", int(response["Count"]), int(response["ScannedCount"]))
        return response

    def _selected(self, rows: Iterator[dict[str, Any]], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        condition = kwargs.get("KeyConditionExpression")
        if condition is None:
            raise AssertionError("query requires a KeyConditionExpression")
        if isinstance(condition, str):
            evaluator = ConditionEvaluator(
                kwargs.get("ExpressionAttributeNames"), kwargs.get("ExpressionAttributeValues")
            )
            return [deepcopy(row) for row in rows if evaluator.holds(condition, row)]
        return [deepcopy(row) for row in rows if _object_condition_holds(condition, row)]

    def _base_candidates(
        self, kwargs: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        return self._selected((row for _, row in sorted(self.rows.items())), kwargs), ()

    def _index_candidates(
        self, index_name: str, kwargs: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        schema = self.indexes.get(index_name)
        if schema is None:
            raise AssertionError(f"unknown index: {index_name}")
        projected = sorted(
            (
                row
                for row in self.rows.values()
                if schema.partition_key in row
                and (schema.sort_key is None or schema.sort_key in row)
            ),
            key=lambda row: (
                str(row.get(schema.partition_key)),
                str(row.get(schema.sort_key)) if schema.sort_key else "",
                (str(row["PK"]), str(row["SK"])),
            ),
        )
        matched = self._selected(iter(projected), kwargs)
        return matched, (schema.partition_key, *((schema.sort_key,) if schema.sort_key else ()))

    def report(self) -> str:
        """The reads as a Markdown table, most rows first."""
        lines = [
            "| Operation | Called from (innermost) | Service caller | Calls | Items returned | Rows read |",
            "|---|---|---|---:|---:|---:|",
        ]
        ordered = sorted(
            self.reads, key=lambda key: (-self.rows_scanned[key], -self.items_read[key], key)
        )
        for key in ordered:
            operation, innermost, service = key
            lines.append(
                f"| {operation} | `{innermost}` | `{service}` | {self.reads[key]}"
                f" | {self.items_read[key]} | {self.rows_scanned[key]} |"
            )
        lines.append(
            f"| **total** | | | **{sum(self.reads.values())}** | **{self.total_items_read}**"
            f" | **{self.total_rows_scanned}** |"
        )
        return "\n".join(lines)
