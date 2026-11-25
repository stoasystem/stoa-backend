"""A letter that names a point, event, set or body is found when it is left outside the formula beside its
neighbours, and nothing else is (stoa-backend#603).

The cases are the shapes met in the 87 candidates of #603: names to find, and the articles, units, option
words and coordinates that look like them and must not be reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_letter_names as check


@pytest.mark.parametrize(
    "text",
    [
        "A and $B$ are independent, $P(B)=\\frac{1}{3}$.",
        "A e $B$ sono indipendenti.",
        "A et $B$ sont indépendants.",
        "The letters A, $B$ and $C$ are all different.",
        "Points A and $A'$ are symmetric about the line $l$.",
        "At least one of A or $B$ happens",
        "After opening, $L$ and A form a loop.",
        "Each sample is counted twice ($A$, $B$ and $B$, A), so there are 45.",
        "$A$ und $B$ sind unabhängig, $P$(A)$=\\frac{1}{2}$.",
    ],
)
def test_a_name_beside_a_formula_is_found(text: str) -> None:
    assert [letter for _, letter in check.letters_in(text)], text


@pytest.mark.parametrize(
    "text",
    [
        "$A$ and $B$ are independent.",
        "A positively charged sphere $C$ is brought close.",
        "A rectangular sheet $ABCD$ has $AB=8$.",
        "$q = It = 5 \\times 120 = 600$ C, $W = Eq = 7200$ J.",
        "the total kinetic energy 22 J. With $v_{A}'=2$, it is 18 J and $A$ stops.",
        "$W = 5\\times 10^{4}$ J, $P = 2500$ W.",
        "Gib beide Werte an (z. B. 3; 5), Reihenfolge beliebig.",
        "ainsi A(3 ; 2) et B(-2 ; -3), donc $OC=1$.",
        "$U_{1} = 1.45$ V at $I_{1} = 0.10$ A and $U_{2} = 1.25$ V.",
        "$P(A)=\\frac{1}{2}$, $P(B)=\\frac{1}{3}$.",
    ],
)
def test_articles_units_and_coordinates_are_not_names(text: str) -> None:
    assert check.letters_in(text) == [], text


def _manifest(exercises: list[dict]) -> dict:
    return {"lessons": [{"publicLessonId": "lesson-1", "exercises": exercises}]}


def test_every_display_text_and_locale_is_read_in_either_key_style() -> None:
    camel = {
        "exerciseId": "ex-1",
        "prompt": "$A$ und $B$ sind unabhängig.",
        "options": ["A und $B$"],
        "translations": {"en": {"prompt": "fine", "correctFeedback": "A and $B$ again"}},
    }
    snake = {
        "exercise_id": "ex-2",
        "prompt": "fine",
        "translations": {"it": {"explanation": "A e $B$", "incorrect_feedback": "fine"}},
    }

    found = check.findings(_manifest([camel, snake]))

    assert [(f.exercise_id, f.locale, f.field) for f in found] == [
        ("ex-1", "de", "options[0]"),
        ("ex-1", "en", "correctFeedback"),
        ("ex-2", "it", "explanation"),
    ]


def test_the_command_fails_on_a_name_and_passes_what_is_allowed(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(_manifest([{"exerciseId": "kb-x", "prompt": "corner of A, $Q$ is the top"}])),
        encoding="utf-8",
    )
    allow = tmp_path / "allow.txt"
    allow.write_text("# letters that stay\nkb-x  pieces A and B are figure labels\n", encoding="utf-8")

    assert check.main([str(manifest)]) == 1
    assert "kb-x [de] prompt: A" in capsys.readouterr().out
    assert check.main([str(manifest), "--allow", str(allow)]) == 0
    assert "allowed: kb-x (pieces A and B are figure labels)" in capsys.readouterr().out


def test_an_allowed_exercise_needs_a_reason(tmp_path: Path) -> None:
    allow = tmp_path / "allow.txt"
    allow.write_text("kb-x\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="without a reason"):
        check.read_allowed(allow)
