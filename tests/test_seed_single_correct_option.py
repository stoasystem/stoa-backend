"""Every multiple-choice question in the practice seed has exactly one right option.

stoa-backend#388: `brueche-l1-c3` asked for a fraction between 1/2 and 1 and
offered both 3/4 and 2/3; only 3/4 was marked correct, so a student who picked
2/3 was told they were wrong. A question whose prompt names a numeric interval
("zwischen a und b") can be checked by value: exactly one option may lie in it,
and it must be the marked answer.
"""

from __future__ import annotations

import re
from fractions import Fraction

import pytest

from scripts import seed_practice

NUMBER = r"-?\d+(?:/\d+)?"
BETWEEN = re.compile(rf"zwischen\s+({NUMBER})\s+und\s+({NUMBER})", re.IGNORECASE)


def _challenges() -> list[dict]:
    return [
        row for row in seed_practice.seed_rows()
        if row["SK"].startswith("CHALLENGE#") and row.get("type") == "multiple_choice"
    ]


def _value(text: str) -> Fraction | None:
    return Fraction(text.strip()) if re.fullmatch(NUMBER, text.strip()) else None


def _interval_questions() -> list[dict]:
    return [c for c in _challenges() if BETWEEN.search(c["prompt"])]


def test_the_seed_has_interval_questions_to_check():
    ids = {c["challenge_id"] for c in _interval_questions()}
    assert "brueche-l1-c3" in ids


@pytest.mark.parametrize(
    "challenge", _interval_questions(), ids=lambda c: c["challenge_id"],
)
def test_exactly_one_option_lies_in_the_named_interval(challenge):
    low, high = sorted(Fraction(x) for x in BETWEEN.search(challenge["prompt"]).groups())
    inside = [
        option for option in challenge["options"]
        if (value := _value(option)) is not None and low < value < high
    ]
    assert inside == [challenge["correct_answer"]], (
        f"{challenge['challenge_id']}: options in ({low}, {high}) are {inside}, "
        f"marked answer is {challenge['correct_answer']!r}"
    )


def test_every_multiple_choice_answer_is_one_distinct_option():
    for challenge in _challenges():
        options = challenge["options"]
        assert len(set(options)) == len(options), challenge["challenge_id"]
        assert options.count(challenge["correct_answer"]) == 1, challenge["challenge_id"]
