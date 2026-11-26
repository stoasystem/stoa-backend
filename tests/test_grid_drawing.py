"""Drawing on a coordinate grid, judged by what the drawing is (#594).

The three sample exercises (`fixtures/grid_drawing_samples_594.json`) - plot
points, draw a rectangle of a given area, draw the image of a rotation - go
through a real migration into the practice partition of a table double and are
answered there. Around them: other ways to draw the same thing, what is not an
answer, what authoring refuses, and that no read a student makes before
answering carries the checks or the solutions.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
from typing import Any

import pytest

from stoa.db.repositories import practice_repo, review_repo
from stoa.services import (
    answer_recording,
    curriculum_migration_service,
    curriculum_ops_service,
    curriculum_service,
    error_causes,
    exercise_localization,
    figure_svg,
    grid_drawing,
    practice_context_service,
    practice_projection_service,
    review_service,
)
from stoa.services.curriculum_issues import Issue, IssueCode
from stoa.services.quiz import _exercise_preview as quiz_exercise_preview
from test_curriculum_publish_projection import install_seeded_table

SAMPLES = json.loads(
    (Path(__file__).parent / "fixtures" / "grid_drawing_samples_594.json").read_text(encoding="utf-8")
)
LESSON_ID = "grid-drawing-samples-594"
PLOT = f"{LESSON_ID}-q01"
RECTANGLE = f"{LESSON_ID}-q02"
ROTATION = f"{LESSON_ID}-q03"
OPERATOR = {
    "sub": "migration-operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    },
}
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch):
    """The samples migrated and published into a seeded table double."""
    table = install_seeded_table(monkeypatch)
    planned = curriculum_migration_service.dry_run(deepcopy(SAMPLES), OPERATOR)
    assert planned["publishReady"], planned["rows"][0]["validationIssues"]
    applied = curriculum_migration_service.apply_migration(
        planned["migrationId"], deepcopy(SAMPLES), planned["confirmationToken"], OPERATOR
    )
    assert applied["rows"][0]["pointer"]["publishedVersionId"] == applied["rows"][0]["versionId"]
    return table


def _challenge(exercise_id: str) -> dict[str, Any]:
    challenge = practice_repo.get_challenge(exercise_id)
    assert challenge is not None
    return challenge


def _points(**where: tuple[float, float]) -> list[dict[str, Any]]:
    return [{"label": name.replace("_", "'"), "x": x, "y": y} for name, (x, y) in where.items()]


def _floats(value: object) -> list[float]:
    """Every float in a row: the table refuses them."""
    if isinstance(value, dict):
        return [found for member in value.values() for found in _floats(member)]
    if isinstance(value, list):
        return [found for member in value for found in _floats(member)]
    return [value] if isinstance(value, float) else []


def _right(exercise_id: str, drawing: object) -> bool:
    return answer_recording.judge(_challenge(exercise_id), drawing, locale="de").correct


# ── the samples, published ───────────────────────────────────────────────────


def test_the_samples_are_published_with_their_grid_checks_and_solutions(published) -> None:
    rotation = _challenge(ROTATION)
    assert rotation["type"] == "grid_drawing"
    assert rotation["correct_answer"] == "A'(8|0); B'(8|3); C'(6|0); A'B'C'"
    assert len(rotation["checks"]) == 2
    assert not _floats(rotation)
    for exercise_id in (PLOT, RECTANGLE, ROTATION):
        assert grid_drawing.solutions(_challenge(exercise_id))


def test_plotted_points_are_right_in_any_order_and_wrong_one_grid_point_off(published) -> None:
    assert _right(PLOT, {"points": _points(A=(1, 2), B=(4, 5), C=(7, 1))})
    assert _right(PLOT, {"points": _points(C=(7, 1), A=(1, 2), B=(4, 5))})
    assert not _right(PLOT, {"points": _points(A=(1, 2), B=(4, 5), C=(7, 2))})
    assert not _right(PLOT, {"points": _points(A=(2, 1), B=(4, 5), C=(7, 1))})  # x and y swapped
    assert not _right(PLOT, {"points": _points(A=(1, 2), B=(4, 5))})
    assert not _right(PLOT, {"points": _points(A=(1, 2), B=(4, 5), C=(7, 1), D=(0, 0))})


@pytest.mark.parametrize(
    "corners",
    [
        [(1, 1), (5, 1), (5, 4), (1, 4)],  # 4 by 3
        [(5, 4), (5, 1), (1, 1), (1, 4)],  # another start, the other way round
        [(2, 2), (8, 2), (8, 4), (2, 4)],  # 6 by 2
        [(0, 0), (0, 6), (2, 6), (2, 0)],  # 2 by 6 standing
        [(1, 2), (3, 0), (6, 3), (4, 5)],  # turned: sides √8 and √18
    ],
)
def test_any_rectangle_of_area_12_is_right(published, corners: list[tuple[int, int]]) -> None:
    labels = ["P", "Q", "R", "S"]
    drawing = {
        "points": [{"label": label, "x": x, "y": y} for label, (x, y) in zip(labels, corners, strict=True)],
        "polygons": [labels],
    }
    assert _right(RECTANGLE, drawing)


@pytest.mark.parametrize(
    "drawing",
    [
        # One corner a grid point off: no longer a rectangle.
        {"points": _points(P=(1, 1), Q=(5, 1), R=(5, 4), S=(1, 5)), "polygons": [["P", "Q", "R", "S"]]},
        # A rectangle of area 15.
        {"points": _points(P=(1, 1), Q=(6, 1), R=(6, 4), S=(1, 4)), "polygons": [["P", "Q", "R", "S"]]},
        # The four sides drawn as segments, but no polygon.
        {"points": _points(P=(1, 1), Q=(5, 1), R=(5, 4), S=(1, 4)),
         "segments": [["P", "Q"], ["Q", "R"], ["R", "S"], ["S", "P"]]},
        # One side missing: three corners make a triangle.
        {"points": _points(P=(1, 1), Q=(5, 1), R=(5, 4)), "polygons": [["P", "Q", "R"]]},
        # Two rectangles where one is asked for.
        {"points": _points(P=(1, 1), Q=(5, 1), R=(5, 4), S=(1, 4), T=(6, 0), U=(8, 0), V=(8, 6), W=(6, 6)),
         "polygons": [["P", "Q", "R", "S"], ["T", "U", "V", "W"]]},
    ],
)
def test_a_wrong_rectangle_is_wrong(published, drawing: dict[str, Any]) -> None:
    assert not _right(RECTANGLE, drawing)


def test_the_rotated_triangle_is_right_however_it_is_drawn(published) -> None:
    corners = _points(A_=(8, 0), B_=(8, 3), C_=(6, 0))
    assert _right(ROTATION, {"points": corners, "polygons": [["A'", "B'", "C'"]]})
    assert _right(ROTATION, {"points": corners[::-1], "polygons": [["C'", "B'", "A'"]]})
    # Other names for the corners do not matter: only where they lie.
    assert _right(ROTATION, {"points": _points(P=(6, 0), Q=(8, 0), R=(8, 3)), "polygons": [["Q", "R", "P"]]})


@pytest.mark.parametrize(
    "drawing",
    [
        # Turned the other way (clockwise).
        {"points": _points(A_=(2, 8), B_=(2, 5), C_=(4, 8)), "polygons": [["A'", "B'", "C'"]]},
        # Turned by 180°.
        {"points": _points(A_=(9, 7), B_=(6, 7), C_=(9, 5)), "polygons": [["A'", "B'", "C'"]]},
        # One corner a grid point off.
        {"points": _points(A_=(8, 0), B_=(8, 3), C_=(7, 0)), "polygons": [["A'", "B'", "C'"]]},
        # The corners, but no triangle.
        {"points": _points(A_=(8, 0), B_=(8, 3), C_=(6, 0))},
    ],
)
def test_a_wrong_image_is_wrong(published, drawing: dict[str, Any]) -> None:
    assert not _right(ROTATION, drawing)


@pytest.mark.parametrize(
    ("exercise_id", "raw"),
    [
        (PLOT, {"points": _points(A=(1, 2), B=(4, 5), C=(9, 1))}),  # off the grid
        (PLOT, {"points": _points(A=(1, 2), B=(4, 5), C=(7, -1))}),
        (PLOT, {"points": _points(A=(1.5, 2))}),  # a whole-unit grid
        (PLOT, {"points": [{"label": f"P{index}", "x": index % 9, "y": index // 9} for index in range(27)]}),
        (RECTANGLE, {"points": _points(P=(1, 1), Q=(5, 1)), "segments": [["P", "Q"]] * 2}),
        (RECTANGLE, {"points": _points(P=(1, 1), Q=(5, 1)), "segments": [["P", "X"]]}),
        (RECTANGLE, {"points": _points(P=(1, 1), Q=(1, 1))}),  # two points on one grid point
        (RECTANGLE, {"points": _points(P=(1, 1)), "polygons": [["P", "P", "P"]]}),
        (RECTANGLE, {"points": [{"label": "P", "x": 1, "y": 1}, {"label": "P", "x": 2, "y": 1}]}),
        (RECTANGLE, {"points": [{"label": "P", "x": "1", "y": 1}]}),  # text is no number
        (RECTANGLE, {"points": [{"label": "P", "x": True, "y": 1}]}),
        (RECTANGLE, {"points": [{"label": "toolong", "x": 1, "y": 1}]}),
        (RECTANGLE, {"points": [], "segments": [], "polygons": []}),  # nothing drawn
        (RECTANGLE, {"lines": []}),
        (ROTATION, {"points": _points(A=(8, 0))}),  # a given point's label
        (ROTATION, [0, 1]),
        (ROTATION, "A'(8|0)"),
    ],
)
def test_what_is_not_a_drawing_is_refused(published, exercise_id: str, raw: object) -> None:
    with pytest.raises(answer_recording.AnswerInvalid):
        answer_recording.judge(_challenge(exercise_id), raw, locale="de")


def test_a_drawing_may_join_the_given_points(published) -> None:
    # A segment from a given point to a point of the student's own is a drawing.
    judgement = answer_recording.judge(
        _challenge(ROTATION),
        {"points": _points(A_=(8, 0)), "segments": [["A", "A'"]]},
        locale="de",
    )
    assert judgement.correct is False


def test_answering_records_the_drawing_and_shows_the_solution_after(
    published, monkeypatch: pytest.MonkeyPatch
) -> None:
    published.seed_active_account("student-1")
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)
    drawing = {"points": _points(P=(1, 1), Q=(6, 1), R=(6, 4), S=(1, 4)), "polygons": [["P", "Q", "R", "S"]]}

    result = answer_recording.answer_practice("student-1", _challenge(RECTANGLE), drawing, locale="it")

    assert result.correct is False
    assert result.standard_answer == "P(1|1); Q(5|1); R(5|4); S(1|4); PQRS"
    assert result.standard_drawing is not None
    assert result.standard_drawing.model_dump()["points"][1] == {"label": "Q", "x": 5, "y": 1}
    [receipt] = [row for key, row in published.rows.items() if key[0] == "ATTEMPTS#student-1" and key[1].startswith("ATTEMPT#")]
    assert receipt["submitted_answer"]["polygons"] == [["P", "Q", "R", "S"]]
    assert receipt["error_cause"] == {"category": error_causes.UNCLASSIFIED}
    assert result.feedback == practice_projection_service.answer_feedback({}, "it")[1]

    mistake = practice_projection_service.build_mistake_projection(receipt)
    assert mistake.model_dump(by_alias=True)["yourAnswer"]["points"][0] == {"label": "P", "x": 1, "y": 1}
    assert practice_context_service._answer_text(receipt) == "P(1|1); Q(6|1); R(6|4); S(1|4); PQRS"  # noqa: SLF001


# ── geometry ─────────────────────────────────────────────────────────────────


def _exercise(checks: list[dict[str, Any]], given: dict[str, Any] | None = None, step: object = 1) -> dict[str, Any]:
    grid: dict[str, Any] = {"xMin": -6, "xMax": 6, "yMin": -6, "yMax": 6, "step": step}
    if given:
        grid["given"] = given
    return {"type": "grid_drawing", "grid": grid, "checks": checks}


def _judge(exercise: dict[str, Any], raw: dict[str, Any]) -> bool:
    drawing = grid_drawing.submitted_drawing(raw, exercise)
    return grid_drawing.judge(drawing, exercise)


def test_a_square_is_a_rectangle_and_a_perimeter_is_exact() -> None:
    square = {"points": _points(A=(0, 0), B=(3, 0), C=(3, 3), D=(0, 3)), "polygons": [["A", "B", "C", "D"]]}
    assert _judge(_exercise([{"kind": "polygon", "shape": "square", "perimeter": 12}]), square)
    assert _judge(_exercise([{"kind": "polygon", "shape": "rectangle", "area": 9}]), square)
    oblong = {"points": _points(A=(0, 0), B=(4, 0), C=(4, 2), D=(0, 2)), "polygons": [["A", "B", "C", "D"]]}
    assert not _judge(_exercise([{"kind": "polygon", "shape": "square"}]), oblong)
    # A tilted square with sides √2: its perimeter 4√2 is no rational number.
    tilted = {"points": _points(A=(1, 0), B=(2, 1), C=(1, 2), D=(0, 1)), "polygons": [["A", "B", "C", "D"]]}
    assert _judge(_exercise([{"kind": "polygon", "shape": "square", "area": 2}]), tilted)
    assert not _judge(_exercise([{"kind": "polygon", "perimeter": "5.66"}]), tilted)
    # A triangle with sides 3, 4, 5.
    triangle = {"points": _points(A=(0, 0), B=(4, 0), C=(4, 3)), "polygons": [["A", "B", "C"]]}
    assert _judge(_exercise([{"kind": "polygon", "shape": "triangle", "area": 6, "perimeter": 12}]), triangle)


def test_on_a_half_grid_areas_are_exact() -> None:
    exercise = _exercise([{"kind": "polygon", "shape": "rectangle", "area": "3.75"}], step=0.5)
    drawing = {"points": _points(A=(0, 0), B=(2.5, 0), C=(2.5, 1.5), D=(0, 1.5)), "polygons": [["A", "B", "C", "D"]]}
    assert _judge(exercise, drawing)
    assert not _judge({**exercise, "checks": [{"kind": "polygon", "area": "15/4"}, {"kind": "count", "polygons": 2}]}, drawing)
    with pytest.raises(ValueError):
        grid_drawing.submitted_drawing({"points": _points(A=(0.25, 0))}, exercise)


def test_a_reflection_and_a_translation_are_images() -> None:
    given = {"points": _points(A=(1, 1), B=(3, 1), C=(1, 4)), "polygons": [["A", "B", "C"]]}
    mirrored = {"points": _points(P=(-1, 1), Q=(-3, 1), R=(-1, 4)), "polygons": [["R", "Q", "P"]]}
    reflect = _exercise([{"kind": "image", "of": ["A", "B", "C"], "reflect": {"through": [[0, 0], [0, 1]]}}], given)
    assert _judge(reflect, mirrored)
    # The diagonal y = x: (1|4) goes to (4|1).
    diagonal = _exercise([{"kind": "image", "of": ["A", "B", "C"], "reflect": {"through": [[0, 0], [2, 2]]}}], given)
    assert _judge(diagonal, {"points": _points(P=(1, 1), Q=(1, 3), R=(4, 1)), "polygons": [["P", "Q", "R"]]})
    shift = _exercise([{"kind": "image", "of": ["A", "B"], "translate": [2, -3]}], given)
    assert _judge(shift, {"points": _points(P=(3, -2), Q=(5, -2)), "segments": [["Q", "P"]]})
    assert not _judge(shift, {"points": _points(P=(3, -2), Q=(5, -1)), "segments": [["Q", "P"]]})


def test_a_figure_completed_to_be_symmetric() -> None:
    given = {"points": _points(A=(0, 0), B=(2, 0), C=(2, 3)), "segments": [["A", "B"], ["B", "C"]]}
    exercise = _exercise([{"kind": "symmetric", "through": [[0, 0], [0, 1]]}], given)
    completed = {"points": _points(D=(-2, 0), E=(-2, 3)), "segments": [["A", "D"], ["D", "E"]]}
    assert _judge(exercise, completed)
    assert not _judge(exercise, {"points": _points(D=(-2, 0), E=(-2, 3)), "segments": [["A", "D"]]})


def test_a_segment_check_reads_either_way_and_polygon_sides() -> None:
    exercise = _exercise([{"kind": "segment", "from": [0, 0], "to": [3, 2]}])
    assert _judge(exercise, {"points": _points(A=(3, 2), B=(0, 0)), "segments": [["A", "B"]]})
    assert _judge(exercise, {"points": _points(A=(0, 0), B=(3, 2), C=(0, 2)), "polygons": [["C", "A", "B"]]})
    assert not _judge(exercise, {"points": _points(A=(0, 0), B=(3, 2))})


def test_numbers_are_stored_without_floats_and_sent_as_numbers() -> None:
    assert grid_drawing.stored_number(Fraction(5, 2)) == Decimal("2.5")
    assert grid_drawing.stored_number(Fraction(4)) == 4
    assert grid_drawing.stored_number(Fraction(1, 3)) == "1/3"
    assert grid_drawing.client_number(Fraction(5, 2)) == 2.5
    exercise = {"grid": {"xMin": 0, "xMax": 4, "yMin": 0, "yMax": 4, "step": 0.5}, "checks": [{"kind": "polygon", "area": 1.25}]}
    grid_drawing.normalize(exercise)
    assert exercise["grid"]["step"] == Decimal("0.5")
    assert exercise["checks"][0]["area"] == Decimal("1.25")


def test_the_grid_is_drawn_inside_the_figure_allowlist() -> None:
    for exercise in SAMPLES["lessons"][0]["exercises"]:
        figure = grid_drawing.render(exercise)
        assert figure is not None
        assert figure_svg.figure_issues(figure) == []
        assert not figure_svg.has_text(figure)  # numbers and point names only: one for every language


# ── authoring ────────────────────────────────────────────────────────────────


def _sample(number: int, **change: Any) -> dict[str, Any]:
    exercise = deepcopy(SAMPLES["lessons"][0]["exercises"][number - 1])
    exercise.update(change)
    return exercise


def _issues(exercise: dict[str, Any]) -> list[tuple[str, Issue]]:
    [stored] = curriculum_ops_service._exercise_payloads(LESSON_ID, [exercise])  # noqa: SLF001
    return [
        (item["field"], Issue(IssueCode(item["code"]), tuple(sorted(item["params"].items()))))
        for item in curriculum_ops_service._validation_issues({}, [stored], level="draft")  # noqa: SLF001
        if item["field"].startswith("exercises[0]")
    ]


def test_the_samples_author_without_an_issue() -> None:
    for exercise in SAMPLES["lessons"][0]["exercises"]:
        assert _issues(deepcopy(exercise)) == []


@pytest.mark.parametrize(
    ("exercise", "expected"),
    [
        # A solution that fails its own checks: here the rectangle has area 15.
        (
            _sample(2, solutions=[{"points": _points(P=(1, 1), Q=(6, 1), R=(6, 4), S=(1, 4)),
                                   "polygons": [["P", "Q", "R", "S"]]}]),
            ("exercises[0].solutions[0]", Issue.of(IssueCode.GRID_SOLUTION_FAILS_CHECKS)),
        ),
        (
            _sample(1, solutions=[{"points": _points(A=(1, 2), B=(4, 5), C=(7, 2))}]),
            ("exercises[0].solutions[0]", Issue.of(IssueCode.GRID_SOLUTION_FAILS_CHECKS)),
        ),
        (
            _sample(1, solutions=[]),
            ("exercises[0].solutions", Issue.of(IssueCode.GRID_SOLUTION_INVALID, max_solutions=5)),
        ),
        (
            _sample(1, solutions=[{"points": _points(A=(1, 2), B=(4, 5), C=(9, 1))}]),
            ("exercises[0].solutions[0]", Issue.of(IssueCode.GRID_SOLUTION_INVALID, max_solutions=5)),
        ),
        # A check naming a point no solution draws, or a given point that is not there.
        (
            _sample(1, checks=[*_sample(1)["checks"], {"kind": "point", "label": "D", "x": 0, "y": 0}]),
            ("exercises[0].checks[4]", Issue.of(IssueCode.GRID_LABEL_UNKNOWN, label="D")),
        ),
        (
            _sample(3, checks=[{"kind": "image", "of": ["A", "B", "X"], "rotate": {"center": [5, 4], "angle": 90}}]),
            ("exercises[0].checks[0]", Issue.of(IssueCode.GRID_LABEL_UNKNOWN, label="X")),
        ),
        (
            _sample(3, checks=[{"kind": "image", "of": ["A"], "rotate": {"center": [5, 4], "angle": 45}}]),
            ("exercises[0].checks[0]", Issue.of(IssueCode.GRID_CHECK_INVALID, part="transform")),
        ),
        (
            _sample(2, checks=[{"kind": "polygon", "shape": "circle"}]),
            ("exercises[0].checks[0]", Issue.of(IssueCode.GRID_CHECK_INVALID, part="shape")),
        ),
        (
            _sample(2, checks=[{"kind": "angle"}]),
            ("exercises[0].checks[0]", Issue.of(IssueCode.GRID_CHECK_INVALID, part="kind")),
        ),
        (_sample(2, checks=[]), ("exercises[0].checks", Issue.of(IssueCode.GRID_CHECKS_INVALID, max_checks=30))),
        (
            _sample(2, grid={"xMin": 0, "xMax": 10, "yMin": 0, "yMax": 8, "step": 0.25}),
            ("exercises[0].grid", Issue.of(IssueCode.GRID_INVALID)),
        ),
        (_sample(2, grid=None), ("exercises[0].grid", Issue.of(IssueCode.GRID_INVALID))),
        (
            _sample(2, figure='<svg xmlns="http://www.w3.org/2000/svg"/>'),
            ("exercises[0].figure", Issue.of(IssueCode.GRID_FIGURE_AUTHORED)),
        ),
        (
            {**_sample(2), "type": "text_input", "answerKey": "12"},
            ("exercises[0].grid", Issue.of(IssueCode.GRID_WITHOUT_GRID_DRAWING)),
        ),
    ],
)
def test_authoring_refuses_a_bad_grid_exercise(exercise: dict[str, Any], expected: tuple[str, Issue]) -> None:
    assert expected in _issues(exercise)


def test_a_solution_failing_its_checks_fails_the_migration_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    install_seeded_table(monkeypatch)
    manifest = deepcopy(SAMPLES)
    manifest["lessons"][0]["exercises"][2]["checks"][0]["rotate"]["angle"] = 270

    planned = curriculum_migration_service.dry_run(manifest, OPERATOR)

    assert planned["publishReady"] is False
    [issue] = planned["rows"][0]["validationIssues"]
    assert (issue["field"], issue["code"]) == ("exercises[2].solutions[0]", "grid_solution_fails_checks")


def test_the_key_text_is_the_same_in_every_language() -> None:
    [stored] = curriculum_ops_service._exercise_payloads(LESSON_ID, [_sample(3)])  # noqa: SLF001
    for locale in ("de", "en", "fr", "it"):
        assert exercise_localization.localized(stored, locale)["correct_answer"] == stored["correct_answer"]


# ── nothing a student reads before answering carries the checks or solutions ─


def _assert_answer_free(projection: object) -> None:
    text = json.dumps(projection, ensure_ascii=False, default=str)
    for leak in ("checks", "solutions", "correct_answer", "correctAnswer", "answer_key", "answerKey",
                 "standardAnswer", "standardDrawing", "A'(8|0)", "rotate", "explanation"):
        assert leak not in text, leak
    # The image triangle's corners are nowhere in the given figure.
    assert '"x": 8, "y": 0' not in text


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_no_pre_answer_projection_carries_the_checks_or_solutions(
    published, monkeypatch: pytest.MonkeyPatch, locale: str
) -> None:
    rotation = _challenge(ROTATION)

    lesson = curriculum_service.get_lesson_detail(LESSON_ID, locale=locale)
    _assert_answer_free(lesson)
    shown = {item["id"]: item for item in lesson["exercises"]}
    assert shown[ROTATION]["grid"]["given"]["points"][3] == {"label": "Z", "x": 5, "y": 4}
    assert shown[ROTATION]["grid"]["labels"] == ["A'", "B'", "C'"]
    assert figure_svg.figure_issues(shown[ROTATION]["figure"]) == []

    preview = practice_projection_service.build_challenge_preview(rotation, locale)
    _assert_answer_free(preview)
    assert preview["type"] == "grid_drawing"
    assert preview["grid"]["xMax"] == 10 and preview["grid"]["step"] == 1

    asked = quiz_exercise_preview([ROTATION], locale)
    _assert_answer_free(asked)
    assert asked["grid"]["given"]["polygons"] == [["A", "B", "C"]]

    published.seed_active_account("student-1")
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)
    review_service.record_answer(student_id="student-1", challenge=rotation, correct=False, answered_at=NOW)
    due = review_service.due_review(student_id="student-1", now=NOW + timedelta(hours=1), locale=locale)
    _assert_answer_free(due)
    [card] = due["items"]
    assert card["type"] == "grid_drawing"
    assert card["grid"]["limits"] == {"points": 26, "segments": 30, "polygons": 6}
    assert card["figure"] == preview["figure"]
