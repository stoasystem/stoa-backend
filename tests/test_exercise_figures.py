"""An exercise can show a figure: an SVG drawing held to an allowlist, in four languages.

The client draws a figure straight into the page, so the authoring path refuses
anything a diagram does not need - script, event handlers, links, external
references - rather than cleaning it, and the student reads get the figure of
their own language where the exercise has one.
"""

from __future__ import annotations

import pytest

from stoa.services import curriculum_ops_service, exercise_localization, figure_svg, practice_projection_service

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">{body}</svg>'
TRIANGLE = SVG.format(
    body='<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">'
    '<path d="M0,0 L6,3 L0,6 z" fill="currentColor"/></marker></defs>'
    '<polygon points="10,50 90,50 50,10" fill="none" stroke="currentColor" stroke-width="2"/>'
    '<line x1="10" y1="55" x2="90" y2="55" stroke="currentColor" marker-end="url(#arrow)"/>'
    '<text x="50" y="58" font-size="6" text-anchor="middle">Grundseite 8 cm</text>'
)


def test_a_diagram_passes() -> None:
    assert figure_svg.figure_issues(TRIANGLE) == []
    assert figure_svg.has_text(TRIANGLE)
    assert not figure_svg.has_text(SVG.format(body='<text x="1" y="1">8</text>'))


@pytest.mark.parametrize(
    ("svg", "problem"),
    [
        (SVG.format(body="<script>alert(1)</script>"), "Element 'script'"),
        (SVG.format(body='<rect width="1" height="1" onclick="steal()"/>'), "Attribute 'onclick'"),
        (SVG.format(body='<foreignObject><p>x</p></foreignObject>'), "Element 'foreignObject'"),
        (SVG.format(body='<image href="https://example.com/x.png"/>'), "Element 'image'"),
        (SVG.format(body='<rect fill="url(https://example.com/x)"/>'), "only refer to a marker"),
        (SVG.format(body='<rect style="fill:red"/>'), "Attribute 'style'"),
        ('<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>', "document type"),
        ('<svg><rect/></svg>', "SVG namespace"),
        ("<svg", "well-formed"),
        ("x" * (figure_svg.MAX_FIGURE_LENGTH + 1), "at most"),
    ],
)
def test_anything_beyond_a_diagram_is_refused(svg: str, problem: str) -> None:
    assert any(problem in message for message in figure_svg.figure_issues(svg))


@pytest.mark.parametrize(
    "attribute",
    [
        # CSS reads a function name in any case, and an escape as the letter (#168).
        'fill="URL(https://example.com/p.svg#p)"',
        'fill="\\75 rl(https://example.com/p.svg#p)"',
        'marker-end="URL(https://example.com/m.svg#m)"',
        'stroke="url (https://example.com/p.svg#p)"',
        'fill="Url(#arrow)"',
        'stroke="red\\"',
        # Written just so, but to an id the figure does not have.
        'marker-end="url(#elsewhere)"',
        'marker-end="url(#elsewhere.svg)"',
    ],
)
def test_a_reference_out_of_the_figure_is_refused(attribute: str) -> None:
    svg = TRIANGLE.replace("</svg>", f'<rect width="1" height="1" {attribute}/></svg>')
    assert any("only refer to a marker" in message for message in figure_svg.figure_issues(svg))


def test_a_backslash_in_a_name_is_just_text() -> None:
    svg = SVG.format(body='<rect width="1" height="1" aria-label="A \\ B"/>')
    assert figure_svg.figure_issues(svg) == []


def _exercise(**extra: object) -> dict:
    return curriculum_ops_service._exercise_payloads("lesson-1", [{  # noqa: SLF001
        "exerciseId": "lesson-1-q1", "type": "multiple_choice", "prompt": "Welche Figur?",
        "options": ["A", "B"], "answerKey": "A", "explanation": "x", **extra,
    }])[0]


def test_authoring_carries_figures_and_refuses_a_bad_one() -> None:
    good = _exercise(figure=TRIANGLE, optionFigures=[TRIANGLE, ""],
                     translations={"fr": {"prompt": "Quelle figure ?", "options": ["A", "B"],
                                          "correctAnswer": "A", "figure": TRIANGLE.replace("Grundseite", "Base")}})
    assert good["figure"] == TRIANGLE and good["option_figures"] == [TRIANGLE, ""]
    assert curriculum_ops_service._choice_issues(good) == []  # noqa: SLF001
    assert exercise_localization.figure_issues(good, good["options"]) == []
    assert exercise_localization.translation_issues(good, max_text=2000) == []

    bad = _exercise(figure=SVG.format(body="<script/>"), optionFigures=[TRIANGLE])
    messages = exercise_localization.figure_issues(bad, bad["options"])
    assert any("script" in m for m in messages) and any("one per option" in m for m in messages)


def test_a_student_sees_the_figure_of_their_language() -> None:
    french = TRIANGLE.replace("Grundseite", "Base")
    row = {
        "challenge_id": "c1", "lesson_id": "l1", "type": "multiple_choice", "prompt": "Welche Figur?",
        "options": ["A", "B"], "correct_answer": "A", "figure": TRIANGLE, "option_figures": [TRIANGLE, ""],
        "translations": {"fr": {"prompt": "Quelle figure ?", "options": ["A", "B"], "correct_answer": "A",
                                "figure": french}},
    }

    shown_fr = practice_projection_service.build_challenge_preview(row, "fr")
    shown_it = practice_projection_service.build_challenge_preview(row, "it")

    assert shown_fr["figure"] == french and shown_fr["optionFigures"] == [TRIANGLE, ""]
    assert shown_it["figure"] == TRIANGLE
    assert "figure" not in practice_projection_service.build_challenge_preview(
        {k: v for k, v in row.items() if k not in {"figure", "option_figures"}}, "de"
    )
