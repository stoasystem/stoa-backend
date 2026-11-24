"""Drawing on a coordinate grid, judged by what the drawing is (#594).

A `grid_drawing` exercise shows a grid and maybe a figure already drawn on it;
the student puts points on grid points, joins two points with a segment and
goes round points to make a polygon. The drawing is right when it passes every
check the exercise lists. Nothing is compared as drawn: a rectangle started at
another corner or drawn the other way round is the same rectangle.

**Numbers** are exact. Every coordinate lies on the grid, whose step is a
whole or a half unit, so it is a `Fraction` here; there is no tolerance. In a
stored row a number is an `int`, or a `Decimal` where it is not whole
(`stored_number`); to a client it is a JSON number (`client_number`), which a
half is exactly.

**The grid** (`grid`): `{xMin, xMax, yMin, yMax, step, axes, axisLabels,
labels, given}`. The bounds are whole numbers, `step` is `1` or `0.5`, `axes`
draws the axes through 0, `axisLabels` numbers them. `labels` are the point
names the exercise asks for, in order, for the client to offer first. `given`
is what is already drawn: `{points: [{label, x, y}], segments: [[a, b]],
polygons: [[a, b, c, ...]]}`, by point label. The backend draws the grid and
the given figure as the exercise's `figure` (`render`).

**The answer** is a drawing of the same shape as `given`: points with labels
of their own, segments and polygons over the student's points and the given
ones. A point lies on a grid point inside the grid; labels are 1 to 3 letters,
digits or primes, none twice and none a given label's; two points never share
a grid point; a polygon has 3 to 12 different points. At most `MAX_POINTS`
points, `MAX_SEGMENTS` segments and `MAX_POLYGONS` polygons, and not empty.
Anything else is not an answer (`submitted_drawing` raises `ValueError`).

**The checks** (`checks`), all of which must hold:

- `{kind: "point", label, x, y}`: the student's point with this label is at (x, y).
- `{kind: "segment", from: [x, y], to: [x, y]}`: the student drew a segment
  between these two grid points, either way round, or a polygon with this side.
- `{kind: "polygon", shape?, area?, perimeter?}`: one of the student's polygons
  is a `triangle`, `rectangle` or `square` (a square is a rectangle too) and
  has this area and this perimeter. A perimeter is rational only when every
  side is, so a side along a diagonal never matches one.
- `{kind: "image", of: [labels of given points], rotate: {center: [x, y],
  angle: 90 | 180 | 270}}`, or `reflect: {through: [[x, y], [x, y]]}`, or
  `translate: [dx, dy]`: the student drew the image of those given points, as
  a polygon with exactly those corners (three or more), a segment (two) or a
  point (one), in any order. A rotation turns counter-clockwise.
- `{kind: "symmetric", through: [[x, y], [x, y]]}`: everything drawn, given
  and the student's, is its own mirror image in the line through the two
  points: every point and every side.
- `{kind: "count", points?, segments?, polygons?}`: the student drew exactly
  that many.

**The solutions** (`solutions`): one or more drawings the exercise is right
for, kept with it. Authoring refuses an exercise any of whose solutions fails
its own checks. The first is shown once an answer is on record, and is what
`correct_answer` writes out as text (`answer_text`).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
import json
import math
import re
from typing import Any

from stoa.services.curriculum_issues import Issue, IssueCode

#: The exercise type.
TYPE = "grid_drawing"
#: The stored fields of a grid exercise.
GRID_FIELD = "grid"
CHECKS_FIELD = "checks"
SOLUTIONS_FIELD = "solutions"
#: How much one drawing may hold.
MAX_POINTS = 26
MAX_SEGMENTS = 30
MAX_POLYGONS = 6
MAX_POLYGON_CORNERS = 12
MAX_CHECKS = 30
MAX_SOLUTIONS = 5
#: The widest and tallest grid, in units, and how far from 0 a bound may lie.
MAX_SPAN = 30
MAX_BOUND = 50
#: The longest drawing a student may send, serialized.
MAX_ANSWER_BYTES = 4096
STEPS = (Fraction(1), Fraction(1, 2))
SHAPES = frozenset({"triangle", "rectangle", "square"})
ANGLES = frozenset({90, 180, 270})
CHECK_KINDS = frozenset({"point", "segment", "polygon", "image", "symmetric", "count"})

_LABEL = re.compile(r"[A-Za-z0-9'′]{1,3}")
_DRAWING_KEYS = frozenset({"points", "segments", "polygons"})

Point = tuple[Fraction, Fraction]


def is_one(challenge: Mapping[str, Any]) -> bool:
    return challenge.get("type") == TYPE


# ── numbers ──────────────────────────────────────────────────────────────────


def rational(value: object) -> Fraction | None:
    """A number as authored, sent or stored: an int, a finite float, a Decimal, or
    text such as `"2.5"` or `"5/2"`. A bool, anything else or nothing is `None`."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(str(value)) if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return Fraction(value) if value.is_finite() else None
    if isinstance(value, str) and value.strip():
        try:
            return Fraction(value.strip())
        except (ValueError, ZeroDivisionError):
            return None
    return None


def stored_number(value: Fraction) -> int | Decimal | str:
    """A number as the table keeps it: whole as `int`, a finite decimal as
    `Decimal`, and anything else (a third) as the text `"p/q"`."""
    if value.denominator == 1:
        return value.numerator
    denominator = value.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    if denominator == 1:
        return Decimal(value.numerator) / Decimal(value.denominator)
    return f"{value.numerator}/{value.denominator}"


def client_number(value: Fraction) -> int | float:
    """A grid number as JSON gives it to the client; a half is exact as a float."""
    return value.numerator if value.denominator == 1 else float(value)


def _text_number(value: Fraction) -> str:
    """A number as `correct_answer` writes it: `3`, `2.5`, else `1/3`."""
    shown = stored_number(value)
    return f"{shown:f}" if isinstance(shown, Decimal) else str(shown)


def _whole(value: object) -> int | None:
    """A whole number as authored or as read back from the table (a `Decimal`)."""
    number = rational(value)
    if number is None or number.denominator != 1 or isinstance(value, str):
        return None
    return number.numerator


def _point(value: object) -> Point | None:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None
    x, y = rational(value[0]), rational(value[1])
    return None if x is None or y is None else (x, y)


# ── the grid ─────────────────────────────────────────────────────────────────


class Grid:
    """A validated grid: its bounds, its step, and the figure already on it."""

    def __init__(
        self,
        *,
        x_min: int,
        x_max: int,
        y_min: int,
        y_max: int,
        step: Fraction,
        axes: bool,
        axis_labels: bool,
        labels: list[str],
        given: Drawing,
    ) -> None:
        self.x_min, self.x_max, self.y_min, self.y_max = x_min, x_max, y_min, y_max
        self.step = step
        self.axes = axes
        self.axis_labels = axis_labels
        self.labels = labels
        self.given = given

    def holds(self, point: Point) -> bool:
        """Whether a point is a grid point inside the grid."""
        x, y = point
        return (
            self.x_min <= x <= self.x_max
            and self.y_min <= y <= self.y_max
            and (x / self.step).denominator == 1
            and (y / self.step).denominator == 1
        )


def read_grid(raw: object) -> Grid | None:
    """The grid an exercise stores, or `None` when it is not a valid one."""
    if not isinstance(raw, Mapping):
        return None
    bounds = [rational(raw.get(key)) for key in ("xMin", "xMax", "yMin", "yMax")]
    if any(bound is None or bound.denominator != 1 or abs(bound) > MAX_BOUND for bound in bounds):
        return None
    x_min, x_max, y_min, y_max = (int(bound) for bound in bounds if bound is not None)
    if not (0 < x_max - x_min <= MAX_SPAN and 0 < y_max - y_min <= MAX_SPAN):
        return None
    step = rational(raw.get("step", 1))
    if step not in STEPS:
        return None
    labels = raw.get("labels", [])
    if not isinstance(labels, list) or not all(
        isinstance(label, str) and _LABEL.fullmatch(label) for label in labels
    ) or len(set(labels)) != len(labels) or len(labels) > MAX_POINTS:
        return None
    for flag in ("axes", "axisLabels"):
        if not isinstance(raw.get(flag, False), bool):
            return None
    grid = Grid(
        x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max, step=step,
        axes=bool(raw.get("axes", False)), axis_labels=bool(raw.get("axisLabels", False)),
        labels=list(labels), given=Drawing(),
    )
    given = raw.get("given", {})
    if given in (None, {}):
        return grid
    try:
        grid.given = read_drawing(given, grid, allow_empty=True)
    except ValueError:
        return None
    return grid


# ── a drawing ────────────────────────────────────────────────────────────────


class Drawing:
    """Labelled points, segments and polygons; segments and polygons by label."""

    def __init__(
        self,
        points: dict[str, Point] | None = None,
        segments: list[tuple[str, str]] | None = None,
        polygons: list[list[str]] | None = None,
    ) -> None:
        self.points = points or {}
        self.segments = segments or []
        self.polygons = polygons or []

    def stored(self) -> dict[str, Any]:
        """The drawing as a row keeps it and the client reads it."""
        return {
            "points": [
                {"label": label, "x": stored_number(x), "y": stored_number(y)}
                for label, (x, y) in self.points.items()
            ],
            "segments": [[a, b] for a, b in self.segments],
            "polygons": [list(polygon) for polygon in self.polygons],
        }


def read_drawing(
    raw: object, grid: Grid, *, allow_empty: bool = False, given: Drawing | None = None
) -> Drawing:
    """A drawing on `grid`; `ValueError` when it is not one.

    Segments and polygons may also join the `given` figure's points.
    """
    if not isinstance(raw, Mapping) or not set(raw) <= _DRAWING_KEYS:
        raise ValueError("a drawing is an object of points, segments and polygons")
    points_raw = raw.get("points", [])
    segments_raw = raw.get("segments", [])
    polygons_raw = raw.get("polygons", [])
    if not all(isinstance(part, list) for part in (points_raw, segments_raw, polygons_raw)):
        raise ValueError("points, segments and polygons are lists")
    if len(points_raw) > MAX_POINTS or len(segments_raw) > MAX_SEGMENTS or len(polygons_raw) > MAX_POLYGONS:
        raise ValueError("the drawing holds more than a drawing may")
    if not allow_empty and not (points_raw or segments_raw or polygons_raw):
        raise ValueError("the drawing is empty")
    known = dict(given.points) if given else {}
    points: dict[str, Point] = {}
    places: set[Point] = set()
    for item in points_raw:
        if not isinstance(item, Mapping) or set(item) != {"label", "x", "y"}:
            raise ValueError("a point is {label, x, y}")
        label = item["label"]
        if not isinstance(label, str) or not _LABEL.fullmatch(label):
            raise ValueError("a point label is 1 to 3 letters, digits or primes")
        if label in points or label in known:
            raise ValueError("a point label is used twice")
        x, y = _coordinate(item["x"]), _coordinate(item["y"])
        if x is None or y is None or not grid.holds((x, y)):
            raise ValueError("a point lies off the grid")
        if (x, y) in places:
            raise ValueError("two points share a grid point")
        points[label] = (x, y)
        places.add((x, y))
    known.update(points)
    segments: list[tuple[str, str]] = []
    for item in segments_raw:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(label, str) and label in known for label in item)
            or item[0] == item[1]
        ):
            raise ValueError("a segment joins two different points of the drawing")
        if frozenset(item) in {frozenset(segment) for segment in segments}:
            raise ValueError("a segment is drawn twice")
        segments.append((item[0], item[1]))
    polygons: list[list[str]] = []
    for item in polygons_raw:
        if (
            not isinstance(item, list)
            or not 3 <= len(item) <= MAX_POLYGON_CORNERS
            or not all(isinstance(label, str) and label in known for label in item)
            or len(set(item)) != len(item)
        ):
            raise ValueError("a polygon goes round 3 to 12 different points of the drawing")
        polygons.append(list(item))
    return Drawing(points, segments, polygons)


def _coordinate(value: object) -> Fraction | None:
    # A coordinate is sent as a JSON number; text is for authoring only.
    if isinstance(value, str):
        return None
    return rational(value)


def submitted_drawing(raw: object, challenge: Mapping[str, Any]) -> Drawing:
    """The student's drawing on this exercise's grid; `ValueError` when it is not one."""
    grid = read_grid(challenge.get(GRID_FIELD))
    if grid is None:
        raise ValueError("the exercise has no valid grid")
    try:
        size = len(json.dumps(raw, separators=(",", ":"), default=str).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ValueError("the drawing is not JSON") from error
    if size > MAX_ANSWER_BYTES:
        raise ValueError("the drawing exceeds the serialized byte bound")
    return read_drawing(raw, grid, given=grid.given)


# ── geometry ─────────────────────────────────────────────────────────────────


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> Fraction:
    return a[0] * b[1] - a[1] * b[0]


def _area(corners: list[Point]) -> Fraction:
    twice = sum(
        (_cross(corners[index], corners[(index + 1) % len(corners)]) for index in range(len(corners))),
        Fraction(0),
    )
    return abs(twice) / 2


def _sqrt(value: Fraction) -> Fraction | None:
    """The exact square root of a non-negative rational, or `None` when it is irrational."""
    numerator, denominator = math.isqrt(value.numerator), math.isqrt(value.denominator)
    if numerator * numerator == value.numerator and denominator * denominator == value.denominator:
        return Fraction(numerator, denominator)
    return None


def _perimeter(corners: list[Point]) -> Fraction | None:
    total = Fraction(0)
    for index, corner in enumerate(corners):
        side = _sub(corners[(index + 1) % len(corners)], corner)
        length = _sqrt(_dot(side, side))
        if length is None:
            return None
        total += length
    return total


def _is_shape(corners: list[Point], shape: str) -> bool:
    if _area(corners) == 0:
        return False
    if shape == "triangle":
        return len(corners) == 3
    if len(corners) != 4:
        return False
    sides = [_sub(corners[(index + 1) % 4], corners[index]) for index in range(4)]
    if any(_dot(sides[index], sides[(index + 1) % 4]) != 0 for index in range(4)):
        return False
    return shape == "rectangle" or _dot(sides[0], sides[0]) == _dot(sides[1], sides[1])


def _rotate(point: Point, center: Point, angle: int) -> Point:
    dx, dy = _sub(point, center)
    turned = {90: (-dy, dx), 180: (-dx, -dy), 270: (dy, -dx)}[angle]
    return (center[0] + turned[0], center[1] + turned[1])


def _reflect(point: Point, through: tuple[Point, Point]) -> Point:
    a, b = through
    direction = _sub(b, a)
    offset = _sub(point, a)
    along = _dot(offset, direction) / _dot(direction, direction)
    foot = (a[0] + along * direction[0], a[1] + along * direction[1])
    return (2 * foot[0] - point[0], 2 * foot[1] - point[1])


def _edges(corners: list[Point]) -> set[frozenset[Point]]:
    return {frozenset((corners[index], corners[(index + 1) % len(corners)])) for index in range(len(corners))}


class _Placed:
    """A drawing with its labels resolved to where they lie."""

    def __init__(self, drawing: Drawing, given: Drawing) -> None:
        where = {**given.points, **drawing.points}
        self.points = dict(drawing.points)
        self.segments = [frozenset((where[a], where[b])) for a, b in drawing.segments]
        self.polygons = [[where[label] for label in polygon] for polygon in drawing.polygons]
        self.drawing = drawing


# ── checks ───────────────────────────────────────────────────────────────────


def _transform(check: Mapping[str, Any]) -> Any:
    """The map an `image` check names, or `None` when it names none correctly."""
    named = [key for key in ("rotate", "reflect", "translate") if key in check]
    if len(named) != 1:
        return None
    spec = check[named[0]]
    if named[0] == "rotate":
        if not isinstance(spec, Mapping):
            return None
        center = _point(spec.get("center"))
        angle = _whole(spec.get("angle"))
        if center is None or angle not in ANGLES:
            return None
        return lambda point: _rotate(point, center, angle)
    if named[0] == "reflect":
        line = _line(spec.get("through") if isinstance(spec, Mapping) else None)
        return None if line is None else (lambda point: _reflect(point, line))
    shift = _point(spec)
    return None if shift is None else (lambda point: (point[0] + shift[0], point[1] + shift[1]))


def _line(value: object) -> tuple[Point, Point] | None:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return None
    a, b = _point(value[0]), _point(value[1])
    if a is None or b is None or a == b:
        return None
    return (a, b)


def check_issue(check: object, grid: Grid) -> str | None:
    """Why a check is not one this module can run, or `None`; a label it
    names that the given figure lacks is reported as the label."""
    if not isinstance(check, Mapping) or check.get("kind") not in CHECK_KINDS:
        return "kind"
    kind = check["kind"]
    if kind == "point":
        label = check.get("label")
        place = _point([check.get("x"), check.get("y")])
        if not isinstance(label, str) or not _LABEL.fullmatch(label) or place is None:
            return "point"
        return None
    if kind == "segment":
        ends = _line([check.get("from"), check.get("to")])
        return None if ends is not None else "segment"
    if kind == "polygon":
        shape = check.get("shape")
        if shape is not None and shape not in SHAPES:
            return "shape"
        for measure in ("area", "perimeter"):
            if measure in check and rational(check[measure]) is None:
                return measure
        return None
    if kind == "image":
        of = check.get("of")
        if not isinstance(of, list) or not of or len(set(map(str, of))) != len(of):
            return "of"
        missing = [label for label in of if label not in grid.given.points]
        if missing:
            return f"label:{missing[0]}"
        return None if _transform(check) is not None else "transform"
    if kind == "symmetric":
        return None if _line(check.get("through")) is not None else "through"
    counts = [_whole(check.get(name)) for name in ("points", "segments", "polygons") if name in check]
    if not counts or any(count is None or count < 0 for count in counts):
        return "count"
    return None


def _holds(check: Mapping[str, Any], placed: _Placed, grid: Grid) -> bool:
    kind = check["kind"]
    if kind == "point":
        place = _point([check["x"], check["y"]])
        return placed.points.get(check["label"]) == place
    if kind == "segment":
        ends = _line([check["from"], check["to"]])
        if ends is None:
            return False
        wanted = frozenset(ends)
        return wanted in placed.segments or any(wanted in _edges(polygon) for polygon in placed.polygons)
    if kind == "polygon":
        area = rational(check["area"]) if "area" in check else None
        perimeter = rational(check["perimeter"]) if "perimeter" in check else None
        shape = check.get("shape")
        return any(
            _area(corners) > 0
            and (shape is None or _is_shape(corners, shape))
            and (area is None or _area(corners) == area)
            and (perimeter is None or _perimeter(corners) == perimeter)
            for corners in placed.polygons
        )
    if kind == "image":
        transform = _transform(check)
        if transform is None:
            return False
        image = {transform(grid.given.points[label]) for label in check["of"]}
        if len(image) >= 3:
            return any(set(corners) == image and len(corners) == len(image) for corners in placed.polygons)
        if len(image) == 2:
            return frozenset(image) in placed.segments
        return image <= set(placed.points.values())
    if kind == "symmetric":
        line = _line(check["through"])
        if line is None:
            return False
        given = _Placed(grid.given, Drawing())
        points = set(given.points.values()) | set(placed.points.values())
        edges: set[frozenset[Point]] = set(given.segments) | set(placed.segments)
        for corners in [*given.polygons, *placed.polygons]:
            edges |= _edges(corners)
        mirrored_points = {_reflect(point, line) for point in points}
        mirrored_edges = {frozenset(_reflect(point, line) for point in edge) for edge in edges}
        return mirrored_points == points and mirrored_edges == edges
    drawing = placed.drawing
    actual = {"points": len(drawing.points), "segments": len(drawing.segments), "polygons": len(drawing.polygons)}
    return all(_whole(check[name]) == actual[name] for name in actual if name in check)


def judge(drawing: Drawing, challenge: Mapping[str, Any]) -> bool:
    """Whether a drawing passes every check of the exercise."""
    grid = read_grid(challenge.get(GRID_FIELD))
    checks = challenge.get(CHECKS_FIELD)
    if grid is None or not isinstance(checks, list) or not checks:
        return False
    if any(check_issue(check, grid) is not None for check in checks):
        return False
    placed = _Placed(drawing, grid.given)
    return all(_holds(check, placed, grid) for check in checks)


# ── what is shown ────────────────────────────────────────────────────────────


def solutions(challenge: Mapping[str, Any]) -> list[Drawing]:
    """The exercise's solutions that are drawings on its grid, in order."""
    grid = read_grid(challenge.get(GRID_FIELD))
    raw = challenge.get(SOLUTIONS_FIELD)
    if grid is None or not isinstance(raw, list):
        return []
    found: list[Drawing] = []
    for item in raw:
        try:
            found.append(read_drawing(_as_sent(item), grid, given=grid.given))
        except ValueError:
            return []
    return found


def _as_sent(value: object) -> object:
    """A stored drawing with its numbers as a client would send them."""
    if isinstance(value, Mapping):
        return {key: _as_sent(member) for key, member in value.items()}
    if isinstance(value, list):
        return [_as_sent(member) for member in value]
    if isinstance(value, Decimal):
        number = rational(value)
        return client_number(number) if number is not None else value
    return value


def answer_text(drawing: Drawing) -> str:
    """A drawing written out: `A(2|3); B(5|3); AB; ABCD`."""
    parts = [f"{label}({_text_number(x)}|{_text_number(y)})" for label, (x, y) in drawing.points.items()]
    parts += [f"{a}{b}" for a, b in drawing.segments]
    parts += ["".join(polygon) for polygon in drawing.polygons]
    return "; ".join(parts)


def stored_text(stored: Mapping[str, Any]) -> str:
    """A stored drawing (a receipt's answer) written out, as `answer_text` does."""
    points = stored.get("points") if isinstance(stored.get("points"), list) else []
    parts = []
    for point in points:
        if isinstance(point, Mapping):
            x, y = rational(point.get("x")), rational(point.get("y"))
            if x is not None and y is not None:
                parts.append(f"{point.get('label')}({_text_number(x)}|{_text_number(y)})")
    for name in ("segments", "polygons"):
        items = stored.get(name) if isinstance(stored.get(name), list) else []
        parts += ["".join(str(label) for label in item) for item in items if isinstance(item, list)]
    return "; ".join(parts)


def client_drawing(stored: Mapping[str, Any]) -> dict[str, Any]:
    """A stored drawing with JSON numbers, as the client reads it."""
    points = []
    for point in stored.get("points") or []:
        if isinstance(point, Mapping):
            x, y = rational(point.get("x")), rational(point.get("y"))
            if x is not None and y is not None:
                points.append({"label": str(point.get("label")), "x": client_number(x), "y": client_number(y)})
    return {
        "points": points,
        "segments": [[str(label) for label in item] for item in stored.get("segments") or [] if isinstance(item, list)],
        "polygons": [[str(label) for label in item] for item in stored.get("polygons") or [] if isinstance(item, list)],
    }


def client_grid(challenge: Mapping[str, Any]) -> dict[str, Any] | None:
    """The grid as a student sees it before answering: no checks, no solutions."""
    grid = read_grid(challenge.get(GRID_FIELD))
    if grid is None:
        return None
    return {
        "xMin": grid.x_min,
        "xMax": grid.x_max,
        "yMin": grid.y_min,
        "yMax": grid.y_max,
        "step": client_number(grid.step),
        "axes": grid.axes,
        "axisLabels": grid.axis_labels,
        "labels": list(grid.labels),
        "given": client_drawing(grid.given.stored()),
        "limits": {"points": MAX_POINTS, "segments": MAX_SEGMENTS, "polygons": MAX_POLYGONS},
    }


#: Pixels per grid unit and around the grid in a rendered figure.
_UNIT = 24
_MARGIN = 24


def render(challenge: Mapping[str, Any]) -> str | None:
    """The grid and its given figure as an SVG the figure allowlist accepts."""
    grid = read_grid(challenge.get(GRID_FIELD))
    if grid is None:
        return None
    width = (grid.x_max - grid.x_min) * _UNIT + 2 * _MARGIN
    height = (grid.y_max - grid.y_min) * _UNIT + 2 * _MARGIN

    def sx(x: Fraction) -> str:
        return _svg_number((x - grid.x_min) * _UNIT + _MARGIN)

    def sy(y: Fraction) -> str:
        return _svg_number((grid.y_max - y) * _UNIT + _MARGIN)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<g stroke="currentColor" stroke-opacity="0.25" stroke-width="1">',
    ]
    x = Fraction(grid.x_min)
    while x <= grid.x_max:
        parts.append(f'<line x1="{sx(x)}" y1="{sy(Fraction(grid.y_min))}" x2="{sx(x)}" y2="{sy(Fraction(grid.y_max))}"/>')
        x += grid.step
    y = Fraction(grid.y_min)
    while y <= grid.y_max:
        parts.append(f'<line x1="{sx(Fraction(grid.x_min))}" y1="{sy(y)}" x2="{sx(Fraction(grid.x_max))}" y2="{sy(y)}"/>')
        y += grid.step
    parts.append("</g>")
    zero = Fraction(0)
    if grid.axes:
        parts.append('<g stroke="currentColor" stroke-width="1.5">')
        if grid.y_min <= 0 <= grid.y_max:
            parts.append(f'<line x1="{sx(Fraction(grid.x_min))}" y1="{sy(zero)}" x2="{sx(Fraction(grid.x_max))}" y2="{sy(zero)}"/>')
        if grid.x_min <= 0 <= grid.x_max:
            parts.append(f'<line x1="{sx(zero)}" y1="{sy(Fraction(grid.y_min))}" x2="{sx(zero)}" y2="{sy(Fraction(grid.y_max))}"/>')
        parts.append("</g>")
    if grid.axis_labels:
        parts.append('<g fill="currentColor" font-size="10" text-anchor="middle">')
        label_y = zero if grid.y_min <= 0 <= grid.y_max else Fraction(grid.y_min)
        label_x = zero if grid.x_min <= 0 <= grid.x_max else Fraction(grid.x_min)
        for value in range(grid.x_min, grid.x_max + 1):
            parts.append(f'<text x="{sx(Fraction(value))}" y="{_svg_number((grid.y_max - label_y) * _UNIT + _MARGIN + 14)}">{value}</text>')
        for value in range(grid.y_min, grid.y_max + 1):
            if value != label_y:
                parts.append(f'<text x="{_svg_number((label_x - grid.x_min) * _UNIT + _MARGIN - 10)}" y="{_svg_number((grid.y_max - value) * _UNIT + _MARGIN + 4)}">{value}</text>')
        parts.append("</g>")
    given = grid.given
    if given.points:
        parts.append('<g fill="none" stroke="currentColor" stroke-width="2">')
        for polygon in given.polygons:
            corners = " ".join(f"{sx(given.points[label][0])},{sy(given.points[label][1])}" for label in polygon)
            parts.append(f'<polygon points="{corners}"/>')
        for a, b in given.segments:
            (ax, ay), (bx, by) = given.points[a], given.points[b]
            parts.append(f'<line x1="{sx(ax)}" y1="{sy(ay)}" x2="{sx(bx)}" y2="{sy(by)}"/>')
        parts.append("</g>")
        parts.append('<g fill="currentColor" font-size="12">')
        for label, (px, py) in given.points.items():
            parts.append(f'<circle cx="{sx(px)}" cy="{sy(py)}" r="3"/>')
            parts.append(f'<text x="{_svg_number((px - grid.x_min) * _UNIT + _MARGIN + 5)}" y="{_svg_number((grid.y_max - py) * _UNIT + _MARGIN - 5)}">{label}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _svg_number(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else format(float(value), "g")


# ── authoring ────────────────────────────────────────────────────────────────


def normalize(exercise: dict[str, Any]) -> None:
    """Put an authored grid exercise's numbers in stored form (`stored_number`), in place.

    A float is never stored; text the author wrote as a number becomes one
    where it reads as one. Anything else is left for the report to name.
    """
    for field in (GRID_FIELD, CHECKS_FIELD, SOLUTIONS_FIELD):
        if field in exercise:
            exercise[field] = _stored_numbers(exercise[field])


def _stored_numbers(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _stored_numbers(member) for key, member in value.items()}
    if isinstance(value, list | tuple):
        return [_stored_numbers(member) for member in value]
    if isinstance(value, float):
        number = rational(value)
        return stored_number(number) if number is not None else None
    return value


def issues(exercise: Mapping[str, Any]) -> list[tuple[str, Issue]]:
    """What is wrong with a grid exercise: its grid, its checks, its solutions."""
    grid = read_grid(exercise.get(GRID_FIELD))
    found: list[tuple[str, Issue]] = []
    if grid is None:
        return [(GRID_FIELD, Issue.of(IssueCode.GRID_INVALID))]
    if exercise.get("figure") not in (None, ""):
        found.append(("figure", Issue.of(IssueCode.GRID_FIGURE_AUTHORED)))
    checks = exercise.get(CHECKS_FIELD)
    if not isinstance(checks, list) or not checks or len(checks) > MAX_CHECKS:
        found.append((CHECKS_FIELD, Issue.of(IssueCode.GRID_CHECKS_INVALID, max_checks=MAX_CHECKS)))
        checks = []
    runnable = True
    for index, check in enumerate(checks):
        problem = check_issue(check, grid)
        if problem is None:
            continue
        runnable = False
        field = f"{CHECKS_FIELD}[{index}]"
        if problem.startswith("label:"):
            found.append((field, Issue.of(IssueCode.GRID_LABEL_UNKNOWN, label=problem.removeprefix("label:"))))
        else:
            found.append((field, Issue.of(IssueCode.GRID_CHECK_INVALID, part=problem)))
    raw = exercise.get(SOLUTIONS_FIELD)
    if not isinstance(raw, list) or not raw or len(raw) > MAX_SOLUTIONS:
        found.append((SOLUTIONS_FIELD, Issue.of(IssueCode.GRID_SOLUTION_INVALID, max_solutions=MAX_SOLUTIONS)))
        return found
    for index, item in enumerate(raw):
        field = f"{SOLUTIONS_FIELD}[{index}]"
        try:
            drawing = read_drawing(_as_sent(item), grid, given=grid.given)
        except ValueError:
            found.append((field, Issue.of(IssueCode.GRID_SOLUTION_INVALID, max_solutions=MAX_SOLUTIONS)))
            continue
        for check_index, check in enumerate(checks):
            if (
                isinstance(check, Mapping)
                and check.get("kind") == "point"
                and check.get("label") not in drawing.points
            ):
                found.append((f"{CHECKS_FIELD}[{check_index}]", Issue.of(IssueCode.GRID_LABEL_UNKNOWN, label=check.get("label"))))
        if runnable and checks and not judge(drawing, exercise):
            found.append((field, Issue.of(IssueCode.GRID_SOLUTION_FAILS_CHECKS)))
    return list(dict.fromkeys(found))


def stray_issues(exercise: Mapping[str, Any]) -> list[tuple[str, Issue]]:
    """A grid, checks or solutions on an exercise of another type."""
    return [
        (field, Issue.of(IssueCode.GRID_WITHOUT_GRID_DRAWING))
        for field in (GRID_FIELD, CHECKS_FIELD, SOLUTIONS_FIELD)
        if exercise.get(field) not in (None, [], {})
    ]


def first_solution_text(exercise: Mapping[str, Any]) -> str | None:
    """`correct_answer` of a grid exercise: its first solution written out."""
    found = solutions(exercise)
    return answer_text(found[0]) if found else None
