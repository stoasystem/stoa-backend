"""Batch 4 of the ZAP1 figure tasks: twelve drawings on the grid (#597).

`fixtures/zap_grid_drawing_597.json` is the migration manifest of the batch:
four new practice sets holding twelve `grid_drawing` exercises adapted from
eleven ZAP1 originals (plot points, join them, draw a rectangle or square of a
given area or perimeter, draw the image of a rotation or a reflection, complete
a figure to be symmetric). Here the manifest goes through a real dry run, apply
and publish into a table double, and every exercise is answered there:

- every solution it stores is right, and so are other ways to draw the same;
- at least two drawings that are almost right are wrong, and are still drawings
  (judged, not refused);
- the standard answer is worked out a second time here, from the given figure
  and the task alone, without `grid_drawing`'s geometry, and agrees;
- the coordinates each language names are the ones the checks ask for.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import re
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.db import table as db_table
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.services import (
    answer_recording,
    curriculum_analytics_service,
    curriculum_migration_service,
    curriculum_ops_service,
    exercise_localization,
    figure_svg,
    grid_drawing,
    knowledge_base_catalog,
    practice_projection_service,
)

MANIFEST = json.loads(
    (Path(__file__).parent / "fixtures" / "zap_grid_drawing_597.json").read_text(encoding="utf-8")
)
LOCALES = ("de", "en", "fr", "it")
EXERCISES: dict[str, dict[str, Any]] = {
    exercise["exerciseId"]: exercise
    for lesson in MANIFEST["lessons"]
    for exercise in lesson["exercises"]
}
PREFIX = "kb-zap-stoa-zap1-"
PLOT = f"{PREFIX}2024-2a-v1"
PLOT_HALVES = f"{PREFIX}d0833-1b-v1"
JOIN = f"{PREFIX}d0833-1c-v1"
TRIANGLE = f"{PREFIX}2026-4a-v1"
AREA_18 = f"{PREFIX}d0825-1a-v1"
SQUARE_9 = f"{PREFIX}d0825-1b-v1"
AREA_10_ROUND_14 = f"{PREFIX}d0825-1c-v1"
SQUARE_ROUND_10 = f"{PREFIX}d0825-1d-v1"
TURN_RIGHT = f"{PREFIX}2022-9a-v1"
TURN_LEFT = f"{PREFIX}2022-9a-v2"
MIRROR = f"{PREFIX}2022-9b-v1"
BOTH_DIAGONALS = f"{PREFIX}2022-9c-v1"
#: The eleven originals of #597 this batch adapts; 2026-2b is left to batch 3 (#596).
ORIGINALS = {
    "ORIG-ZAP1-2024-2a", "ORIG-ZAP1-D0833-1b", "ORIG-ZAP1-D0833-1c", "ORIG-ZAP1-2026-4a",
    "ORIG-ZAP1-D0825-1a", "ORIG-ZAP1-D0825-1b", "ORIG-ZAP1-D0825-1c", "ORIG-ZAP1-D0825-1d",
    "ORIG-ZAP1-2022-9a", "ORIG-ZAP1-2022-9b", "ORIG-ZAP1-2022-9c",
}
OPERATOR = {
    "sub": "migration-operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    },
}


@pytest.fixture(scope="module")
def migrated() -> dict[str, Any]:
    """The manifest dry-run, applied as drafts, reviewed and published in a table
    double seeded as production is (knowledge base live); the dry run's answer
    and the published exercises as the practice partition stores them."""
    table = FakeTable()
    table.seed(*seed_practice.seed_rows(knowledge_base=seed_practice.knowledge_base_live_mode([])))
    db_table.install(table)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(curriculum_analytics_service, "record_publish_event", lambda *a, **k: None)
        planned = curriculum_migration_service.dry_run(deepcopy(MANIFEST), OPERATOR)
        applied = curriculum_migration_service.apply_migration(
            planned["migrationId"], deepcopy(MANIFEST), planned["confirmationToken"], OPERATOR
        )
        for row in applied["rows"]:
            lesson_id, version_id = row["publicLessonId"], row["versionId"]
            curriculum_ops_service.submit_review(lesson_id, version_id, OPERATOR)
            curriculum_ops_service.approve(lesson_id, version_id, OPERATOR)
            curriculum_ops_service.publish(
                lesson_id, version_id, OPERATOR, expected_published_version_id=None
            )
            pointer = curriculum_ops_repo.get_pointer(lesson_id) or {}
            assert pointer.get("published_version_id") == version_id
        challenges = {exercise_id: practice_repo.get_challenge(exercise_id) for exercise_id in EXERCISES}
        lessons = {
            lesson["publicLessonId"]: practice_repo.get_lesson(lesson["publicLessonId"])
            for lesson in MANIFEST["lessons"]
        }
    db_table.install(None)
    return {"planned": planned, "challenges": deepcopy(challenges), "lessons": deepcopy(lessons)}


def _right(migrated: dict[str, Any], exercise_id: str, drawing: object, locale: str = "de") -> bool:
    challenge = migrated["challenges"][exercise_id]
    assert challenge is not None, exercise_id
    return answer_recording.judge(challenge, drawing, locale=locale).correct


def _points(*items: tuple[str, float, float]) -> list[dict[str, Any]]:
    return [{"label": label, "x": x, "y": y} for label, x, y in items]


def _path(places: list[tuple[float, float]], labels: str = "WXYZ", skip: int | None = None) -> dict[str, Any]:
    """An open line through `places`, drawn as points joined by segments."""
    names = list(labels[: len(places)])
    segments = [[names[index], names[index + 1]] for index in range(len(names) - 1)]
    if skip is not None:
        del segments[skip]
    return {"points": _points(*((name, x, y) for name, (x, y) in zip(names, places, strict=True))),
            "segments": segments}


def _polygon(corners: list[tuple[float, float]], labels: str = "PQRSTUVW") -> dict[str, Any]:
    names = list(labels[: len(corners)])
    return {"points": _points(*((name, x, y) for name, (x, y) in zip(names, corners, strict=True))),
            "polygons": [names]}


def _box(x: float, y: float, width: float, height: float) -> dict[str, Any]:
    return _polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)])


# ── the manifest as a migration ──────────────────────────────────────────────


def test_the_dry_run_creates_four_draft_practice_sets_without_an_issue(migrated) -> None:
    planned = migrated["planned"]
    assert planned["summary"] == {
        "total": 4, "creates": 4, "updates": 0, "skips": 0, "conflicts": 0, "errors": 0,
        "missingTitles": 0,
    }
    assert planned["publishReady"] is True
    assert [row["validationIssues"] for row in planned["rows"]] == [[], [], [], []]
    assert all(lesson["publish"] is False for lesson in MANIFEST["lessons"])


def test_the_batch_covers_the_eleven_originals_with_twelve_exercises() -> None:
    assert len(EXERCISES) == 12
    assert all(exercise["type"] == "grid_drawing" for exercise in EXERCISES.values())
    tagged = {tag for exercise in EXERCISES.values() for tag in exercise["tags"] if tag != "zap"}
    assert tagged == ORIGINALS


def test_each_set_hangs_under_its_star_and_small_star_and_is_named_in_four_languages(migrated) -> None:
    skills = knowledge_base_catalog._skills_data()["skills"]  # noqa: SLF001
    registered = knowledge_base_catalog.practice_sets()
    for lesson in MANIFEST["lessons"]:
        lesson_id, fields = lesson["publicLessonId"], lesson["lesson"]
        star, small_star, part = lesson_id.split("--")
        assert fields["unitId"] == star and part.startswith("zap")
        assert set(fields["titles"]) == set(LOCALES) and fields["titles"]["de"] == fields["title"]
        assert registered[lesson_id] == fields["titles"]
        for exercise in lesson["exercises"]:
            assert exercise["skills"] == [f"{star}--{small_star}"]
            assert skills[exercise["skills"][0]]["unit"] == star
        row = migrated["lessons"][lesson_id]
        assert row["unit_id"] == star and row["titles"] == fields["titles"]


@pytest.mark.parametrize("exercise_id", list(EXERCISES))
def test_every_stored_solution_is_right_and_the_first_is_the_standard_answer(
    migrated, exercise_id: str
) -> None:
    challenge = migrated["challenges"][exercise_id]
    stored = grid_drawing.solutions(challenge)
    assert len(stored) == len(EXERCISES[exercise_id]["solutions"]) >= 1
    for solution in EXERCISES[exercise_id]["solutions"]:
        for locale in LOCALES:
            assert _right(migrated, exercise_id, solution, locale)
    assert challenge["correct_answer"] == grid_drawing.answer_text(stored[0])
    for locale in LOCALES:
        shown = exercise_localization.localized(challenge, locale)
        assert shown["correct_answer"] == challenge["correct_answer"]


# ── the standard answer, worked out again ────────────────────────────────────
#
# None of this uses `grid_drawing`: a point is a pair of Fractions and the maps
# are written out as a sixth-grader is taught them.

Spot = tuple[Fraction, Fraction]


def _spot(x: object, y: object) -> Spot:
    return (Fraction(str(x)), Fraction(str(y)))


def _given(exercise_id: str) -> dict[str, Spot]:
    given = EXERCISES[exercise_id]["grid"].get("given", {})
    return {point["label"]: _spot(point["x"], point["y"]) for point in given.get("points", [])}


def _standard(exercise_id: str) -> dict[str, Any]:
    return EXERCISES[exercise_id]["solutions"][0]


def _drawn(exercise_id: str, solution: dict[str, Any] | None = None) -> dict[str, Spot]:
    solution = _standard(exercise_id) if solution is None else solution
    return {point["label"]: _spot(point["x"], point["y"]) for point in solution.get("points", [])}


def _sides(exercise_id: str, solution: dict[str, Any] | None = None) -> set[frozenset[Spot]]:
    """Every side the solution draws, by where its ends lie."""
    solution = _standard(exercise_id) if solution is None else solution
    where = {**_given(exercise_id), **_drawn(exercise_id, solution)}
    sides = {frozenset((where[a], where[b])) for a, b in solution.get("segments", [])}
    for polygon in solution.get("polygons", []):
        sides |= {
            frozenset((where[polygon[index]], where[polygon[(index + 1) % len(polygon)]]))
            for index in range(len(polygon))
        }
    return sides


def _given_sides(exercise_id: str, *, square: bool) -> set[frozenset[Spot]]:
    given = EXERCISES[exercise_id]["grid"]["given"]
    where = _given(exercise_id)
    sides = {frozenset((where[a], where[b])) for a, b in given.get("segments", [])}
    if square:
        for polygon in given.get("polygons", []):
            sides |= {
                frozenset((where[polygon[index]], where[polygon[(index + 1) % len(polygon)]]))
                for index in range(len(polygon))
            }
    return sides


def _quarter_turn_clockwise(point: Spot, about: Spot) -> Spot:
    right, up = point[0] - about[0], point[1] - about[1]
    return (about[0] + up, about[1] - right)  # what was above is now to the right


def _quarter_turn_anticlockwise(point: Spot, about: Spot) -> Spot:
    right, up = point[0] - about[0], point[1] - about[1]
    return (about[0] - up, about[1] + right)  # what was to the right is now above


def _shoelace(corners: list[Spot]) -> Fraction:
    twice = sum(
        corners[index][0] * corners[(index + 1) % len(corners)][1]
        - corners[(index + 1) % len(corners)][0] * corners[index][1]
        for index in range(len(corners))
    )
    return abs(Fraction(twice)) / 2


_NAMED_POINT = re.compile(r"\$([A-Z])\((\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\)\$")


@pytest.mark.parametrize("exercise_id", [PLOT, PLOT_HALVES, TRIANGLE])
def test_the_points_each_language_names_are_the_points_checked_and_drawn(exercise_id: str) -> None:
    exercise = EXERCISES[exercise_id]
    checked = {
        check["label"]: _spot(check["x"], check["y"])
        for check in exercise["checks"]
        if check["kind"] == "point"
    }
    prompts = {"de": exercise["prompt"], **{loc: exercise["translations"][loc]["prompt"] for loc in ("en", "fr", "it")}}
    for locale, prompt in prompts.items():
        named = {label: _spot(x, y) for label, x, y in _NAMED_POINT.findall(prompt)}
        assert named == checked, locale
    assert _drawn(exercise_id) == checked
    assert exercise["grid"]["labels"] == list(checked)
    [count] = [check for check in exercise["checks"] if check["kind"] == "count"]
    assert count == {"kind": "count", "points": len(checked)}
    grid = exercise["grid"]
    for x, y in checked.values():
        assert grid["xMin"] <= x <= grid["xMax"] and grid["yMin"] <= y <= grid["yMax"]
        assert (x / Fraction(str(grid["step"]))).denominator == 1
        assert (y / Fraction(str(grid["step"]))).denominator == 1


def test_the_half_grid_points_need_the_half_lines_and_the_star_is_one_figure() -> None:
    assert EXERCISES[PLOT_HALVES]["grid"]["step"] == 0.5
    asked = _drawn(PLOT_HALVES)
    assert all(x.denominator == 2 or y.denominator == 2 for x, y in asked.values())
    # The join exercise shows the same eight points: the four given and the four asked for.
    star = _given(JOIN)
    assert star == {**_given(PLOT_HALVES), **asked}
    assert list(star) == list("ABCDEFGH")


def test_the_joined_points_make_a_closed_star_that_does_not_cross_itself() -> None:
    star = _given(JOIN)
    ring = list("ABCDEFGH")
    wanted = {frozenset((star[ring[index]], star[ring[(index + 1) % 8]])) for index in range(8)}
    checked = {
        frozenset((_spot(*check["from"]), _spot(*check["to"])))
        for check in EXERCISES[JOIN]["checks"]
    }
    assert checked == wanted and len(EXERCISES[JOIN]["checks"]) == 8
    for solution in EXERCISES[JOIN]["solutions"]:
        assert _sides(JOIN, solution) == wanted
    # No two sides that are not neighbours meet.
    corners = [star[label] for label in ring]

    def turn(a: Spot, b: Spot, c: Spot) -> Fraction:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    for first in range(8):
        for second in range(first + 2, 8):
            if (second + 1) % 8 == first:
                continue
            a, b = corners[first], corners[(first + 1) % 8]
            c, d = corners[second], corners[(second + 1) % 8]
            assert not (turn(a, b, c) * turn(a, b, d) <= 0 and turn(c, d, a) * turn(c, d, b) <= 0)
    # Four tips: the corners turn left and right in turn.
    turns = [turn(corners[index - 1], corners[index], corners[(index + 1) % 8]) > 0 for index in range(8)]
    assert turns in ([True, False] * 4, [False, True] * 4)


def test_the_triangle_is_the_three_named_points_joined() -> None:
    points = _drawn(TRIANGLE)
    wanted = {frozenset(pair) for pair in (
        (points["R"], points["S"]), (points["S"], points["T"]), (points["T"], points["R"])
    )}
    checked = {
        frozenset((_spot(*check["from"]), _spot(*check["to"])))
        for check in EXERCISES[TRIANGLE]["checks"]
        if check["kind"] == "segment"
    }
    assert checked == wanted
    for solution in EXERCISES[TRIANGLE]["solutions"]:
        assert _sides(TRIANGLE, solution) == wanted
    assert _shoelace(list(points.values())) > 0  # the three points do not lie on one line


@pytest.mark.parametrize(
    ("exercise_id", "shape", "area", "round_it", "asked"),
    [
        (AREA_18, "rectangle", 18, None, "18 cm²"),
        (SQUARE_9, "square", 9, None, "9 cm²"),
        (AREA_10_ROUND_14, "rectangle", 10, 14, "10 cm²"),
        (SQUARE_ROUND_10, "square", None, 10, "10 cm"),
    ],
)
def test_the_rectangles_measure_what_the_task_asks_in_centimetres(
    exercise_id: str, shape: str, area: int | None, round_it: int | None, asked: str
) -> None:
    exercise = EXERCISES[exercise_id]
    # One unit of the grid is 1 cm and its lines are 5 mm apart, as the task says.
    assert exercise["grid"]["step"] == 0.5 and "axes" not in exercise["grid"]
    wanted: dict[str, Any] = {"kind": "polygon", "shape": shape}
    if area is not None:
        wanted["area"] = area
    if round_it is not None:
        wanted["perimeter"] = round_it
    assert exercise["checks"] == [wanted, {"kind": "count", "polygons": 1}]
    prompts = [exercise["prompt"], *(exercise["translations"][loc]["prompt"] for loc in ("en", "fr", "it"))]
    assert all("5 mm" in prompt and asked in prompt for prompt in prompts)
    if area is not None and round_it is not None:
        assert all(f"{round_it} cm" in prompt for prompt in prompts)
    for solution in exercise["solutions"]:
        p, q, r, s = _drawn(exercise_id, solution).values()
        # Drawn along the lines: P and Q level, Q and R upright, and so on round.
        assert p[1] == q[1] and q[0] == r[0] and r[1] == s[1] and s[0] == p[0]
        width, height = q[0] - p[0], r[1] - q[1]
        assert width > 0 and height > 0
        if shape == "square":
            assert width == height
        if area is not None:
            assert width * height == area == _shoelace([p, q, r, s])
        if round_it is not None:
            assert 2 * (width + height) == round_it


def test_area_10_with_perimeter_14_leaves_only_5_by_2() -> None:
    # Length and width in half centimetres: every pair with the area, and the ones with the perimeter too.
    halves = [Fraction(n, 2) for n in range(1, 41)]
    fitting = {(a, b) for a in halves for b in halves if a >= b and a * b == 10 and 2 * (a + b) == 14}
    assert fitting == {(Fraction(5), Fraction(2))}


@pytest.mark.parametrize(
    ("exercise_id", "corner", "turn", "angle", "words"),
    [
        (TURN_RIGHT, "B", _quarter_turn_clockwise, 270,
         ("im Uhrzeigersinn", " clockwise", "sens des aiguilles", "senso orario")),
        (TURN_LEFT, "D", _quarter_turn_anticlockwise, 90,
         ("im Gegenuhrzeigersinn", "anticlockwise", "sens inverse des aiguilles", "senso antiorario")),
    ],
)
def test_the_turned_line_is_where_a_quarter_turn_about_the_corner_puts_it(
    exercise_id: str, corner: str, turn: Any, angle: int, words: tuple[str, ...]
) -> None:
    exercise = EXERCISES[exercise_id]
    given = _given(exercise_id)
    about = given[corner]
    # The checks name the corner the task names, and the sense the task names
    # (`grid_drawing` counts a rotation anticlockwise: 270 is a quarter turn clockwise).
    assert [check["rotate"] for check in exercise["checks"]] == [
        {"center": [int(about[0]), int(about[1])], "angle": angle}
    ] * 3
    assert [check["of"] for check in exercise["checks"]] == [["P", "Q"], ["Q", "R"], ["R", "S"]]
    prompts = [exercise["prompt"], *(exercise["translations"][loc]["prompt"] for loc in ("en", "fr", "it"))]
    for prompt, word in zip(prompts, words, strict=True):
        assert word in prompt and f"${corner}$" in prompt and "90°" in prompt
    image = {f"{label}'": turn(given[label], about) for label in "PQRS"}
    assert _drawn(exercise_id) == image
    assert _sides(exercise_id) == {
        frozenset((image[f"{a}'"], image[f"{b}'"])) for a, b in ("PQ", "QR", "RS")
    }
    # The square turns onto the free field beside it, and the line stays inside it.
    square = [turn(given[label], about) for label in "ABCD"]
    xs, ys = [x for x, _ in square], [y for _, y in square]
    assert all(min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys) for x, y in image.values())
    old = [given[label] for label in "ABCD"]
    assert max(xs) - min(xs) == max(ys) - min(ys) == 5
    assert min(xs) >= max(x for x, _ in old) or min(ys) >= max(y for _, y in old)
    # Turned the other way it also fits on the grid: the grid does not give the sense away.
    other = _quarter_turn_anticlockwise if turn is _quarter_turn_clockwise else _quarter_turn_clockwise
    grid = exercise["grid"]
    for label in "ABCDPQRS":
        x, y = other(given[label], about)
        assert grid["xMin"] <= x <= grid["xMax"] and grid["yMin"] <= y <= grid["yMax"]


def test_the_mirrored_line_lies_as_far_above_the_side_cd_as_the_line_lies_below() -> None:
    exercise = EXERCISES[MIRROR]
    given = _given(MIRROR)
    c, d = given["C"], given["D"]
    assert c[1] == d[1]  # CD is level, so mirroring keeps x and flips the height about it
    assert [check["reflect"] for check in exercise["checks"]] == [
        {"through": [[int(d[0]), int(d[1])], [int(c[0]), int(c[1])]]}
    ] * 3
    image = {f"{label}'": (given[label][0], 2 * c[1] - given[label][1]) for label in "PQRS"}
    assert _drawn(MIRROR) == image
    assert _sides(MIRROR) == {frozenset((image[f"{a}'"], image[f"{b}'"])) for a, b in ("PQ", "QR", "RS")}
    for label in "PQRS":
        assert given[label][1] < c[1] < image[f"{label}'"][1]
    prompts = [exercise["prompt"], *(exercise["translations"][loc]["prompt"] for loc in ("en", "fr", "it"))]
    assert all("$CD$" in prompt for prompt in prompts)


def test_the_completed_figure_is_the_given_line_four_times_about_both_diagonals() -> None:
    exercise = EXERCISES[BOTH_DIAGONALS]
    given = _given(BOTH_DIAGONALS)
    a, b, c, d = (given[label] for label in "ABCD")
    assert (a, b, c, d) == (_spot(1, 1), _spot(7, 1), _spot(7, 7), _spot(1, 7))
    assert exercise["checks"] == [
        {"kind": "symmetric", "through": [[1, 1], [7, 7]]},  # the diagonal AC
        {"kind": "symmetric", "through": [[1, 7], [7, 1]]},  # the diagonal DB
    ]

    def in_ac(point: Spot) -> Spot:  # AC is y = x: right and up change places
        return (point[1], point[0])

    def in_bd(point: Spot) -> Spot:  # BD is x + y = 8
        return (8 - point[1], 8 - point[0])

    line = _given_sides(BOTH_DIAGONALS, square=False)
    assert len(line) == 2
    copies = [
        {frozenset(mirror(point) for point in side) for side in line}
        for mirror in (in_ac, in_bd, lambda point: in_bd(in_ac(point)))
    ]
    wanted = set().union(*copies)
    assert len(wanted) == 6 and not wanted & line  # three more lines, none on the given one
    assert _sides(BOTH_DIAGONALS) == wanted
    # The points drawn are the mirrored ends, each once.
    ends = {point for side in wanted for point in side}
    assert set(_drawn(BOTH_DIAGONALS).values()) == ends and len(_drawn(BOTH_DIAGONALS)) == 9
    # The line keeps clear of both diagonals, so the four copies do not touch.
    for point in (given[label] for label in "EFG"):
        assert point[0] != point[1] and point[0] + point[1] != 8


# ── other ways to draw the same are right ────────────────────────────────────

ALSO_RIGHT: list[tuple[str, dict[str, Any]]] = [
    (PLOT, {"points": _points(("M", 6, 9), ("K", 3, 7), ("L", 8, 2))}),
    (PLOT_HALVES, {"points": _points(("H", 3.5, 6), ("G", 2.5, 11.5), ("F", 6.5, 7.5), ("E", 11.5, 10))}),
    # The star the other way round and from another point, as one polygon or as segments.
    (JOIN, {"polygons": [list("DCBAHGFE")]}),
    (JOIN, {"segments": [list(pair) for pair in ("HA", "HG", "GF", "FE", "ED", "DC", "CB", "BA")]}),
    # The triangle as a polygon from another corner, the other way round.
    (TRIANGLE, {"points": _points(("T", 4, 11), ("S", 10, 5), ("R", 2, 3)), "polygons": [["T", "S", "R"]]}),
    (TRIANGLE, {"points": _points(("R", 2, 3), ("S", 10, 5), ("T", 4, 11)),
                "segments": [["T", "S"], ["R", "T"], ["S", "R"]]}),
    (AREA_18, _box(0.5, 0.5, 3, 6)),  # standing
    (AREA_18, _box(0.5, 2, 9, 2)),
    (AREA_18, _box(3, 2, 4.5, 4)),
    (AREA_18, _box(0, 0, 4, 4.5)),
    (AREA_18, _polygon([(7, 4), (1, 4), (1, 1), (7, 1)])),  # another start, the other way round
    (AREA_18, _polygon([(3, 0), (6, 3), (3, 6), (0, 3)])),  # a square on its corner: 18 cm² too
    (SQUARE_9, _box(6.5, 3.5, 3, 3)),
    (SQUARE_9, _polygon([(4, 4), (4, 1), (1, 1), (1, 4)])),
    (AREA_10_ROUND_14, _box(4.5, 0.5, 2, 5)),  # standing
    (AREA_10_ROUND_14, _polygon([(6, 3), (1, 3), (1, 1), (6, 1)])),
    (SQUARE_ROUND_10, _box(7, 4, 2.5, 2.5)),
    (SQUARE_ROUND_10, _polygon([(2, 0), (3.5, 2), (1.5, 3.5), (0, 1.5)])),  # tilted: every side 2.5 cm
    # The image under other names, from the other end.
    (TURN_RIGHT, _path([(10, 7), (7, 8), (7, 10), (10, 10)])),
    (TURN_LEFT, _path([(10, 8), (9, 10), (7, 9), (7, 7)])),
    (MIRROR, _path([(6, 9), (5, 7), (3, 8), (3, 10)])),
    (BOTH_DIAGONALS, {
        "points": _points(("H", 2, 3), ("I", 3, 4), ("J", 1, 5), ("K", 3, 2), ("L", 4, 3), ("M", 5, 1),
                          ("N", 5, 6), ("O", 4, 5), ("P", 3, 7)),
        "segments": [["I", "H"], ["J", "I"], ["L", "K"], ["M", "L"], ["O", "N"], ["P", "O"]],
    }),
]


@pytest.mark.parametrize(("exercise_id", "drawing"), ALSO_RIGHT)
def test_another_way_to_draw_the_same_is_right(migrated, exercise_id: str, drawing: dict[str, Any]) -> None:
    assert _right(migrated, exercise_id, drawing)


#: What the task asks for with something more beside it. The checks of these
#: exercises say what must be there, not that nothing else is: a helping line
#: is not a mistake.
RIGHT_WITH_MORE: list[tuple[str, dict[str, Any]]] = [
    # The turned square drawn round the turned line (B and C are given corners).
    (TURN_RIGHT, {
        "points": _points(("P'", 10, 10), ("Q'", 7, 10), ("R'", 7, 8), ("S'", 10, 7), ("X", 11, 11), ("Y", 11, 6)),
        "segments": [["P'", "Q'"], ["Q'", "R'"], ["R'", "S'"]],
        "polygons": [["B", "C", "X", "Y"]],
    }),
    # Both diagonals drawn in as helping lines.
    (BOTH_DIAGONALS, {
        **deepcopy(EXERCISES[BOTH_DIAGONALS]["solutions"][0]),
        "segments": [*EXERCISES[BOTH_DIAGONALS]["solutions"][0]["segments"], ["A", "C"], ["B", "D"]],
    }),
    # The star with one more line across it.
    (JOIN, {"polygons": [list("ABCDEFGH")], "segments": [["B", "F"]]}),
]


@pytest.mark.parametrize(("exercise_id", "drawing"), RIGHT_WITH_MORE)
def test_a_helping_line_beside_the_answer_does_not_make_it_wrong(
    migrated, exercise_id: str, drawing: dict[str, Any]
) -> None:
    assert _right(migrated, exercise_id, drawing)


# ── almost right is wrong ────────────────────────────────────────────────────

_SYMMETRIC = EXERCISES[BOTH_DIAGONALS]["solutions"][0]

ALMOST: list[tuple[str, str, dict[str, Any]]] = [
    (PLOT, "x and y of K swapped", {"points": _points(("K", 7, 3), ("L", 8, 2), ("M", 6, 9))}),
    (PLOT, "M one line too low", {"points": _points(("K", 3, 7), ("L", 8, 2), ("M", 6, 8))}),
    (PLOT, "the names of K and L swapped", {"points": _points(("K", 8, 2), ("L", 3, 7), ("M", 6, 9))}),
    (PLOT, "M missing", {"points": _points(("K", 3, 7), ("L", 8, 2))}),
    (PLOT_HALVES, "x and y of E swapped",
     {"points": _points(("E", 10, 11.5), ("F", 6.5, 7.5), ("G", 2.5, 11.5), ("H", 3.5, 6))}),
    (PLOT_HALVES, "F on the whole line instead of the half",
     {"points": _points(("E", 11.5, 10), ("F", 6, 7.5), ("G", 2.5, 11.5), ("H", 3.5, 6))}),
    (PLOT_HALVES, "G half a unit too low",
     {"points": _points(("E", 11.5, 10), ("F", 6.5, 7.5), ("G", 2.5, 11), ("H", 3.5, 6))}),
    (PLOT_HALVES, "H missing", {"points": _points(("E", 11.5, 10), ("F", 6.5, 7.5), ("G", 2.5, 11.5))}),
    (JOIN, "not closed: H is not joined back to A",
     {"segments": [list(pair) for pair in ("AB", "BC", "CD", "DE", "EF", "FG", "GH")]}),
    (JOIN, "A joined to C instead of to B",
     {"segments": [list(pair) for pair in ("AC", "BC", "CD", "DE", "EF", "FG", "GH", "HA")]}),
    (JOIN, "B and C in the wrong order", {"polygons": [list("ACBDEFGH")]}),
    (JOIN, "only the four tips joined", {"polygons": [list("ACEG")]}),
    (TRIANGLE, "the points without the triangle", {"points": _points(("R", 2, 3), ("S", 10, 5), ("T", 4, 11))}),
    (TRIANGLE, "x and y of T swapped",
     {"points": _points(("R", 2, 3), ("S", 10, 5), ("T", 11, 4)), "polygons": [["R", "S", "T"]]}),
    (TRIANGLE, "the side TR missing",
     {"points": _points(("R", 2, 3), ("S", 10, 5), ("T", 4, 11)), "segments": [["R", "S"], ["S", "T"]]}),
    (TRIANGLE, "the right triangle with the names of R and S swapped",
     {"points": _points(("S", 2, 3), ("R", 10, 5), ("T", 4, 11)), "polygons": [["R", "S", "T"]]}),
    (AREA_18, "6 by 3 small squares, which is 3 cm by 1.5 cm", _box(1, 1, 3, 1.5)),
    (AREA_18, "5 cm by 4 cm: 20 cm²", _box(1, 1, 5, 4)),
    (AREA_18, "a parallelogram of 18 cm²", _polygon([(1, 1), (7, 1), (8, 4), (2, 4)])),
    (AREA_18, "one corner half a centimetre off", _polygon([(1, 1), (7, 1), (7, 4), (1, 4.5)])),
    (AREA_18, "the four sides as segments, no rectangle",
     {"points": _points(("P", 1, 1), ("Q", 7, 1), ("R", 7, 4), ("S", 1, 4)),
      "segments": [["P", "Q"], ["Q", "R"], ["R", "S"], ["S", "P"]]}),
    (SQUARE_9, "3 by 3 small squares, which is 2.25 cm²", _box(1, 1, 1.5, 1.5)),
    (SQUARE_9, "a rectangle of 9 cm² that is no square", _box(1, 1, 4.5, 2)),
    (SQUARE_9, "a square with sides of 3.5 cm", _box(1, 1, 3.5, 3.5)),
    (SQUARE_9, "3 cm by 2.5 cm", _box(1, 1, 3, 2.5)),
    (AREA_10_ROUND_14, "10 cm by 1 cm: the area, but 22 cm round", _box(0, 1, 10, 1)),
    (AREA_10_ROUND_14, "4 cm by 3 cm: 14 cm round, but 12 cm²", _box(1, 1, 4, 3)),
    (AREA_10_ROUND_14, "4 cm by 2.5 cm: the area, but 13 cm round", _box(1, 1, 4, 2.5)),
    (AREA_10_ROUND_14, "10 by 4 small squares, which is 5 cm²", _box(1, 1, 5, 1)),
    (SQUARE_ROUND_10, "a rectangle 3 cm by 2 cm: 10 cm round, no square", _box(1, 1, 3, 2)),
    (SQUARE_ROUND_10, "a square with sides of 5 cm: 20 cm round", _box(1, 1, 5, 5)),
    (SQUARE_ROUND_10, "a square with sides of 2 cm: 8 cm round", _box(1, 1, 2, 2)),
    (SQUARE_ROUND_10, "a square with sides of 3 cm: 12 cm round", _box(1, 1, 3, 3)),
    (TURN_RIGHT, "turned anticlockwise", _path([(2, 2), (5, 2), (5, 4), (2, 5)])),
    (TURN_RIGHT, "moved to the right instead of turned", _path([(7, 10), (7, 7), (9, 7), (10, 10)])),
    (TURN_RIGHT, "mirrored in the side BC instead of turned", _path([(10, 10), (10, 7), (8, 7), (7, 10)])),
    (TURN_RIGHT, "S' one line too high", _path([(10, 10), (7, 10), (7, 8), (10, 8)])),
    (TURN_RIGHT, "the last piece of the line missing", _path([(10, 10), (7, 10), (7, 8), (10, 7)], skip=2)),
    (TURN_LEFT, "turned clockwise", _path([(5, 5), (5, 3), (3, 2), (2, 4)])),
    (TURN_LEFT, "moved up instead of turned", _path([(7, 10), (9, 10), (10, 8), (8, 7)])),
    (TURN_LEFT, "mirrored in the side DC instead of turned", _path([(7, 7), (9, 7), (10, 9), (8, 10)])),
    (TURN_LEFT, "R' one line too far left", _path([(7, 7), (7, 9), (8, 10), (10, 8)])),
    (TURN_LEFT, "the middle piece of the line missing", _path([(7, 7), (7, 9), (9, 10), (10, 8)], skip=1)),
    (MIRROR, "moved up instead of mirrored", _path([(3, 7), (3, 9), (5, 10), (6, 8)])),
    (MIRROR, "a half turn about the middle of CD", _path([(6, 10), (6, 8), (4, 7), (3, 9)])),
    (MIRROR, "R' one line too high", _path([(3, 10), (3, 8), (5, 8), (6, 9)])),
    (MIRROR, "the first piece of the line missing", _path([(3, 10), (3, 8), (5, 7), (6, 9)], skip=0)),
    (BOTH_DIAGONALS, "mirrored in the diagonal AC only",
     {"points": _SYMMETRIC["points"][:3], "segments": _SYMMETRIC["segments"][:2]}),
    (BOTH_DIAGONALS, "mirrored in each diagonal once, the fourth line missing",
     {"points": _SYMMETRIC["points"][:6], "segments": _SYMMETRIC["segments"][:4]}),
    (BOTH_DIAGONALS, "the line turned three times, a pinwheel", {
        "points": _points(("E1", 5, 7), ("F1", 4, 5), ("G1", 3, 6), ("E2", 1, 5), ("F2", 3, 4), ("G2", 2, 3),
                          ("E3", 3, 1), ("F3", 4, 3), ("G3", 5, 2)),
        "segments": _SYMMETRIC["segments"],
    }),
    (BOTH_DIAGONALS, "one end of the fourth line a grid point off", {
        "points": [*_SYMMETRIC["points"][:8], {"label": "G3", "x": 2, "y": 2}],
        "segments": _SYMMETRIC["segments"],
    }),
    (BOTH_DIAGONALS, "all nine points, one piece of line not drawn",
     {"points": _SYMMETRIC["points"], "segments": _SYMMETRIC["segments"][:5]}),
]


@pytest.mark.parametrize(("exercise_id", "why", "drawing"), ALMOST, ids=[f"{e[len(PREFIX):]}: {w}" for e, w, _ in ALMOST])
def test_an_almost_right_drawing_is_judged_wrong_not_refused(
    migrated, exercise_id: str, why: str, drawing: dict[str, Any]
) -> None:
    for locale in LOCALES:
        assert _right(migrated, exercise_id, drawing, locale) is False, why


def _entry_issues(exercise: dict[str, Any]) -> list[tuple[str, str]]:
    """What authoring says of one exercise on entry (the check of #594)."""
    [stored] = curriculum_ops_service._exercise_payloads("zap-597", [deepcopy(exercise)])  # noqa: SLF001
    return [
        (item["field"], item["code"])
        for item in curriculum_ops_service._validation_issues({}, [stored], level="draft")  # noqa: SLF001
        if item["field"].startswith("exercises[0]")
    ]


@pytest.mark.parametrize("exercise_id", list(EXERCISES))
def test_the_entry_check_accepts_every_exercise_as_written(exercise_id: str) -> None:
    assert _entry_issues(EXERCISES[exercise_id]) == []


@pytest.mark.parametrize(("exercise_id", "why", "drawing"), ALMOST, ids=[f"{e[len(PREFIX):]}: {w}" for e, w, _ in ALMOST])
def test_the_entry_check_refuses_an_almost_right_drawing_as_the_standard_answer(
    exercise_id: str, why: str, drawing: dict[str, Any]
) -> None:
    exercise = {**EXERCISES[exercise_id], "solutions": [drawing]}
    assert ("exercises[0].solutions[0]", "grid_solution_fails_checks") in _entry_issues(exercise), why


def test_every_exercise_has_at_least_two_almost_right_drawings() -> None:
    counted = {exercise_id: 0 for exercise_id in EXERCISES}
    for exercise_id, _why, _drawing in ALMOST:
        counted[exercise_id] += 1
    assert min(counted.values()) >= 2, counted


def test_the_almost_right_drawings_differ_from_every_solution_by_what_is_drawn() -> None:
    """Guards the list above against a drawing that is wrong for a reason of form
    only: each differs from the solutions in a point or a side."""
    for exercise_id, why, drawing in ALMOST:
        for solution in EXERCISES[exercise_id]["solutions"]:
            same_points = set(_drawn(exercise_id, drawing).items()) == set(_drawn(exercise_id, solution).items())
            same_sides = _sides(exercise_id, drawing) == _sides(exercise_id, solution)
            if exercise_id == AREA_18 and "segments" in why:
                continue  # the same four sides, but not a rectangle drawn as one
            assert not (same_points and same_sides), (exercise_id, why)


# ── what the student is shown ────────────────────────────────────────────────


@pytest.mark.parametrize("exercise_id", list(EXERCISES))
def test_the_grid_figure_passes_the_allowlist_and_is_one_for_every_language(exercise_id: str) -> None:
    figure = grid_drawing.render(EXERCISES[exercise_id])
    assert figure is not None
    assert figure_svg.figure_issues(figure) == []
    assert not figure_svg.has_text(figure)  # numbers and point names only
    assert "figure" not in EXERCISES[exercise_id]
    assert all("figure" not in text for text in EXERCISES[exercise_id]["translations"].values())


@pytest.mark.parametrize("exercise_id", list(EXERCISES))
@pytest.mark.parametrize("locale", LOCALES)
def test_the_preview_shows_the_grid_and_nothing_of_the_answer(migrated, exercise_id: str, locale: str) -> None:
    challenge = migrated["challenges"][exercise_id]
    preview = practice_projection_service.build_challenge_preview(challenge, locale)
    assert preview["type"] == "grid_drawing"
    assert preview["grid"]["given"] == grid_drawing.client_grid(challenge)["given"]
    text = json.dumps(preview, ensure_ascii=False, default=str)
    for leak in ("checks", "solutions", "correct_answer", "correctAnswer", "answerKey", "standardDrawing",
                 "explanation", '"through"', '"center"', challenge["correct_answer"]):
        assert leak not in text, leak
    # Where the asked-for points lie is nowhere in what is shown before the answer.
    shown = {(point["x"], point["y"]) for point in preview["grid"]["given"]["points"]}
    asked = {(float(x), float(y)) for x, y in _drawn(exercise_id).values()}
    assert not asked & {(float(x), float(y)) for x, y in shown}


# ── the four languages ───────────────────────────────────────────────────────

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@pytest.mark.parametrize("exercise_id", list(EXERCISES))
def test_each_language_has_the_task_and_the_way_with_the_same_numbers_and_names(
    migrated, exercise_id: str
) -> None:
    exercise = EXERCISES[exercise_id]
    assert set(exercise["translations"]) == {"en", "fr", "it"}
    texts = {"de": exercise, **exercise["translations"]}
    for field in ("prompt", "explanation"):
        german = texts["de"][field]
        assert "ß" not in german  # Swiss spelling
        for locale in LOCALES:
            text = texts[locale][field]
            assert text.strip() and (locale == "de" or text != german)
            assert sorted(_NUMBER.findall(text)) == sorted(_NUMBER.findall(german)), (locale, field)
            # The same formulas, whatever order the sentence puts them in.
            assert sorted(re.findall(r"\$[^$]*\$", text)) == sorted(re.findall(r"\$[^$]*\$", german)), (locale, field)
            assert text.count("$") % 2 == 0
    challenge = migrated["challenges"][exercise_id]
    for locale in LOCALES:
        shown = exercise_localization.localized(challenge, locale)
        assert shown["prompt"] == texts[locale]["prompt"]
        assert shown["explanation"] == texts[locale]["explanation"]
    assert 2 <= len(exercise["explanation"].split("\n")) <= 4
