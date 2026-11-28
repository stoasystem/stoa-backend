"""The eleven "which marked points lie in the region" tasks of batch 3 (#596).

Each ZAP1 original asks for a region to be constructed with compass and ruler.
The adaptation draws a new plan on squared paper, marks candidate points and
asks which of them meet every condition. A task here is its plan, its
conditions and its candidates; the key is computed from them (`solve`), never
written down, and a candidate may not lie within `MIN_MARGIN` of a boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from scripts.zap_figure_batch3_geometry import (
    Check,
    Interval,
    Line,
    Point,
    Rect,
    Wall,
    distance,
    point,
    rope_length,
    verdict,
)

#: Every inequality of every condition holds or fails by at least this much, in
#: grid squares, at every candidate: half a square, a clear step on the paper.
MIN_MARGIN = Fraction(1, 2)
#: One grid square in the drawing, and the white border round the paper.
CELL = 28
PAD = 16
#: Two hotspots are at least this far apart (the larger of across and down) in
#: a figure about 360 wide: the client gives each a 44 px target.
MIN_HOTSPOT_GAP = 44

Checks = Callable[[Point], list[Check]]


@dataclass(frozen=True)
class Condition:
    """One demand on a point, named for the verification report."""

    name: str
    checks: Checks


def _exact(value: object) -> Interval:
    return Interval.exact(value)


def nearer_point(a: Point, b: Point, name: str) -> Condition:
    return Condition(name, lambda p: [Check("<", distance(p, a), distance(p, b))])


def within(centre: Point, radius: object, name: str) -> Condition:
    return Condition(name, lambda p: [Check("<", distance(p, centre), _exact(radius))])


def beyond(centre: Point, radius: object, name: str) -> Condition:
    return Condition(name, lambda p: [Check(">", distance(p, centre), _exact(radius))])


def between(centre: Point, inner: object, outer: object, name: str) -> Condition:
    return Condition(
        name,
        lambda p: [
            Check(">", distance(p, centre), _exact(inner)),
            Check("<", distance(p, centre), _exact(outer)),
        ],
    )


def line_beyond(line: Line, gap: object, name: str) -> Condition:
    return Condition(name, lambda p: [Check(">", line.distance(p), _exact(gap))])


def line_exactly(line: Line, gap: object, name: str) -> Condition:
    return Condition(name, lambda p: [Check("=", line.distance(p), _exact(gap))])


def nearer_line(g: Line, h: Line, name: str) -> Condition:
    return Condition(name, lambda p: [Check("<", g.distance(p), h.distance(p))])


def rope(anchor: Point, obstacle: Rect | Wall, length: object, name: str) -> Condition:
    """Reached by a rope of this length that cannot pass through the obstacle. A
    candidate also keeps the margin from the obstacle itself."""
    return Condition(
        name,
        lambda p: [
            Check("<", rope_length(anchor, obstacle, p), _exact(length)),
            Check(">", obstacle.signed_distance(p), _exact(0)),
        ],
    )


def outside(rect: Rect, name: str) -> Condition:
    return Condition(name, lambda p: [Check(">", rect.signed_distance(p), _exact(0))])


@dataclass(frozen=True)
class Candidate:
    name: str
    at: Point
    #: Where its letter stands: a compass direction from the dot.
    label: str = "ne"


@dataclass(frozen=True)
class LocusTask:
    key: str
    original: str
    paper: Paper
    conditions: Sequence[Condition]
    candidates: Sequence[Candidate]
    #: SVG of the plan's fixed parts, drawn by the paper's helpers.
    plan: Sequence[str] = field(default_factory=tuple)

    @property
    def figure(self) -> str:
        return self.paper.svg(self.plan, self.candidates)


@dataclass(frozen=True)
class Solved:
    name: str
    at: Point
    #: Per condition: whether it holds.
    holds: tuple[bool, ...]
    #: The smallest certain gap between the two sides of any inequality, in squares.
    margin: Fraction

    @property
    def inside(self) -> bool:
        return all(self.holds)


def solve(task: LocusTask) -> list[Solved]:
    """Every candidate's verdict per condition. Raises when one is too close to call."""
    solved = []
    for candidate in task.candidates:
        holds = []
        gaps = []
        for condition in task.conditions:
            checks = condition.checks(candidate.at)
            decided = verdict(checks, MIN_MARGIN)
            if decided is None:
                raise ValueError(
                    f"{task.key}: {candidate.name} is within {MIN_MARGIN} of the boundary of "
                    f"'{condition.name}'"
                )
            holds.append(decided)
            gaps.extend(check.gap() for check in checks if check.relation != "=" or check.gap())
        solved.append(Solved(candidate.name, candidate.at, tuple(holds), min(gaps)))
    return solved


def classify(task: LocusTask, p: Point) -> str:
    """One character for the exploring map: `#` in, a digit for the only failing
    condition, `x` for several, `?` too close to call."""
    verdicts = [verdict(condition.checks(p), MIN_MARGIN) for condition in task.conditions]
    if any(v is None for v in verdicts):
        return "?"
    failing = [index for index, v in enumerate(verdicts, start=1) if not v]
    if not failing:
        return "#"
    return str(failing[0]) if len(failing) == 1 else "x"


def explore(task: LocusTask) -> str:
    """The grid points of a task's paper, classified, with its candidates in brackets."""
    width, height = task.paper.width, task.paper.height
    chosen = {candidate.at: candidate.name for candidate in task.candidates}
    rows = [task.key]
    for y in range(height, -1, -1):
        cells = []
        for x in range(width + 1):
            mark = classify(task, point(x, y))
            cells.append(f"[{mark}]" if point(x, y) in chosen else f" {mark} ")
        rows.append(f"{y:2d} " + "".join(cells))
    rows.append("   " + "".join(f" {x % 10} " for x in range(width + 1)))
    return "\n".join(rows)


# ── drawing ──────────────────────────────────────────────────────────────────

_OFFSETS = {
    "n": (0, -9, "middle"), "s": (0, 17, "middle"), "e": (9, 4, "start"), "w": (-9, 4, "end"),
    "ne": (7, -6, "start"), "nw": (-7, -6, "end"), "se": (7, 14, "start"), "sw": (-7, 14, "end"),
}


def _number(value: Fraction | float | int) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


class Paper:
    """Squared paper `width` by `height` squares; grid coordinates, y upwards."""

    def __init__(self, width: int, height: int, *, axes: bool = False) -> None:
        self.width, self.height, self.axes = width, height, axes
        #: Room for the coordinate numbers, left of the paper and under it.
        self.left = PAD + (14 if axes else 0)
        self.below = PAD + (16 if axes else 0)

    def x(self, x: object) -> str:
        return _number(self.left + Fraction(str(x)) * CELL)

    def y(self, y: object) -> str:
        return _number(PAD + (self.height - Fraction(str(y))) * CELL)

    def label(self, name: str, at: Point, where: str, *, bold: bool = False) -> str:
        dx, dy, anchor = _OFFSETS[where]
        weight = ' font-weight="bold"' if bold else ""
        return (
            f'<text x="{_number(float(self.x(at[0])) + dx)}" y="{_number(float(self.y(at[1])) + dy)}" '
            f'font-size="13" font-style="italic"{weight} text-anchor="{anchor}" '
            f'fill="currentColor">{name}</text>'
        )

    def given_point(self, name: str, at: Point, where: str = "ne") -> str:
        return (
            f'<circle id="pt-{name}" cx="{self.x(at[0])}" cy="{self.y(at[1])}" r="3.5" '
            f'fill="currentColor"/>' + self.label(name, at, where, bold=True)
        )

    def line(self, name: str, p: Point, q: Point, label_at: Point, where: str = "ne") -> str:
        return (
            f'<line id="ln-{name}" x1="{self.x(p[0])}" y1="{self.y(p[1])}" x2="{self.x(q[0])}" '
            f'y2="{self.y(q[1])}" stroke="currentColor" stroke-width="2"/>'
            + self.label(name, label_at, where, bold=True)
        )

    def wall(self, name: str, p: Point, q: Point, label_at: Point, where: str = "e") -> str:
        return (
            f'<line id="wa-{name}" x1="{self.x(p[0])}" y1="{self.y(p[1])}" x2="{self.x(q[0])}" '
            f'y2="{self.y(q[1])}" stroke="currentColor" stroke-width="5" stroke-linecap="butt"/>'
            + self.label(name, label_at, where, bold=True)
        )

    def circle(self, name: str, centre: Point, radius: object, label_at: Point, where: str) -> str:
        return (
            f'<circle id="ci-{name}" cx="{self.x(centre[0])}" cy="{self.y(centre[1])}" '
            f'r="{_number(Fraction(str(radius)) * CELL)}" fill="none" stroke="currentColor" '
            f'stroke-width="2"/>' + self.label(name, label_at, where, bold=True)
        )

    def block(self, name: str, rect: Rect, *, dashed: bool = False) -> str:
        """A house (grey, with its letter) or, dashed and without one, a zone marked off."""
        look = (
            'fill="#e9e9e9" stroke="currentColor" stroke-width="1.5" stroke-dasharray="5 3"'
            if dashed
            else 'fill="#bdbdbd" stroke="currentColor" stroke-width="1.5"'
        )
        centre = ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        drawn = (
            f'<rect id="re-{name}" x="{self.x(rect.x0)}" y="{self.y(rect.y1)}" '
            f'width="{_number((rect.x1 - rect.x0) * CELL)}" '
            f'height="{_number((rect.y1 - rect.y0) * CELL)}" {look}/>'
        )
        if dashed:
            return drawn
        return drawn + (
            f'<text x="{self.x(centre[0])}" y="{_number(float(self.y(centre[1])) + 5)}" font-size="13" '
            f'font-style="italic" font-weight="bold" text-anchor="middle" fill="currentColor">'
            f"{name}</text>"
        )

    def candidate(self, letter: str, candidate: Candidate) -> str:
        cx, cy = self.x(candidate.at[0]), self.y(candidate.at[1])
        dx, dy, anchor = _OFFSETS[candidate.label]
        return (
            f'<g data-choice="{letter}"><circle cx="{cx}" cy="{cy}" r="5" fill="#ffffff" '
            f'stroke="currentColor" stroke-width="2"/>'
            f'<text x="{_number(float(cx) + dx)}" y="{_number(float(cy) + dy)}" font-size="13" '
            f'font-style="italic" text-anchor="{anchor}" fill="currentColor">{candidate.name}</text></g>'
        )

    def svg(self, plan: Sequence[str], candidates: Sequence[Candidate]) -> str:
        full_w = self.width * CELL + self.left + PAD
        full_h = self.height * CELL + PAD + self.below
        grid = []
        for column in range(self.width + 1):
            grid.append(
                f'<line x1="{self.x(column)}" y1="{self.y(0)}" x2="{self.x(column)}" '
                f'y2="{self.y(self.height)}"/>'
            )
        for row in range(self.height + 1):
            grid.append(
                f'<line x1="{self.x(0)}" y1="{self.y(row)}" x2="{self.x(self.width)}" '
                f'y2="{self.y(row)}"/>'
            )
        numbers = []
        if self.axes:
            for column in range(0, self.width + 1, 2):
                numbers.append(
                    f'<text x="{self.x(column)}" y="{_number(float(self.y(0)) + 15)}" '
                    f'font-size="11" text-anchor="middle" fill="currentColor">{column}</text>'
                )
            for row in range(0, self.height + 1, 2):
                numbers.append(
                    f'<text x="{_number(float(self.x(0)) - 6)}" y="{_number(float(self.y(row)) + 4)}" '
                    f'font-size="11" text-anchor="end" fill="currentColor">{row}</text>'
                )
        frame = (
            f'<rect id="frame" x="{self.x(0)}" y="{self.y(self.height)}" '
            f'width="{self.width * CELL}" height="{self.height * CELL}" fill="none" '
            f'stroke="currentColor" stroke-width="1"/>'
        )
        marks = "".join(
            self.candidate(chr(ord("A") + index), candidate)
            for index, candidate in enumerate(candidates)
        )
        body = (
            f'<g id="grid" stroke="#c4c4c4" stroke-width="0.6">{"".join(grid)}</g>'
            f'{frame}{"".join(numbers)}{"".join(plan)}{marks}'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {full_w} {full_h}">'
            f"{body}</svg>"
        )


def hotspot_gap(task: LocusTask) -> Fraction:
    """The smallest distance between two candidates, in drawing units (larger of across and down)."""
    points = [candidate.at for candidate in task.candidates]
    return min(
        max(abs(p[0] - q[0]), abs(p[1] - q[1])) * CELL
        for index, p in enumerate(points)
        for q in points[index + 1:]
    )


# ── the eleven tasks ─────────────────────────────────────────────────────────


def _p(x: object, y: object) -> Point:
    return point(x, y)


def _marks(*items: tuple[str, int, int, str]) -> tuple[Candidate, ...]:
    return tuple(Candidate(name, _p(x, y), where) for name, x, y, where in items)


def _half(value: int) -> Fraction:
    return Fraction(value, 2)


def tasks() -> list[LocusTask]:
    """The eleven plans, in the order of the two practice sets."""
    found: list[LocusTask] = []

    # 2023-5a asks for the point of a path at equal distance from two places.
    paper = Paper(12, 9)
    b, h, k = _p(9, 8), _p(1, 6), _p(8, 2)
    found.append(LocusTask(
        "rastplaetze", "2023-5a", paper,
        (
            nearer_point(b, h, "nearer B than H"),
            within(k, _half(9), "at most 4.5 squares from K"),
        ),
        _marks(("P", 1, 1, "nw"), ("Q", 3, 2, "nw"), ("R", 5, 3, "nw"),
               ("S", 7, 4, "nw"), ("T", 9, 5, "nw"), ("U", 11, 6, "nw")),
        (
            paper.line("w", _p(0, _half(1)), _p(12, _half(13)), _p(2, _half(3)), "se"),
            paper.given_point("B", b, "e"),
            paper.given_point("H", h, "n"),
            paper.given_point("K", k, "e"),
        ),
    ))

    # 2023-5b: a dog on a leash, a house in the way.
    paper = Paper(13, 9)
    house, a = Rect(Fraction(5), Fraction(3), Fraction(9), Fraction(6)), _p(2, 7)
    found.append(LocusTask(
        "kabel", "2023-5b", paper,
        (rope(a, house, 9, "reached by 9 squares of cable from A round the house"),),
        _marks(("P", 1, 3, "ne"), ("Q", 6, 1, "ne"), ("R", 10, 1, "ne"), ("S", 10, 3, "ne"),
               ("T", 10, 5, "ne"), ("U", 8, 8, "ne"), ("V", 12, 8, "nw"), ("W", 12, 6, "nw")),
        (paper.block("H", house), paper.given_point("A", a, "nw")),
    ))

    # 2020-9: three conditions on points given by their coordinates.
    paper = Paper(12, 10, axes=True)
    a, b, c = _p(3, 2), _p(9, 2), _p(5, 7)
    found.append(LocusTask(
        "koordinaten", "2020-9", paper,
        (
            nearer_point(b, a, "nearer B than A"),
            within(c, 5, "at most 5 from C"),
            beyond(b, 3, "at least half of AB (3) from B"),
        ),
        _marks(("P", 9, 9, "ne"), ("Q", 4, 6, "ne"), ("R", 11, 7, "ne"), ("S", 8, 4, "ne"),
               ("T", 7, 7, "ne"), ("U", 5, 3, "ne"), ("V", 11, 9, "ne"), ("W", 9, 6, "ne")),
        (
            paper.given_point("A", a, "sw"),
            paper.given_point("B", b, "se"),
            paper.given_point("C", c, "nw"),
        ),
    ))

    # 2010-9: inside a circle and nearer one of two crossing lines.
    paper = Paper(12, 10)
    g = Line(_p(0, 2), _p(12, 2))
    h = Line(_p(2, 2), _p(8, 10))
    m = _p(7, 2)
    found.append(LocusTask(
        "kreis-und-geraden", "2010-9", paper,
        (
            within(m, 5, "less than 5 squares from M"),
            nearer_line(h, g, "nearer h than g"),
        ),
        _marks(("P", 4, 4, "se"), ("Q", 6, 5, "se"), ("R", 8, 6, "se"), ("S", 10, 5, "ne"),
               ("T", 9, 3, "ne"), ("U", 4, 8, "nw"), ("V", 10, 8, "ne"), ("W", 1, 6, "ne")),
        (
            paper.line("g", g.p, g.q, _p(11, 2), "s"),
            paper.line("h", _p(_half(1), 0), _p(8, 10), _p(7, _half(17)), "w"),
            paper.given_point("M", m, "s"),
        ),
    ))

    # 2014-9: a goat on a rope, fences in the way.
    paper = Paper(12, 9)
    wall, a = Wall(_p(7, 2), _p(7, 7)), _p(3, 4)
    found.append(LocusTask(
        "pony", "2014-9", paper,
        (rope(a, wall, 7, "reached by 7 squares of rope from A round the wall"),),
        _marks(("P", 8, 7, "ne"), ("Q", 9, 5, "ne"), ("R", 9, 2, "ne"), ("S", 11, 3, "ne"),
               ("T", 5, 8, "ne"), ("U", 10, 8, "ne"), ("V", 1, 2, "ne"), ("W", 11, 1, "ne")),
        (paper.wall("m", wall.a, wall.b, _p(7, _half(9)), "w"), paper.given_point("A", a, "nw")),
    ))

    # 2025-7: a map with a road, a fireplace and two bathing places.
    paper = Paper(12, 9)
    brook = Line(_p(0, 1), _p(12, 1))
    f, a, b = _p(6, 5), _p(2, 8), _p(10, 6)
    found.append(LocusTask(
        "zeltplatz", "2025-7", paper,
        (
            line_beyond(brook, _half(5), "at least 2.5 squares from b"),
            within(f, 4, "at most 4 squares from F"),
            nearer_point(a, b, "nearer A than B"),
        ),
        _marks(("P", 4, 7, "ne"), ("Q", 3, 5, "nw"), ("R", 8, 6, "ne"), ("S", 7, 4, "se"),
               ("T", 4, 3, "se"), ("U", 1, 6, "ne"), ("V", 11, 4, "ne"), ("W", 7, 8, "ne")),
        (
            paper.line("b", brook.p, brook.q, _p(11, 1), "s"),
            paper.given_point("F", f, "ne"),
            paper.given_point("A", a, "nw"),
            paper.given_point("B", b, "ne"),
        ),
    ))

    # 2018-9: near a circle line, away from a line, nearer one of two points.
    paper = Paper(13, 10)
    g = Line(_p(1, 0), _p(1, 10))
    m, a, b = _p(6, 5), _p(10, 9), _p(4, 1)
    found.append(LocusTask(
        "kreislinie", "2018-9", paper,
        (
            between(m, _half(3), _half(9), "at most 1.5 squares from the circle line k"),
            line_beyond(g, _half(7), "at least 3.5 squares from g"),
            nearer_point(a, b, "nearer A than B"),
        ),
        _marks(("P", 6, 8, "n"), ("Q", 8, 6, "ne"), ("R", 10, 5, "ne"), ("S", 8, 3, "se"),
               ("T", 6, 2, "s"), ("U", 4, 8, "nw"), ("V", 12, 7, "nw"), ("W", 3, 5, "w")),
        (
            paper.circle("k", m, 3, _p(4, 3), "sw"),
            paper.line("g", g.p, g.q, _p(1, 9), "e"),
            paper.given_point("M", m, "s"),
            paper.given_point("A", a, "ne"),
            paper.given_point("B", b, "sw"),
        ),
    ))

    # 2008-9: nearer one of two points and nearer one of two crossing lines.
    paper = Paper(12, 9)
    g = Line(_p(0, 2), _p(12, 2))
    h = Line(_p(3, 0), _p(9, 8))
    a, b = _p(3, 7), _p(9, 5)
    found.append(LocusTask(
        "zwei-geraden", "2008-9", paper,
        (
            nearer_point(a, b, "nearer A than B"),
            nearer_line(g, h, "nearer g than h"),
        ),
        _marks(("P", 1, 6, "ne"), ("Q", 1, 4, "ne"), ("R", 3, 3, "nw"), ("S", 5, 8, "ne"),
               ("T", 5, 5, "nw"), ("U", 10, 3, "ne"), ("V", 8, 1, "se"), ("W", 7, 7, "nw")),
        (
            paper.line("g", g.p, g.q, _p(11, 2), "n"),
            paper.line("h", h.p, _p(Fraction(39, 4), 9), _p(9, 8), "e"),
            paper.given_point("A", a, "nw"),
            paper.given_point("B", b, "e"),
        ),
    ))

    # 2011-9: a treasure at a distance from a point, nearer one of two points,
    # exactly so far from a path.
    paper = Paper(12, 9)
    s = Line(_p(0, 4), _p(12, 4))
    z, a, b = _p(6, 3), _p(3, 8), _p(10, 3)
    found.append(LocusTask(
        "schatz", "2011-9", paper,
        (
            line_exactly(s, 2, "exactly 2 squares from s"),
            between(z, _half(5), _half(11), "between 2.5 and 5.5 squares from Z"),
            nearer_point(a, b, "nearer A than B"),
        ),
        _marks(("P", 2, 6, "sw"), ("Q", 4, 6, "se"), ("R", 6, 6, "ne"), ("S", 8, 6, "ne"),
               ("T", 6, 8, "ne"), ("U", 2, 2, "ne"), ("V", 10, 2, "se"), ("W", 5, 2, "sw")),
        (
            paper.line("s", s.p, s.q, _p(11, 4), "n"),
            paper.given_point("Z", z, "se"),
            paper.given_point("A", a, "nw"),
            paper.given_point("B", b, "ne"),
        ),
    ))

    # 2009-8: nearer the station than the school, away from the track.
    paper = Paper(12, 9)
    t = Line(_p(0, 0), _p(12, 9))
    a, b = _p(9, 2), _p(3, 3)
    found.append(LocusTask(
        "tram", "2009-8", paper,
        (
            line_beyond(t, 2, "more than 2 squares from t"),
            nearer_point(a, b, "nearer A than B"),
        ),
        _marks(("P", 11, 4, "ne"), ("Q", 7, 1, "sw"), ("R", 9, 5, "se"), ("S", 11, 7, "se"),
               ("T", 3, 7, "ne"), ("U", 1, 5, "ne"), ("V", 5, 3, "se"), ("W", 11, 1, "ne")),
        (
            paper.line("t", t.p, t.q, _p(7, Fraction(21, 4)), "nw"),
            paper.given_point("A", a, "ne"),
            paper.given_point("B", b, "nw"),
        ),
    ))

    # 2013-9: two anglers on the shore, a bathing zone, a strip along the shore.
    paper = Paper(12, 9)
    shore = Line(_p(0, 1), _p(12, 1))
    zone = Rect(Fraction(4), Fraction(4), Fraction(6), Fraction(6))
    m, n = _p(5, 1), _p(11, 1)
    found.append(LocusTask(
        "angeln", "2013-9", paper,
        (
            within(m, 6, "at most 6 squares from M"),
            line_beyond(shore, _half(5), "at least 2.5 squares from the shore u"),
            outside(zone, "outside the bathing zone"),
            nearer_point(m, n, "nearer M than N"),
        ),
        _marks(("P", 1, 4, "ne"), ("Q", 3, 6, "ne"), ("R", 5, 5, "ne"), ("S", 7, 5, "ne"),
               ("T", 9, 4, "ne"), ("U", 3, 8, "ne"), ("V", 7, 3, "ne"), ("W", 11, 6, "ne")),
        (
            paper.block("zone", zone, dashed=True),
            paper.line("u", shore.p, shore.q, _p(1, 1), "s"),
            paper.given_point("M", m, "s"),
            paper.given_point("N", n, "s"),
        ),
    ))
    return found

