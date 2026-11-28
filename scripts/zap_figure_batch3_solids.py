"""Solids, nets and polyominoes for the ZAP figure tasks of batch 3 (#596).

Three kinds of computed keys, none of them read off a drawing:

- a solid built of unit cubes: which cubes are fully drawn, and how many faces
  of each lie on the outside (`CubeSolid`);
- a net of a solid: the solid is given by its named corners and its faces, the
  net is that solid unfolded along a tree of its faces, so every corner and edge
  of the net carries the name of the corner or edge of the solid it is (`unfold`).
  Which edges are glued together and which points of the net become one corner
  follow from the names;
- a polyomino: whether it can be cut into two given pieces (`splits_into`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import isqrt

Cell = tuple[int, int, int]
Vec = tuple[Fraction, Fraction, Fraction]
Flat = tuple[Fraction, Fraction]


# ── solids of unit cubes ─────────────────────────────────────────────────────

#: The faces a viewer in front, to the right and above sees: outward direction and
#: the four corners (offsets from the cube's cell), the first and third joined by
#: the short diagonal of the drawn rhombus.
VISIBLE_FACES: dict[str, tuple[Cell, tuple[Cell, Cell, Cell, Cell]]] = {
    "top": ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
    "right": ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    "left": ((0, 1, 0), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1))),
}
_NEIGHBOURS: tuple[Cell, ...] = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def _add(a: Cell, b: Cell) -> Cell:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


@dataclass(frozen=True)
class CubeSolid:
    """Unit cubes at whole-number cells, seen from in front, the right and above:
    x runs to the front right, y to the front left, z up."""

    cells: tuple[Cell, ...]

    def outside_faces(self, cell: Cell) -> int:
        """How many of the cube's six faces touch no other cube."""
        return sum(_add(cell, step) not in self.cells for step in _NEIGHBOURS)

    def _hidden(self, at: tuple[Fraction, Fraction, Fraction], own: Cell) -> bool:
        """Whether another cube lies between this point and the viewer (along (1, 1, 1))."""
        for cell in self.cells:
            if cell == own:
                continue
            low = max(Fraction(cell[axis]) - at[axis] for axis in range(3))
            high = min(Fraction(cell[axis] + 1) - at[axis] for axis in range(3))
            if low < high and high > 0:
                return True
        return False

    def visible_halves(self, cell: Cell, face: str) -> list[tuple[Fraction, Fraction, Fraction]]:
        """The centres of the halves of this face that nothing covers. The view along
        (1, 1, 1) cuts the picture into equal triangles, two to a face; each is covered
        whole or not at all, so its centre decides."""
        step, corners = VISIBLE_FACES[face]
        if _add(cell, step) in self.cells:
            return []
        points = [_add(cell, corner) for corner in corners]
        seen = []
        for triangle in ((points[0], points[1], points[2]), (points[0], points[2], points[3])):
            centre = (
                Fraction(sum(p[0] for p in triangle), 3),
                Fraction(sum(p[1] for p in triangle), 3),
                Fraction(sum(p[2] for p in triangle), 3),
            )
            if not self._hidden(centre, cell):
                seen.append(centre)
        return seen

    def label_point(self, cell: Cell) -> tuple[Fraction, Fraction, Fraction] | None:
        """Where the cube's letter stands: the middle of the first of its top, right
        and left faces drawn whole, else the middle of a half face drawn whole; `None`
        when the cube shows no such half."""
        halves = {face: self.visible_halves(cell, face) for face in VISIBLE_FACES}
        for seen in halves.values():
            if len(seen) == 2:
                return (
                    (seen[0][0] + seen[1][0]) / 2,
                    (seen[0][1] + seen[1][1]) / 2,
                    (seen[0][2] + seen[1][2]) / 2,
                )
        return next((seen[0] for seen in halves.values() if seen), None)


def isometric(at: Sequence[Fraction | int], edge: float) -> tuple[float, float]:
    """Where a point of a cube solid is drawn (y downwards), before shifting into the picture."""
    x, y, z = (float(value) for value in at)
    return ((x - y) * edge * 0.8660254, (x + y) * edge * 0.5 - z * edge)


# ── solids with named corners, and their nets ────────────────────────────────


@dataclass(frozen=True)
class Solid:
    """A solid with flat faces: corners by name, and each face as its corners in
    order, anticlockwise seen from outside."""

    corners: dict[str, Vec]
    faces: dict[str, tuple[str, ...]]

    def edges(self) -> list[frozenset[str]]:
        found: list[frozenset[str]] = []
        for face in self.faces.values():
            for a, b in zip(face, face[1:] + face[:1], strict=True):
                if frozenset((a, b)) not in found:
                    found.append(frozenset((a, b)))
        return found

    def faces_at(self, edge: frozenset[str]) -> list[str]:
        return [
            name for name, face in self.faces.items()
            if any(frozenset(pair) == edge for pair in zip(face, face[1:] + face[:1], strict=True))
        ]

    def normal(self, face: str) -> Vec:
        """Outward, not of length one."""
        a, b, c = (self.corners[name] for name in self.faces[face][:3])
        return _cross(_sub(b, a), _sub(c, a))


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Vec, b: Vec) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _rational_root(value: Fraction) -> Fraction:
    numerator, denominator = isqrt(value.numerator), isqrt(value.denominator)
    if numerator * numerator != value.numerator or denominator * denominator != value.denominator:
        raise ValueError(f"the length {value}^(1/2) is not rational: this solid cannot be unfolded exactly")
    return Fraction(numerator, denominator)


def _unit(vector: Vec) -> Vec:
    length = _rational_root(_dot(vector, vector))
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def cuboid(a: int, b: int, c: int) -> Solid:
    """a wide (x), b deep (y), c high (z); corner names say which end of each axis."""
    corners = {
        f"{x}{y}{z}": (Fraction(a * x), Fraction(b * y), Fraction(c * z))
        for x in (0, 1) for y in (0, 1) for z in (0, 1)
    }
    faces = {
        "bottom": ("000", "010", "110", "100"),
        "top": ("001", "101", "111", "011"),
        "front": ("000", "100", "101", "001"),
        "back": ("010", "011", "111", "110"),
        "left": ("000", "001", "011", "010"),
        "right": ("100", "110", "111", "101"),
    }
    return Solid(corners, faces)


def wedge(run: int, rise: int, depth: int) -> Solid:
    """A prism over a right triangle: the right angle at A, B along the ground,
    C straight above A; A2, B2, C2 behind them."""
    f = Fraction
    corners = {
        "A": (f(0), f(0), f(0)), "B": (f(run), f(0), f(0)), "C": (f(0), f(0), f(rise)),
        "A2": (f(0), f(depth), f(0)), "B2": (f(run), f(depth), f(0)),
        "C2": (f(0), f(depth), f(rise)),
    }
    faces = {
        "front": ("A", "B", "C"),
        "back": ("A2", "C2", "B2"),
        "bottom": ("A", "A2", "B2", "B"),
        "upright": ("A", "C", "C2", "A2"),
        "slope": ("B", "B2", "C2", "C"),
    }
    return Solid(corners, faces)


@dataclass(frozen=True)
class NetFace:
    name: str
    #: The solid's corner at each corner of the drawn face, and where it is drawn.
    corners: tuple[str, ...]
    points: tuple[Flat, ...]


@dataclass(frozen=True)
class NetEdge:
    """An edge on the outline of a net."""

    face: str
    a: Flat
    b: Flat
    #: The edge of the solid it is.
    solid: frozenset[str]

    @property
    def middle(self) -> Flat:
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2)


def _flat_face(solid: Solid, name: str) -> list[Flat]:
    """The face laid flat by itself, seen from outside."""
    points = [solid.corners[corner] for corner in solid.faces[name]]
    e1 = _unit(_sub(points[1], points[0]))
    e2 = _unit(_cross(solid.normal(name), e1))
    return [(_dot(_sub(p, points[0]), e1), _dot(_sub(p, points[0]), e2)) for p in points]


def unfold(solid: Solid, root: str, tree: Sequence[tuple[str, str]]) -> list[NetFace]:
    """The net with `root` as drawn by `_flat_face` and each `(child, parent)` of the
    tree hinged to its parent along the edge they share. Every face is seen from
    outside, so a child is moved without turning it over and lands beyond the hinge."""
    placed: dict[str, NetFace] = {
        root: NetFace(root, solid.faces[root], tuple(_flat_face(solid, root)))
    }
    for child, parent in tree:
        shared = [corner for corner in solid.faces[child] if corner in solid.faces[parent]]
        if len(shared) != 2 or child in placed:
            raise ValueError(f"{child} cannot be hinged to {parent}")
        own = dict(zip(solid.faces[child], _flat_face(solid, child), strict=True))
        there = dict(zip(placed[parent].corners, placed[parent].points, strict=True))
        a, b = shared
        # The turn and shift that carry the child's a and b onto the parent's.
        ux, uy = own[b][0] - own[a][0], own[b][1] - own[a][1]
        vx, vy = there[b][0] - there[a][0], there[b][1] - there[a][1]
        norm = ux * ux + uy * uy
        cos, sin = (ux * vx + uy * vy) / norm, (ux * vy - uy * vx) / norm
        points = []
        for corner in solid.faces[child]:
            px, py = own[corner][0] - own[a][0], own[corner][1] - own[a][1]
            points.append((there[a][0] + cos * px - sin * py, there[a][1] + sin * px + cos * py))
        placed[child] = NetFace(child, solid.faces[child], tuple(points))
    if set(placed) != set(solid.faces):
        raise ValueError("the tree does not reach every face")
    return list(placed.values())


def outline(net: Sequence[NetFace]) -> list[NetEdge]:
    """The edges on the outside of the net, in order round it, starting at the
    top-left corner and going clockwise as drawn (y upwards here)."""
    sides: list[NetEdge] = []
    for face in net:
        ring = list(zip(face.corners, face.points, strict=True))
        for (ca, pa), (cb, pb) in zip(ring, ring[1:] + ring[:1], strict=True):
            sides.append(NetEdge(face.name, pa, pb, frozenset((ca, cb))))
    outer = [
        side for side in sides
        if not any(other.a == side.b and other.b == side.a for other in sides)
    ]
    start = min(outer, key=lambda side: (-side.b[1], side.b[0]))
    # Each face runs anticlockwise, so the outline does too; walk it backwards.
    ordered = [start]
    while len(ordered) < len(outer):
        ordered.append(next(side for side in outer if side.b == ordered[-1].a))
    return ordered


def glued_to(edges: Sequence[NetEdge], index: int) -> int:
    """The outline edge that meets edge `index` when the net is folded."""
    [partner] = [
        other for other, edge in enumerate(edges)
        if other != index and edge.solid == edges[index].solid
    ]
    return partner


def outline_points(net: Sequence[NetFace]) -> list[tuple[Flat, str]]:
    """Each point of the outline with the corner of the solid it becomes, in outline order."""
    names = {point: corner for face in net for corner, point in zip(face.corners, face.points, strict=True)}
    return [(edge.b, names[edge.b]) for edge in outline(net)]


def _strictly_inside(p: Flat, polygon: Sequence[Flat]) -> bool:
    """For a convex polygon given anticlockwise."""
    ring = list(polygon)
    return all(
        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) > 0
        for a, b in zip(ring, ring[1:] + ring[:1], strict=True)
    )


def overlapping_faces(net: Sequence[NetFace]) -> list[tuple[str, str]]:
    """Pairs of faces of a net that lie on top of each other. The faces are convex:
    two overlap exactly when a point strictly inside both exists, and then one is
    found among the corners, edge middles and centres of the two and the middles
    between them."""
    found = []
    for first, second in combinations(net, 2):
        probes: list[Flat] = []
        for face in (first, second):
            ring = list(face.points)
            centre = (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
            probes.append(centre)
            for a, b in zip(ring, ring[1:] + ring[:1], strict=True):
                middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                probes.extend(
                    ((q[0] * 9 + centre[0]) / 10, (q[1] * 9 + centre[1]) / 10) for q in (a, middle)
                )
        if any(_strictly_inside(p, first.points) and _strictly_inside(p, second.points) for p in probes):
            found.append((first.name, second.name))
    return found


# ── polyominoes ──────────────────────────────────────────────────────────────

Square = tuple[int, int]


def squares(rows: Iterable[str]) -> frozenset[Square]:
    """The squares of a shape drawn with `#`, row by row from the top."""
    return frozenset(
        (column, row) for row, line in enumerate(rows) for column, mark in enumerate(line) if mark == "#"
    )


def _normal(shape: Iterable[Square]) -> frozenset[Square]:
    shape = list(shape)
    left, top = min(x for x, _ in shape), min(y for _, y in shape)
    return frozenset((x - left, y - top) for x, y in shape)


def placements(shape: Iterable[Square]) -> set[frozenset[Square]]:
    """The shape turned and turned over every way, pushed into the corner."""
    found = set()
    current = list(shape)
    for _ in range(4):
        current = [(-y, x) for x, y in current]
        found.add(_normal(current))
        found.add(_normal((-x, y) for x, y in current))
    return found


def splits_into(shape: frozenset[Square], first: frozenset[Square], second: frozenset[Square]) -> bool:
    """Whether the shape can be cut along the grid into the two pieces (which may be
    turned and turned over)."""
    if len(shape) != len(first) + len(second):
        return False
    for part in combinations(sorted(shape), len(first)):
        if _normal(part) in placements(first) and _normal(shape - set(part)) in placements(second):
            return True
    return False
