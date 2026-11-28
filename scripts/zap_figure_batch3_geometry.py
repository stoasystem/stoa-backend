"""Exact geometry for the ZAP figure tasks of batch 3 (#596).

Everything a key of `scripts/zap_figure_batch3.py` rests on is computed here
with `fractions.Fraction`. A length that is a square root is carried as an
interval of two fractions that certainly holds it (`Interval`), 10^-30 wide, or
of width zero when the root is rational; a comparison counts only when the two
intervals lie apart by the margin asked for. Nothing is decided by a float.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import permutations
from math import isqrt

Point = tuple[Fraction, Fraction]
#: 10^30: a bracketed square root is known to 30 decimal places.
_SCALE = 10**30
#: The rope length to a point no rope reaches.
UNREACHABLE = 10**9


def frac(value: object) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


def point(x: object, y: object) -> Point:
    return (frac(x), frac(y))


@dataclass(frozen=True)
class Interval:
    """A real number known to lie in [lo, hi]."""

    lo: Fraction
    hi: Fraction

    @classmethod
    def exact(cls, value: object) -> Interval:
        number = frac(value)
        return cls(number, number)

    def __add__(self, other: Interval) -> Interval:
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def certainly_at_least(self, other: Interval, margin: Fraction) -> bool:
        return self.lo - other.hi >= margin

    def is_exactly(self, other: Interval) -> bool:
        return self.lo == self.hi == other.lo == other.hi


def sqrt_interval(value: Fraction) -> Interval:
    """The square root of a non-negative fraction, exact when it is rational."""
    if value < 0:
        raise ValueError("no square root of a negative number")
    numerator, denominator = value.numerator, value.denominator
    root_n, root_d = isqrt(numerator), isqrt(denominator)
    if root_n * root_n == numerator and root_d * root_d == denominator:
        return Interval.exact(Fraction(root_n, root_d))
    scaled = isqrt(numerator * _SCALE * _SCALE // denominator)
    return Interval(Fraction(scaled, _SCALE), Fraction(scaled + 1, _SCALE))


def smallest(values: Iterable[Interval]) -> Interval:
    values = list(values)
    return Interval(min(v.lo for v in values), min(v.hi for v in values))


def distance(p: Point, q: Point) -> Interval:
    return sqrt_interval((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


@dataclass(frozen=True)
class Line:
    """The line through two points, as a*x + b*y + c = 0."""

    p: Point
    q: Point

    @property
    def coefficients(self) -> tuple[Fraction, Fraction, Fraction]:
        a = self.q[1] - self.p[1]
        b = self.p[0] - self.q[0]
        return a, b, -(a * self.p[0] + b * self.p[1])

    def side(self, p: Point) -> Fraction:
        a, b, c = self.coefficients
        return a * p[0] + b * p[1] + c

    def distance(self, p: Point) -> Interval:
        a, b, _c = self.coefficients
        return sqrt_interval(self.side(p) ** 2 / (a * a + b * b))


@dataclass(frozen=True)
class Rect:
    """An axis-parallel rectangle."""

    x0: Fraction
    y0: Fraction
    x1: Fraction
    y1: Fraction

    @property
    def corners(self) -> list[Point]:
        return [(self.x0, self.y0), (self.x1, self.y0), (self.x1, self.y1), (self.x0, self.y1)]

    def signed_distance(self, p: Point) -> Interval:
        """How far outside the rectangle the point is; negative inside it."""
        dx = max(self.x0 - p[0], p[0] - self.x1, Fraction(0))
        dy = max(self.y0 - p[1], p[1] - self.y1, Fraction(0))
        if dx or dy:
            return sqrt_interval(dx * dx + dy * dy)
        inside = min(p[0] - self.x0, self.x1 - p[0], p[1] - self.y0, self.y1 - p[1])
        return Interval.exact(-inside)

    def blocks(self, p: Point, q: Point) -> bool:
        """Whether the segment pq passes through the open inside of the rectangle."""
        t_min, t_max = Fraction(0), Fraction(1)
        for start, end, low, high in (
            (p[0], q[0], self.x0, self.x1),
            (p[1], q[1], self.y0, self.y1),
        ):
            step = end - start
            if step == 0:
                if not low < start < high:
                    return False
                continue
            first, second = sorted(((low - start) / step, (high - start) / step))
            t_min, t_max = max(t_min, first), min(t_max, second)
        return t_min < t_max


@dataclass(frozen=True)
class Wall:
    """A straight wall: nothing passes through it, a rope bends round its two ends."""

    a: Point
    b: Point

    @property
    def corners(self) -> list[Point]:
        return [self.a, self.b]

    def signed_distance(self, p: Point) -> Interval:
        ax, ay = self.a
        bx, by = self.b
        length2 = (bx - ax) ** 2 + (by - ay) ** 2
        t = ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / length2
        t = max(Fraction(0), min(Fraction(1), t))
        return distance(p, (ax + t * (bx - ax), ay + t * (by - ay)))

    def blocks(self, p: Point, q: Point) -> bool:
        """Whether pq crosses the wall between its ends (touching an end does not count)."""

        def orient(u: Point, v: Point, w: Point) -> Fraction:
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

        return (
            orient(p, q, self.a) * orient(p, q, self.b) < 0
            and orient(self.a, self.b, p) * orient(self.a, self.b, q) < 0
        )


def rope_length(anchor: Point, obstacle: Rect | Wall, p: Point) -> Interval:
    """The shortest way from the anchor to p that does not pass through the obstacle:
    straight, or bending at the obstacle's corners."""
    ways: list[Interval] = []
    corners = [corner for corner in obstacle.corners if corner != anchor]
    for count in range(len(corners) + 1):
        for bends in permutations(corners, count):
            path = [anchor, *bends, p]
            legs = list(zip(path, path[1:], strict=False))
            if any(obstacle.blocks(u, v) for u, v in legs):
                continue
            total = Interval.exact(0)
            for u, v in legs:
                total = total + distance(u, v)
            ways.append(total)
    # A point inside the obstacle is reached by no way at all.
    return smallest(ways) if ways else Interval.exact(UNREACHABLE)


@dataclass(frozen=True)
class Check:
    """One inequality of a condition at one point: `left` < `right`, `left` > `right`
    or `left` = `right`, as the condition demands."""

    relation: str
    left: Interval
    right: Interval

    def verdict(self, margin: Fraction) -> bool | None:
        """Whether it holds; `None` when the two sides are closer than the margin
        (for an equality: neither exactly equal nor clearly apart)."""
        below = self.right.certainly_at_least(self.left, margin)
        above = self.left.certainly_at_least(self.right, margin)
        if self.relation == "=":
            if self.left.is_exactly(self.right):
                return True
            return False if below or above else None
        if not (below or above):
            return None
        return below if self.relation == "<" else above

    def gap(self) -> Fraction:
        """A certain lower bound of how far the two sides are apart."""
        return max(self.right.lo - self.left.hi, self.left.lo - self.right.hi, Fraction(0))


def verdict(checks: Sequence[Check], margin: Fraction) -> bool | None:
    """Whether a point meets all the inequalities; `None` when one of them is too close to call."""
    verdicts = [check.verdict(margin) for check in checks]
    if any(v is None for v in verdicts):
        return None
    return all(verdicts)
