#!/usr/bin/env python3
"""Find a letter that names a point, event, set or body left outside the formula beside its neighbours.

The practice page renders `$...$` with KaTeX, so `$B$` is an italic B. When the conversion to KaTeX (#567)
left a name such as the A in "A and $B$ are independent" as plain text - it took it for the English
article - the student sees an upright A next to italic B, C, D (stoa-backend#603). This check reads a
curriculum migration manifest, or a state file of the same shape (`{"lessons": [{"exercises": [...]}]}`),
and lists every such letter in a display text: the prompt, the explanation, the two feedbacks and the
options, in German and in every translation.

It finds two shapes:

- **beside a name**: a lone capital letter outside the formulas, directly before ", $X", " and $X",
  " e $X", " et $X", " und $X", " or $X", " ou $X", " o $X", or directly after one of those joined to a
  formula that is a single letter ("$B$ and A");
- **a broken function**: "$P$(A)$=...$", where a letter in parentheses sits between two formulas.

A unit after a number ("600$ C, ...", "22 J et ...") is not a name and is not reported. The question text
stays out of this repository (docs/knowledge-base-import.md, Licence), so the check runs on a manifest
on disk:

    uv run python scripts/check_letter_names.py manifest.json [more.json ...] [--allow allow.txt]

`--allow` names exercises whose letters stay as they are on purpose, one per line, the exercise id first
and the reason after it (`kb-zap-stoa-zap1-2019-9d-v1  pieces A and B are figure labels`). Exit code 1
when anything not allowed is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOLLAR = re.compile(r"(?<!\\)\$")
JOIN = r"(?:,| and| e| et| und| or| ou| o)"
#: A lone capital letter before a joiner and a formula that starts with a letter.
BEFORE = re.compile(r"(?<![\w$\\'’])([A-Z])(?![\w'’])(?=" + JOIN + r" \$[A-Z])")
#: A lone capital letter after a one-letter formula and a joiner.
AFTER = re.compile(r"\$[A-Z]'?\$" + JOIN + r" ([A-Z])(?![\w'’(])")
#: "$P$(A)$=...$": a letter in parentheses between two formulas.
BROKEN_FUNCTION = re.compile(r"\$[A-Za-z]\$\(([A-Z])\)\$")
#: What may stand right before a unit: a number, a closed formula after a number ("600$ C"), an exponent.
UNIT_BEFORE = re.compile(r"(?:\d|\d\$|\}\$|°)\s?$")
TEXT_FIELDS = (
    ("prompt", "prompt"),
    ("explanation", "explanation"),
    ("correctFeedback", "correct_feedback"),
    ("incorrectFeedback", "incorrect_feedback"),
)


@dataclass(frozen=True)
class Finding:
    exercise_id: str
    locale: str
    field: str
    letter: str
    context: str

    def line(self) -> str:
        return f"{self.exercise_id} [{self.locale}] {self.field}: {self.letter} in …{self.context}…"


def _inside_math(text: str, index: int) -> bool:
    return len(DOLLAR.findall(text[:index])) % 2 == 1


def _is_unit(text: str, index: int) -> bool:
    return bool(UNIT_BEFORE.search(text[max(0, index - 8):index]))


def _context(text: str, index: int) -> str:
    return text[max(0, index - 30):index + 31].replace("\n", " ")


def letters_in(text: str) -> list[tuple[int, str]]:
    """Positions and letters of every name left outside its formula in one text."""
    found: dict[int, str] = {}
    for pattern in (BEFORE, AFTER):
        for match in pattern.finditer(text):
            index = match.start(1)
            if not _inside_math(text, index) and not _is_unit(text, index):
                found[index] = match.group(1)
    for match in BROKEN_FUNCTION.finditer(text):
        if not _inside_math(text, match.start()):
            found[match.start(1)] = match.group(1)
    return sorted(found.items())


def _texts(exercise: Mapping[str, Any]) -> Iterator[tuple[str, str, str]]:
    sides: dict[str, Mapping[str, Any]] = {"de": exercise}
    sides.update(exercise.get("translations") or {})
    for locale, side in sides.items():
        for camel, snake in TEXT_FIELDS:
            value = side.get(camel, side.get(snake))
            if isinstance(value, str):
                yield locale, camel, value
        for index, option in enumerate(side.get("options") or []):
            if isinstance(option, str):
                yield locale, f"options[{index}]", option


def findings(document: Mapping[str, Any]) -> list[Finding]:
    """Every letter name left outside the formulas in the exercises of a manifest or state file."""
    result = []
    for lesson in document.get("lessons") or []:
        for exercise in lesson.get("exercises") or []:
            exercise_id = str(exercise.get("exerciseId") or exercise.get("exercise_id") or "?")
            for locale, field, text in _texts(exercise):
                for index, letter in letters_in(text):
                    result.append(Finding(exercise_id, locale, field, letter, _context(text, index)))
    return result


def read_allowed(path: Path) -> dict[str, str]:
    allowed = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        exercise_id, _, reason = line.partition(" ")
        if not reason.strip():
            raise SystemExit(f"{path}: {exercise_id} is allowed without a reason")
        allowed[exercise_id] = reason.strip()
    return allowed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="manifest or state JSON files")
    parser.add_argument("--allow", type=Path, help="exercise ids left as they are, each with its reason")
    args = parser.parse_args(argv)
    allowed = read_allowed(args.allow) if args.allow else {}
    reported, kept = [], []
    for path in args.files:
        for finding in findings(json.loads(path.read_text(encoding="utf-8"))):
            (kept if finding.exercise_id in allowed else reported).append(finding)
    for finding in reported:
        print(finding.line())
    for exercise_id in sorted({finding.exercise_id for finding in kept}):
        print(f"allowed: {exercise_id} ({allowed[exercise_id]})")
    print(f"{len(reported)} letter names outside their formula, {len(kept)} allowed")
    return 1 if reported else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
