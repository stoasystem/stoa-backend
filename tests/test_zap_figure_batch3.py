"""ZAP figure tasks, batch 3 (#596): the manifest as it will be migrated.

`fixtures/zap_figure_batch3_596.json` is built by `scripts/zap_figure_batch3.py`,
which computes every key with exact arithmetic from the description the figure
is drawn from. This file takes the finished manifest and nothing else:

- every key is worked out a second time from the figure as the student sees it
  (the positions of the drawn points, lines and faces) and from what the German
  question asks, by another way than the builder's: distances in floats, rope
  lengths by a shortest-path search on a fine lattice, nets by zipping their
  outline shut, shapes by trying every cut;
- the manifest goes through a real migration into a table double - dry run,
  apply, review, publish - and each exercise is answered there in four languages.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import heapq
from itertools import combinations
import json
import math
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

import pytest

from fakes.dynamodb import FakeTable
from scripts import seed_practice, zap_figure_batch3
from stoa.db import table as db_table
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.services import (
    answer_recording,
    curriculum_analytics_service,
    curriculum_migration_service,
    curriculum_ops_service,
    figure_svg,
    multi_select,
    practice_projection_service,
)

MANIFEST_PATH = Path(__file__).parent / "fixtures" / "zap_figure_batch3_596.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
EXERCISES: dict[str, dict[str, Any]] = {
    exercise["exerciseId"]: exercise for lesson in MANIFEST["lessons"] for exercise in lesson["exercises"]
}
LOCALES = ("de", "en", "fr", "it")
#: The seventeen originals of the issue.
ORIGINALS = {
    "2026-5", "2009-9", "2023-6b", "2023-6c", "2017-9a", "2017-9b",
    "2023-5a", "2023-5b", "2020-9", "2010-9", "2014-9", "2025-7", "2018-9", "2008-9", "2011-9",
    "2009-8", "2013-9",
}
#: A candidate of a locus task keeps at least this far from every boundary, in grid squares.
MARGIN = 0.5
SVG = "{http://www.w3.org/2000/svg}"
OPERATOR = {
    "sub": "migration-operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
    },
}

Pt = tuple[float, float]


def _id(original: str, version: int = 1) -> str:
    return f"kb-zap-stoa-zap1-{original}-v{version}"


def _key(exercise_id: str) -> set[str]:
    """The stored key, as the options' names without their dollars."""
    exercise = EXERCISES[exercise_id]
    return {exercise["options"][index].strip("$") for index in exercise["correctOptions"]}


# ── reading a figure ─────────────────────────────────────────────────────────


class Drawing:
    """A figure of the manifest, parsed: its parts by `id`, its hotspots in order."""

    def __init__(self, exercise_id: str) -> None:
        self.exercise = EXERCISES[exercise_id]
        self.root = ET.fromstring(self.exercise["figure"])
        self.by_id = {element.attrib["id"]: element for element in self.root.iter() if "id" in element.attrib}
        self.hotspots = [element for element in self.root.iter() if "data-choice" in element.attrib]

    def option(self, hotspot: ET.Element) -> str:
        index = ord(hotspot.attrib["data-choice"]) - ord("A")
        return self.exercise["options"][index].strip("$")

    def centre(self, element: ET.Element) -> Pt:
        circle = element if element.tag == f"{SVG}circle" else element.find(f"{SVG}circle")
        assert circle is not None
        return (float(circle.attrib["cx"]), float(circle.attrib["cy"]))

    def ends(self, name: str) -> tuple[Pt, Pt]:
        line = self.by_id[name]
        return (
            (float(line.attrib["x1"]), float(line.attrib["y1"])),
            (float(line.attrib["x2"]), float(line.attrib["y2"])),
        )

    def polygons(self, prefix: str) -> dict[str, list[Pt]]:
        found = {}
        for name, element in self.by_id.items():
            if name.startswith(prefix):
                pairs = [pair.split(",") for pair in element.attrib["points"].split()]
                found[name[len(prefix):]] = [(float(x), float(y)) for x, y in pairs]
        return found


class Plan(Drawing):
    """A locus task's squared paper: everything in grid squares, y upwards."""

    def __init__(self, exercise_id: str) -> None:
        super().__init__(exercise_id)
        frame = self.by_id["frame"]
        columns = sorted({float(line.attrib["x1"]) for line in self.by_id["grid"] if line.attrib["x1"] == line.attrib["x2"]})
        self.cell = columns[1] - columns[0]
        self.left = float(frame.attrib["x"])
        self.bottom = float(frame.attrib["y"]) + float(frame.attrib["height"])
        self.width = round(float(frame.attrib["width"]) / self.cell)
        self.height = round(float(frame.attrib["height"]) / self.cell)

    def grid(self, at: Pt) -> Pt:
        return ((at[0] - self.left) / self.cell, (self.bottom - at[1]) / self.cell)

    def point(self, name: str) -> Pt:
        return self.grid(self.centre(self.by_id[f"pt-{name}"]))

    def line(self, name: str, kind: str = "ln") -> tuple[Pt, Pt]:
        a, b = self.ends(f"{kind}-{name}")
        return (self.grid(a), self.grid(b))

    def circle(self, name: str) -> tuple[Pt, float]:
        element = self.by_id[f"ci-{name}"]
        return (self.grid(self.centre(element)), float(element.attrib["r"]) / self.cell)

    def rect(self, name: str) -> tuple[float, float, float, float]:
        """x0, y0, x1, y1 in grid squares."""
        element = self.by_id[f"re-{name}"]
        x0, top = self.grid((float(element.attrib["x"]), float(element.attrib["y"])))
        return (x0, top - float(element.attrib["height"]) / self.cell, x0 + float(element.attrib["width"]) / self.cell, top)

    def candidates(self) -> dict[str, Pt]:
        return {self.option(hotspot): self.grid(self.centre(hotspot)) for hotspot in self.hotspots}


def _dist(p: Pt, q: Pt) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _to_line(p: Pt, line: tuple[Pt, Pt]) -> float:
    (ax, ay), (bx, by) = line
    return abs((bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)) / math.hypot(bx - ax, by - ay)


Demand = tuple[float, str, float]


def _decide(demands: list[Demand]) -> bool:
    """Whether all demands (left, `<` / `>` / `=`, right) hold. A demand within the
    margin of its boundary fails the test: such a point could not be judged."""
    met = True
    for left, relation, right in demands:
        if relation == "=":
            exact = abs(left - right) < 1e-9
            assert exact or abs(left - right) >= MARGIN - 1e-9, (left, relation, right)
            met = met and exact
            continue
        assert abs(left - right) >= MARGIN - 1e-9, (left, relation, right)
        met = met and (left < right if relation == "<" else left > right)
    return met


def _rope_reach(plan: Plan, anchor: Pt, blocked: Callable[[Pt, Pt], bool], inside: Callable[[Pt], bool]) -> Callable[[Pt], float]:
    """The length of the shortest way from the anchor that crosses no obstacle, found
    by Dijkstra on a lattice of quarter squares with steps in 32 directions (at
    most about one per cent longer than the true way)."""
    step = 0.25
    moves = [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if math.gcd(dx, dy) == 1]
    start = (round(anchor[0] / step), round(anchor[1] / step))
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        length, node = heapq.heappop(queue)
        if length > best[node]:
            continue
        here = (node[0] * step, node[1] * step)
        for dx, dy in moves:
            nxt = (node[0] + dx, node[1] + dy)
            there = (nxt[0] * step, nxt[1] * step)
            if not (0 <= there[0] <= plan.width and 0 <= there[1] <= plan.height) or inside(there):
                continue
            if blocked(here, there):
                continue
            reached = length + _dist(here, there)
            if reached < best.get(nxt, math.inf):
                best[nxt] = reached
                heapq.heappush(queue, (reached, nxt))
    return lambda p: best.get((round(p[0] / step), round(p[1] / step)), math.inf)


def _locus_rules() -> dict[str, Callable[[Plan], Callable[[Pt], list[Demand]]]]:
    """What each German question demands of a point, restated from its text; lengths
    in grid squares (the question gives the width of a square where it uses metres)."""

    def rastplaetze(plan: Plan) -> Callable[[Pt], list[Demand]]:
        b, h, k = plan.point("B"), plan.point("H"), plan.point("K")
        # nearer the castle than the harbour; at most 450 m from the church, 100 m a square
        return lambda p: [(_dist(p, b), "<", _dist(p, h)), (_dist(p, k), "<", 4.5)]

    def zwei_geraden(plan: Plan) -> Callable[[Pt], list[Demand]]:
        a, b, g, h = plan.point("A"), plan.point("B"), plan.line("g"), plan.line("h")
        return lambda p: [(_dist(p, a), "<", _dist(p, b)), (_to_line(p, g), "<", _to_line(p, h))]

    def kreis_und_geraden(plan: Plan) -> Callable[[Pt], list[Demand]]:
        m, g, h = plan.point("M"), plan.line("g"), plan.line("h")
        return lambda p: [(_dist(p, m), "<", 5), (_to_line(p, h), "<", _to_line(p, g))]

    def koordinaten(plan: Plan) -> Callable[[Pt], list[Demand]]:
        a, b, c = plan.point("A"), plan.point("B"), plan.point("C")
        # The question names the points by their coordinates.
        assert [*a, *b, *c] == pytest.approx([3, 2, 9, 2, 5, 7])
        return lambda p: [(_dist(p, b), "<", _dist(p, a)), (_dist(p, c), "<", 5), (_dist(p, b), ">", _dist(a, b) / 2)]

    def zeltplatz(plan: Plan) -> Callable[[Pt], list[Demand]]:
        brook, f, a, b = plan.line("b"), plan.point("F"), plan.point("A"), plan.point("B")
        # 10 m a square: at least 25 m from the brook, at most 40 m from the fireplace
        return lambda p: [(_to_line(p, brook), ">", 2.5), (_dist(p, f), "<", 4), (_dist(p, a), "<", _dist(p, b))]

    def tram(plan: Plan) -> Callable[[Pt], list[Demand]]:
        t, a, b = plan.line("t"), plan.point("A"), plan.point("B")
        # 100 m a square: more than 200 m from the tram line; nearer the school A than the station B
        return lambda p: [(_to_line(p, t), ">", 2), (_dist(p, a), "<", _dist(p, b))]

    def kreislinie(plan: Plan) -> Callable[[Pt], list[Demand]]:
        (centre, radius), g, a, b = plan.circle("k"), plan.line("g"), plan.point("A"), plan.point("B")
        assert centre == pytest.approx(plan.point("M"))
        return lambda p: [
            (abs(_dist(p, centre) - radius), "<", 1.5),
            (_to_line(p, g), ">", 3.5),
            (_dist(p, a), "<", _dist(p, b)),
        ]

    def schatz(plan: Plan) -> Callable[[Pt], list[Demand]]:
        s, z, a, b = plan.line("s"), plan.point("Z"), plan.point("A"), plan.point("B")
        # 10 m a square: exactly 20 m from the path, 25 m to 55 m from the tower
        return lambda p: [
            (_to_line(p, s), "=", 2),
            (_dist(p, z), ">", 2.5),
            (_dist(p, z), "<", 5.5),
            (_dist(p, a), "<", _dist(p, b)),
        ]

    def angeln(plan: Plan) -> Callable[[Pt], list[Demand]]:
        u, m, n = plan.line("u"), plan.point("M"), plan.point("N")
        x0, y0, x1, y1 = plan.rect("zone")

        def out_of_zone(p: Pt) -> float:
            """How far outside the zone; negative inside it."""
            dx, dy = max(x0 - p[0], p[0] - x1, 0), max(y0 - p[1], p[1] - y1, 0)
            if dx or dy:
                return math.hypot(dx, dy)
            return -min(p[0] - x0, x1 - p[0], p[1] - y0, y1 - p[1])

        return lambda p: [
            (_dist(p, m), "<", 6),
            (_to_line(p, u), ">", 2.5),
            (out_of_zone(p), ">", 0),
            (_dist(p, m), "<", _dist(p, n)),
        ]

    def kabel(plan: Plan) -> Callable[[Pt], list[Demand]]:
        x0, y0, x1, y1 = plan.rect("H")

        def inside(p: Pt) -> bool:
            return x0 < p[0] < x1 and y0 < p[1] < y1

        def blocked(p: Pt, q: Pt) -> bool:
            return any(inside((p[0] + (q[0] - p[0]) * t / 8, p[1] + (q[1] - p[1]) * t / 8)) for t in range(1, 8))

        reach = _rope_reach(plan, plan.point("A"), blocked, inside)
        return lambda p: [(reach(p), "<", 9)]  # 9 m of cable, 1 m a square

    def pony(plan: Plan) -> Callable[[Pt], list[Demand]]:
        (ax, ay), (bx, by) = plan.line("m", "wa")
        assert ax == pytest.approx(bx)  # the wall is drawn upright
        low, high = sorted((ay, by))

        def inside(p: Pt) -> bool:
            # On the wall, but not at an end: the rope bends round the ends.
            return abs(p[0] - ax) < 1e-9 and low < p[1] < high

        def blocked(p: Pt, q: Pt) -> bool:
            if (p[0] - ax) * (q[0] - ax) >= 0:
                return False
            crossing = p[1] + (q[1] - p[1]) * (ax - p[0]) / (q[0] - p[0])
            return low < crossing < high

        reach = _rope_reach(plan, plan.point("A"), blocked, inside)
        return lambda p: [(reach(p), "<", 7)]  # 7 m of rope, 1 m a square

    return {
        _id("2023-5a"): rastplaetze, _id("2008-9"): zwei_geraden, _id("2010-9"): kreis_und_geraden,
        _id("2020-9"): koordinaten, _id("2025-7"): zeltplatz, _id("2009-8"): tram,
        _id("2018-9"): kreislinie, _id("2011-9"): schatz, _id("2013-9"): angeln,
        _id("2023-5b"): kabel, _id("2014-9"): pony,
    }


LOCUS_RULES = _locus_rules()
#: The two rope tasks allow for the lattice search running up to one per cent long.
ROPE_TASKS = {_id("2023-5b"), _id("2014-9")}


@pytest.mark.parametrize("exercise_id", sorted(LOCUS_RULES))
def test_a_locus_key_is_what_the_drawn_plan_and_the_question_give(exercise_id: str) -> None:
    plan = Plan(exercise_id)
    demands = LOCUS_RULES[exercise_id](plan)
    right = set()
    for name, at in plan.candidates().items():
        # Candidates stand on grid points, where a student can count squares.
        assert at == pytest.approx((round(at[0]), round(at[1])), abs=1e-6)
        found = demands(at)
        if exercise_id in ROPE_TASKS:
            # A way found is the true one or up to 1 % longer. Shorter than the rope by
            # 0.4: reached, and clear of the boundary. Longer by the margin: the true
            # way is longer than the rope too, since 1 % of it is far less than that.
            (length, _relation, limit), = found
            assert length < limit - 0.4 or length > limit + MARGIN, (name, length)
            met = length < limit
        else:
            met = _decide(found)
        if met:
            right.add(name)
    assert right == _key(exercise_id)


def test_the_eleven_locus_tasks_mark_six_to_ten_candidates() -> None:
    assert len(LOCUS_RULES) == 11
    for exercise_id in LOCUS_RULES:
        assert 6 <= len(EXERCISES[exercise_id]["options"]) <= 10


# ── the solid of cubes ───────────────────────────────────────────────────────


def test_the_cube_key_counts_the_faces_that_touch_no_other_cube() -> None:
    drawing = Drawing(_id("2009-9"))
    cells = {}
    for hotspot in drawing.hotspots:
        x, y, z = (int(part) for part in hotspot.attrib["id"].removeprefix("cube-").split("-"))
        cells[(x, y, z)] = drawing.option(hotspot)
    assert len(cells) == len(drawing.exercise["options"]) == 10  # "zehn Würfel", none hidden
    painted = {}
    for (x, y, z), name in cells.items():
        touching = sum(
            (x + dx, y + dy, z + dz) in cells
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
        )
        painted[name] = 6 - touching
        # No cube floats: the solid stands on the ground or on a cube.
        assert z == 0 or (x, y, z - 1) in cells
    assert {name for name, faces in painted.items() if faces == 4} == _key(_id("2009-9"))


# ── nets, zipped shut ────────────────────────────────────────────────────────


def _same(p: Pt, q: Pt) -> bool:
    return _dist(p, q) < 1e-3


def _angle_at(polygon: list[Pt], index: int) -> float:
    here, before, after = polygon[index], polygon[index - 1], polygon[(index + 1) % len(polygon)]
    a = math.atan2(before[1] - here[1], before[0] - here[0])
    b = math.atan2(after[1] - here[1], after[0] - here[0])
    turn = abs(a - b) % (2 * math.pi)
    return math.degrees(min(turn, 2 * math.pi - turn))


class Zipped:
    """A net folded by its outline alone. Going round the outline, two neighbouring
    edges are glued as soon as the faces round the point between them fill a corner
    of the solid (`full(angle, triangle)`); gluing joins the points at their far
    ends, which may complete the next corner. Knows nothing of the solid's corners
    by name: only the drawn faces and how much angle a corner takes."""

    def __init__(self, faces: dict[str, list[Pt]], full: Callable[[float, float], bool]) -> None:
        self.faces = faces
        sides = []
        for polygon in faces.values():
            area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1], strict=True))
            ring = polygon if area > 0 else polygon[::-1]
            sides += list(zip(ring, ring[1:] + ring[:1], strict=True))
        outer = [side for side in sides if not any(_same(side[0], o[1]) and _same(side[1], o[0]) for o in sides)]
        ordered = [outer[0]]
        while len(ordered) < len(outer):
            ordered.append(next(side for side in outer if _same(side[0], ordered[-1][1])))
        self.edges = ordered
        count = len(ordered)
        # The outline point before edge i is point i.
        self.points = [edge[0] for edge in ordered]
        angle, triangle = [], []
        for point in self.points:
            total = corner = 0.0
            for polygon in faces.values():
                for index, vertex in enumerate(polygon):
                    if _same(vertex, point):
                        total += _angle_at(polygon, index)
                        if len(polygon) == 3:
                            corner += _angle_at(polygon, index)
            angle.append(total)
            triangle.append(corner)
        self.group = list(range(count))  # which outline points have become one
        self.partner: dict[int, int] = {}
        alive = list(range(count))  # edges not yet glued, in outline order
        angles = {index: (angle[index], triangle[index]) for index in range(count)}  # at the start of edge i
        while alive:
            for place, edge in enumerate(alive):
                before = alive[place - 1]
                if before == edge:
                    continue
                if full(*angles[edge]) and math.isclose(self._length(before), self._length(edge), abs_tol=1e-3):
                    after = alive[(place + 1) % len(alive)]
                    self.partner[before], self.partner[edge] = edge, before
                    if len(alive) > 2:
                        # The far ends of the two edges become one point.
                        self._join(before, after)
                        angles[after] = (
                            angles[after][0] + angles[before][0], angles[after][1] + angles[before][1]
                        )
                    alive = [e for e in alive if e not in (before, edge)]
                    break
            else:
                raise AssertionError("the outline does not zip shut")

    def _length(self, edge: int) -> float:
        return _dist(*self.edges[edge])

    def _join(self, first: int, second: int) -> None:
        old, new = self.group[first], self.group[second]
        self.group = [new if g == old else g for g in self.group]

    def edge_between(self, a: Pt, b: Pt) -> int:
        return next(
            index for index, (p, q) in enumerate(self.edges)
            if (_same(p, a) and _same(q, b)) or (_same(p, b) and _same(q, a))
        )

    def point_at(self, at: Pt) -> int:
        return next(index for index, point in enumerate(self.points) if _same(point, at))

    def same_corner(self, first: int, second: int) -> bool:
        return self.group[first] == self.group[second]

    def middle(self, edge: int) -> Pt:
        (ax, ay), (bx, by) = self.edges[edge]
        return ((ax + bx) / 2, (ay + by) / 2)


def _cuboid_corner(angle: float, _triangle: float) -> bool:
    return math.isclose(angle, 270, abs_tol=0.01)


def _wedge_corner(angle: float, triangle: float) -> bool:
    """Two right angles of rectangles and the corner of one triangle."""
    return triangle > 0 and math.isclose(angle, 180 + triangle, abs_tol=0.01)


def _hotspot_at(drawing: Drawing, at: Pt) -> str | None:
    return next((drawing.option(h) for h in drawing.hotspots if _same(drawing.centre(h), at)), None)


def test_the_cuboid_net_zips_k_and_m_onto_the_keyed_edges() -> None:
    drawing = Drawing(_id("2023-6b"))
    net = Zipped(drawing.polygons("face-"), _cuboid_corner)
    assert len(net.faces) == 6 and len(net.edges) == 14
    met = set()
    for mark in ("k", "m"):
        edge = net.edge_between(*drawing.ends(f"mark-{mark}"))
        # A marked edge is no option; the edge it meets is one.
        assert _hotspot_at(drawing, net.middle(edge)) is None
        name = _hotspot_at(drawing, net.middle(net.partner[edge]))
        assert name is not None
        met.add(name)
    assert met == _key(_id("2023-6b")) and len(met) == 2
    # Every option sits on the middle of an outline edge.
    for hotspot in drawing.hotspots:
        assert any(_same(drawing.centre(hotspot), net.middle(edge)) for edge in range(len(net.edges)))


def test_the_cuboid_net_zips_the_keyed_points_onto_z() -> None:
    drawing = Drawing(_id("2023-6c"))
    net = Zipped(drawing.polygons("face-"), _cuboid_corner)
    z = net.point_at(drawing.centre(drawing.by_id["mark-Z"]))
    together = {index for index in range(len(net.points)) if index != z and net.same_corner(index, z)}
    names = {_hotspot_at(drawing, net.points[index]) for index in together}
    assert None not in names  # every point that becomes Z's corner can be picked
    assert names == _key(_id("2023-6c"))
    for hotspot in drawing.hotspots:
        assert any(_same(drawing.centre(hotspot), point) for point in net.points)


def _wedge_corners(net: Zipped) -> dict[str, int]:
    """The outline point groups of a wedge's net, named as in the drawing of the
    wedge: A the right angle, B the end of the long leg, C the end of the short
    leg of the front triangle, A2, B2, C2 those of the back one.

    The net shows the outside. Seen from outside and going anticlockwise from the
    right angle, the front triangle of the drawn wedge (right angle bottom left,
    long leg along the ground to the right, short leg upright) comes to the long
    leg's end first; the back triangle, seen from behind, to the short leg's."""
    named = {}
    for polygon in (p for p in net.faces.values() if len(p) == 3):
        # On the page y runs down: a positive shoelace sum is clockwise to the eye.
        area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1], strict=True))
        ring = polygon[::-1] if area > 0 else polygon
        right = next(index for index in range(3) if math.isclose(_angle_at(ring, index), 90, abs_tol=0.01))
        corner, first, second = ring[right], ring[(right + 1) % 3], ring[(right + 2) % 3]
        front = _dist(corner, first) > _dist(corner, second)
        long_end, short_end = (first, second) if front else (second, first)
        suffix = "" if front else "2"
        named.update({
            f"A{suffix}": net.group[net.point_at(corner)],
            f"B{suffix}": net.group[net.point_at(long_end)],
            f"C{suffix}": net.group[net.point_at(short_end)],
        })
    assert len(set(named.values())) == 6
    return named


def test_the_wedge_net_zips_k_and_m_onto_the_keyed_edges_of_the_wedge() -> None:
    drawing = Drawing(_id("2017-9a"))
    net = Zipped(drawing.polygons("face-"), _wedge_corner)
    assert len(net.faces) == 5
    corners = {group: name for name, group in _wedge_corners(net).items()}
    right = set()
    for mark in ("k", "m"):
        a, b = drawing.ends(f"mark-{mark}")
        edge = sorted((corners[net.group[net.point_at(a)]], corners[net.group[net.point_at(b)]]))
        hotspot = drawing.by_id["solid-edge-" + "-".join(edge)]
        right.add(drawing.option(hotspot))
    assert right == _key(_id("2017-9a")) and len(right) == 2
    # The wedge has nine edges, each an option.
    assert len(drawing.hotspots) == 9


def test_the_wedge_net_zips_the_keyed_points_onto_the_top_front_corner() -> None:
    drawing = Drawing(_id("2017-9b"))
    net = Zipped(drawing.polygons("face-"), _wedge_corner)
    # Z is drawn at the top of the upright edge of the triangle facing the viewer: C.
    top_front = _wedge_corners(net)["C"]
    names = {
        _hotspot_at(drawing, point) for index, point in enumerate(net.points) if net.group[index] == top_front
    }
    assert None not in names
    assert names == _key(_id("2017-9b")) and len(names) == 3


# ── shapes cut into two pieces ───────────────────────────────────────────────

Squares = frozenset[tuple[int, int]]


def _cells(group: ET.Element) -> Squares:
    rects = group.findall(f"{SVG}rect")
    side = float(rects[0].attrib["width"])
    return frozenset((round(float(r.attrib["x"]) / side * 2), round(float(r.attrib["y"]) / side * 2)) for r in rects)


def _shape_key(cells: Squares) -> frozenset[Squares]:
    """A shape up to moving, turning and turning over: its eight pictures, each
    pushed so that its smallest square is the origin."""
    pictures = set()
    for a, b, c, d in ((1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0),
                       (-1, 0, 0, 1), (0, 1, 1, 0), (1, 0, 0, -1), (0, -1, -1, 0)):
        turned = [(a * x + b * y, c * x + d * y) for x, y in cells]
        low = min(turned)
        pictures.add(frozenset((x - low[0], y - low[1]) for x, y in turned))
    return frozenset(pictures)


@pytest.mark.parametrize(("version", "sizes"), [(1, (3, 3)), (2, (4, 2))])
def test_a_shape_is_keyed_when_some_cut_gives_the_two_pieces(version: int, sizes: tuple[int, int]) -> None:
    exercise_id = _id("2026-5", version)
    drawing = Drawing(exercise_id)
    first, second = _cells(drawing.by_id["piece-1"]), _cells(drawing.by_id["piece-2"])
    assert (len(first), len(second)) == sizes
    wanted = (_shape_key(first), _shape_key(second))
    fits = set()
    for hotspot in drawing.hotspots:
        cells = _cells(hotspot)
        assert len(cells) == 6
        if any(
            (_shape_key(frozenset(part)), _shape_key(cells - frozenset(part))) == wanted
            for part in combinations(sorted(cells), len(first))
        ):
            fits.add(drawing.option(hotspot))
    assert fits == _key(exercise_id)


# ── the manifest as a whole ──────────────────────────────────────────────────


def test_the_manifest_is_what_the_builder_builds() -> None:
    assert MANIFEST_PATH.read_text(encoding="utf-8") == zap_figure_batch3.rendered()


def test_every_original_of_the_issue_has_a_choose_several_exercise() -> None:
    adapted = set()
    for exercise_id, exercise in EXERCISES.items():
        assert exercise["type"] == multi_select.TYPE
        match = re.fullmatch(r"kb-zap-stoa-zap1-(.+)-v\d", exercise_id)
        assert match is not None
        year, _, number = match.group(1).partition("-")
        assert exercise["tags"] == ["zap", f"ZAP1 {year} · {number}"]
        adapted.add(match.group(1))
    assert adapted == ORIGINALS
    assert len(EXERCISES) == 18
    # Every key was worked out again above: none is left to trust.
    rederived = set(LOCUS_RULES) | {_id(o) for o in ("2009-9", "2023-6b", "2023-6c", "2017-9a", "2017-9b")}
    assert rederived | {_id("2026-5", 1), _id("2026-5", 2)} == set(EXERCISES)


@pytest.mark.parametrize("exercise_id", sorted(EXERCISES))
def test_hotspots_and_options_match_one_to_one(exercise_id: str) -> None:
    exercise = EXERCISES[exercise_id]
    drawing = Drawing(exercise_id)
    assert figure_svg.figure_issues(exercise["figure"]) == []
    assert not figure_svg.has_text(exercise["figure"])  # one figure serves four languages
    letters = [multi_select.letter(index) for index in range(len(exercise["options"]))]
    assert figure_svg.hotspots(exercise["figure"]) == letters
    for hotspot in drawing.hotspots:
        # What is written in the hotspot is the option's own name.
        written = "".join(text.text or "" for text in hotspot.iter(f"{SVG}text"))
        assert written == drawing.option(hotspot)
    # A 44 px target round each hotspot in a figure 360 px wide.
    width = float(drawing.root.attrib["viewBox"].split()[2])
    centres = []
    for hotspot in drawing.hotspots:
        circle = hotspot.find(f"{SVG}circle")
        if circle is not None:
            centres.append(drawing.centre(hotspot))
        else:
            rects = hotspot.findall(f"{SVG}rect")
            centres.append((
                sum(float(r.attrib["x"]) for r in rects) / len(rects),
                sum(float(r.attrib["y"]) for r in rects) / len(rects),
            ))
    for p, q in combinations(centres, 2):
        assert max(abs(p[0] - q[0]), abs(p[1] - q[1])) * 360 / max(width, 360) >= 40
    key = exercise["correctOptions"]
    assert 2 <= len(key) < len(exercise["options"]) <= multi_select.MAX_OPTIONS
    assert key == sorted(set(key))


@pytest.mark.parametrize("exercise_id", sorted(EXERCISES))
def test_the_four_texts_are_whole_and_name_the_key(exercise_id: str) -> None:
    exercise = EXERCISES[exercise_id]
    assert set(exercise["translations"]) == {"en", "fr", "it"}
    right = [exercise["options"][index] for index in exercise["correctOptions"]]
    for locale in LOCALES:
        text = exercise if locale == "de" else exercise["translations"][locale]
        assert text.get("options", exercise["options"]) == exercise["options"]
        for field in ("prompt", "explanation"):
            assert 40 <= len(text[field]) <= 2000
            assert "{" not in text[field] and "}" not in text[field]
        # The explanation names every right option.
        named = set(re.findall(r"\$[A-Z]\$" if right[0].startswith("$") else r"\d+", text["explanation"]))
        assert set(right) <= named, locale
    assert "ß" not in exercise["prompt"] + exercise["explanation"]
    french = exercise["translations"]["fr"]
    assert not re.search(r" [?!:;]", french["prompt"] + french["explanation"])


def test_the_new_practice_sets_are_named_in_four_languages() -> None:
    skills = json.loads(
        (Path(__file__).parents[1] / "src" / "stoa" / "services" / "knowledge_base_skills.json").read_text(encoding="utf-8")
    )
    for lesson in MANIFEST["lessons"]:
        assert lesson["publish"] is False
        titles = skills["practiceSets"][lesson["publicLessonId"]]
        assert set(titles) == set(LOCALES)
        assert lesson["lesson"]["titles"] == titles
        for exercise in lesson["exercises"]:
            [skill] = exercise["skills"]
            assert skills["skills"][skill]["unit"] == lesson["lesson"]["unitId"]
            assert lesson["publicLessonId"].startswith(skill + "--zap")


# ── migrated and answered ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def migrated() -> FakeTable:
    """The manifest in a seeded table double: dry run, apply, review, publish. Once
    for the module: seeding the knowledge base takes a while."""
    table = FakeTable()
    table.seed(*seed_practice.seed_rows(knowledge_base=seed_practice.knowledge_base_live_mode([])))
    db_table.install(table)
    record = curriculum_analytics_service.record_publish_event
    curriculum_analytics_service.record_publish_event = lambda *a, **k: None  # type: ignore[assignment]
    try:
        planned = curriculum_migration_service.dry_run(deepcopy(MANIFEST), OPERATOR)
        assert planned["summary"]["errors"] == 0, [row["validationIssues"] for row in planned["rows"]]
        assert planned["publishReady"]
        assert {row["action"] for row in planned["rows"]} == {"create"}
        assert not any(row["validationIssues"] or row["conflicts"] for row in planned["rows"])
        applied = curriculum_migration_service.apply_migration(
            planned["migrationId"], deepcopy(MANIFEST), planned["confirmationToken"], OPERATOR
        )
        for row in applied["rows"]:
            lesson_id, version_id = row["publicLessonId"], row["versionId"]
            # Applied as a draft: nothing is live before a person publishes.
            assert (curriculum_ops_repo.get_pointer(lesson_id) or {}).get("published_version_id") is None
            curriculum_ops_service.submit_review(lesson_id, version_id, OPERATOR)
            curriculum_ops_service.approve(lesson_id, version_id, OPERATOR)
            curriculum_ops_service.publish(lesson_id, version_id, OPERATOR, expected_published_version_id=None)
        return table
    finally:
        curriculum_analytics_service.record_publish_event = record  # type: ignore[assignment]
        db_table.install(None)


@pytest.fixture
def published(migrated: FakeTable) -> FakeTable:
    """The migrated table behind the repositories for this test (the suite gives
    every test an empty one by default)."""
    db_table.install(migrated)
    return migrated


@pytest.mark.parametrize("exercise_id", sorted(EXERCISES))
def test_a_published_exercise_is_right_only_for_exactly_its_key(published: FakeTable, exercise_id: str) -> None:
    challenge = practice_repo.get_challenge(exercise_id)
    assert challenge is not None
    key = EXERCISES[exercise_id]["correctOptions"]
    count = len(EXERCISES[exercise_id]["options"])
    assert multi_select.correct_options(challenge) == key
    others = [index for index in range(count) if index not in key]
    for locale in LOCALES:
        assert answer_recording.judge(challenge, list(reversed(key)), locale=locale).correct is True
        assert answer_recording.judge(challenge, key[:-1], locale=locale).correct is False  # one missing
        assert answer_recording.judge(challenge, [*key, others[0]], locale=locale).correct is False  # one extra
        assert answer_recording.judge(challenge, [*key[1:], others[-1]], locale=locale).correct is False
        shown = practice_projection_service.build_challenge_preview(challenge, locale)
        assert figure_svg.hotspots(shown["figure"]) == [multi_select.letter(i) for i in range(count)]
        assert len(shown["options"]) == count
        assert not {"correctOptions", "correct_options", "correctAnswer", "correct_answer"} & set(shown)
