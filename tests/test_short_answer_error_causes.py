"""错因 step 2: a wrong typed answer's cause, inferred by fixed rules (#453).

A typed answer has no distractor to tag, so a wrong one is compared with the
key by rules, never by a model: the same number with the other sign, or a
number very close to the key, is a deviation (knows it, got it wrong). Each
rule records one fixed misconception sentence in every locale; whatever no
rule explains stays unclassified, as in step 1. The cause lands on the receipt
the same way a distractor's does, so the evidence tally and the teacher's
preparation summary read it unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import student_evidence as fake_evidence

from stoa.services import answer_judging, answer_recording, error_causes
from test_answer_recording import _Writes

TYPED: dict[str, Any] = {
    "challenge_id": "exercise-7",
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "gleichungen",
    "unit_id": "gleichungen-u1",
    "type": "text_input",
    "prompt": "Löse 3x + 12 = -3.",
    "correct_answer": "x = -5",
    "explanation": "3x = -15, also x = -5.",
}

SIGN = error_causes.rule_cause(error_causes.RULE_SIGN)
CLOSE = error_causes.rule_cause(error_causes.RULE_CLOSE)


# ── the number an answer holds ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("-5", ("#", "-5")),
        ("−5", ("#", "-5")),
        ("x = -5", ("x=#", "-5")),
        ("31,4", ("#", "31.4")),
        ("1'200", ("#", "1200")),
        ("12cm", ("# cm", "12")),
        ("34.–", ("#", "34")),
        ("10 000", ("#", "10000")),
        ("10 000", ("#", "10000")),
        ("10 000", ("#", "10000")),
        ("10’000", ("#", "10000")),
        ("x = -1 234 567", ("x=#", "-1234567")),
        ("12 500 m", ("# m", "12500")),
    ],
    ids=[
        "minus",
        "unicode minus",
        "equation",
        "decimal comma",
        "thousands",
        "unit",
        "price",
        "space thousands",
        "no-break space thousands",
        "narrow no-break space thousands",
        "typographic apostrophe thousands",
        "grouped equation",
        "grouped with unit",
    ],
)
def test_an_answer_with_one_number_is_read_as_judging_reads_it(
    answer: str, expected: tuple[str, str]
) -> None:
    found = answer_judging.single_number(answer)

    assert found is not None
    assert (found[0], str(found[1])) == expected


@pytest.mark.parametrize(
    "answer",
    [
        "2/5",
        "7; -7",
        "P(2 | 3)",
        "3-5",
        "fünf",
        "",
        "1.2.3",
        "1 2",
        "10 00",
        "10 000; 20 000",
        "P(1 000 | 2 000)",
        "4 125/1000",
    ],
)
def test_an_answer_that_is_not_one_number_has_none(answer: str) -> None:
    assert answer_judging.single_number(answer) is None


# ── the rules ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        ("5", "-5"),
        ("-5", "5"),
        ("x = 5", "x = -5"),
        ("-0,25", "0.25"),
        ("-12 cm", "12 cm"),
        ("-10 000", "10000"),
        ("-10 000 m", "10'000 m"),
    ],
)
def test_only_the_sign_differs(answer: str, key: str) -> None:
    assert error_causes.infer(answer, [key]) == SIGN


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        # Within 2 % of the key: a rounding or last-digit slip.
        ("3.1", "3.14"),
        ("98", "100"),
        ("102", "100"),
        ("0,51", "0.5"),
        ("x = -4,9", "x = -5"),
        # A whole number off by exactly one, the key at least 10: 7 · 8 = 57.
        ("57", "56"),
        ("11", "10"),
        ("-21", "-20"),
        # Thousands grouped in the answer or the key are read as one number.
        ("9 900", "10000"),
        ("10 001", "10'000"),
        ("x = 10 150", "x = 10 000"),
        ("12 499 CHF", "12 500 CHF"),
    ],
)
def test_a_number_close_to_the_key(answer: str, key: str) -> None:
    assert error_causes.infer(answer, [key]) == CLOSE


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        # More than 2 % off and not a whole number off by one.
        ("97", "100"),
        ("54", "56"),
        ("3", "3.14"),
        ("0.52", "0.5"),
        # Off by one under 10 is a different answer, not a slip.
        ("4", "5"),
        ("9", "8"),
        # Off by one, but not whole numbers.
        ("10.5", "11.5"),
        # Close, but the sign flipped too.
        ("-99", "100"),
        # Nothing is close to zero, and zero has no sign.
        ("0.01", "0"),
        ("-0", "0"),
        # Not the same answer around the number.
        ("5", "x = -5"),
        ("12 m", "-12 cm"),
        # Not a number at all, or several.
        ("fünf", "5"),
        ("2/5", "3/5"),
        ("7; 7", "7; -7"),
        ("", "5"),
        # Spaces that do not group thousands leave several numbers.
        ("1 2", "12"),
        ("100 01", "10000"),
        ("10 000; 20 001", "10000; 20000"),
    ],
)
def test_anything_else_has_no_rule(answer: str, key: str) -> None:
    assert error_causes.infer(answer, [key]) is None


def test_the_sign_rule_is_tried_before_closeness() -> None:
    """-100 is exactly the sign away from 100 and nothing else."""
    assert error_causes.infer("-100", ["100"]) == SIGN


def test_any_accepted_writing_of_the_key_counts() -> None:
    assert error_causes.infer("-0.5", ["1/2", "0.5"]) == SIGN


def test_a_list_answer_has_no_rule() -> None:
    assert error_causes.infer(["5", "3"], ["-5"]) is None


@pytest.mark.parametrize("rule", [error_causes.RULE_SIGN, error_causes.RULE_CLOSE])
def test_each_rule_is_a_deviation_with_one_sentence_per_locale(rule: str) -> None:
    cause = error_causes.rule_cause(rule)

    assert cause["category"] == "deviation"
    assert set(cause["misconception"]) == set(error_causes.LOCALES)
    assert all(text.strip() for text in cause["misconception"].values())


def test_the_rules_say_different_things() -> None:
    assert SIGN["misconception"]["en"] != CLOSE["misconception"]["en"]


# ── recording ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exercise", "answer", "expected"),
    [
        (TYPED, "x = 5", SIGN),
        (TYPED, "x=-4,9", CLOSE),
        (TYPED, "x = 3", {"category": "unclassified"}),
        (TYPED, "keine Ahnung", {"category": "unclassified"}),
        ({**TYPED, "type": "numeric", "correct_answer": "56"}, "57", CLOSE),
        ({**TYPED, "correct_answer": "-5", "accepted_answers": ["x = -5"]}, "x = 5", SIGN),
    ],
    ids=["sign", "close", "far", "words", "numeric exercise", "an accepted answer"],
)
def test_a_wrong_typed_answer_records_the_inferred_cause(
    monkeypatch: pytest.MonkeyPatch, exercise: dict[str, Any], answer: str, expected: Any
) -> None:
    recorded = _Writes(monkeypatch, [exercise])

    result = answer_recording.answer_practice("student-1", exercise, answer, locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert result.correct is False
    assert receipt["error_cause"] == expected


def test_the_key_as_the_reader_saw_it_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    translated = {**TYPED, "translations": {"fr": {"correct_answer": "x = -5,0 m"}}}
    recorded = _Writes(monkeypatch, [translated])

    answer_recording.answer_practice("student-1", translated, "x = 5,0 m", locale="fr")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["error_cause"] == SIGN


def test_a_right_typed_answer_has_no_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _Writes(monkeypatch, [TYPED])

    answer_recording.answer_practice("student-1", TYPED, "x=-5", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt.get("error_cause") is None


def test_an_untagged_distractor_is_not_ruled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A choice exercise's causes are the author's; the rules are for typed answers."""
    choice = {**TYPED, "type": "multiple_choice", "options": ["x = -5", "x = 5", "x = 3"]}
    recorded = _Writes(monkeypatch, [choice])

    answer_recording.answer_practice("student-1", choice, "x = 5", locale="de")

    [receipt] = recorded.by_kind["receipt"]
    assert receipt["error_cause"] == {"category": "unclassified"}


# ── the evidence ─────────────────────────────────────────────────────────────


def test_inferred_causes_are_tallied_like_authored_ones() -> None:
    def wrong(n: int, cause: dict[str, Any]) -> dict[str, Any]:
        return {
            "challenge_id": f"c{n}",
            "attempt_id": f"a{n:02d}",
            "correct": False,
            "unit_id": "u1",
            "created_at": f"2026-11-{n:02d}T10:00:00+00:00",
            "error_cause": cause,
        }

    evidence = fake_evidence.evidence(
        attempts=[wrong(1, {"category": "unclassified"}), wrong(2, SIGN), wrong(3, SIGN), wrong(4, CLOSE)]
    )

    assert [(item.category, item.misconception_in("it"), item.count) for item in evidence.recent_error_causes] == [
        ("deviation", SIGN["misconception"]["it"], 2),
        # A tie goes to the cause seen last.
        ("deviation", CLOSE["misconception"]["it"], 1),
        ("unclassified", "", 1),
    ]
    assert evidence.most_common_error_cause is not None
    assert evidence.most_common_error_cause.misconception_in("fr") == SIGN["misconception"]["fr"]
