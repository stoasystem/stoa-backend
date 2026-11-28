"""The seven tasks of batch 3 picked in a drawing of a solid, a net or a set of
shapes (#596): each task's figure and its key, both made from one description.

The figures carry `id`s on the parts the key rests on (`cube-x-y-z`, `face-…`,
`mark-…`, `net-point-…`, `piece-…`), so `tests/test_zap_figure_batch3.py` can
work the key out again from the finished drawing by another way.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from scripts.zap_figure_batch3_solids import (
    VISIBLE_FACES,
    CubeSolid,
    Flat,
    NetEdge,
    NetFace,
    Solid,
    cuboid,
    glued_to,
    isometric,
    outline,
    outline_points,
    overlapping_faces,
    splits_into,
    squares,
    unfold,
    wedge,
)

#: Two hotspots are at least this far apart (the larger of across and down) in
#: a figure about 360 wide: the client gives each a 44 px target.
MIN_HOTSPOT_GAP = 44
INK = 'stroke="currentColor"'


@dataclass(frozen=True)
class FigureTask:
    key: str
    original: str
    figure: str
    #: What each option is called, in order; the hotspots are lettered A, B, … in the same order.
    options: tuple[str, ...]
    correct: tuple[int, ...]
    #: Facts the explanation quotes, by name.
    facts: dict[str, object]
    #: Where each hotspot's badge is drawn, to check their distances.
    hotspots: tuple[tuple[float, float], ...]

    def hotspot_gap(self) -> float:
        points = self.hotspots
        return min(
            max(abs(p[0] - q[0]), abs(p[1] - q[1]))
            for index, p in enumerate(points)
            for q in points[index + 1:]
        )


def _n(value: float | Fraction) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _points(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in points)


def _badge(letter: str, name: str, text: str, at: tuple[float, float], radius: int = 10) -> str:
    return (
        f'<g data-choice="{letter}" id="{name}"><circle cx="{_n(at[0])}" cy="{_n(at[1])}" '
        f'r="{radius}" fill="#ffffff" {INK} stroke-width="1.5"/>'
        f'<text x="{_n(at[0])}" y="{_n(at[1] + 4)}" font-size="12" text-anchor="middle" '
        f'fill="currentColor">{text}</text></g>'
    )


def _svg(width: float, height: float, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(width)} {_n(height)}">'
        f"{body}</svg>"
    )


def _letter(index: int) -> str:
    return chr(ord("A") + index)


# ── 2009-9: a solid of cubes, painted ────────────────────────────────────────

CUBE_EDGE = 52
#: Ten cubes, lettered in this order. Every cube shows a whole face.
CUBES = CubeSolid((
    (0, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0), (2, 1, 1),
    (3, 0, 0), (3, 0, 1), (3, 0, 2), (3, 1, 0), (3, 1, 1),
))
#: The task asks for the cubes with this many painted faces.
PAINTED_FACES = 4
_FACE_FILL = {"top": "#f4f4f4", "right": "#d9d9d9", "left": "#bdbdbd"}


def cube_task() -> FigureTask:
    solid = CUBES
    corners = [
        isometric((cell[0] + dx, cell[1] + dy, cell[2] + dz), CUBE_EDGE)
        for cell in solid.cells for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)
    ]
    pad = 14
    shift_x = pad - min(x for x, _ in corners)
    shift_y = pad - min(y for _, y in corners)

    def at(point: Sequence[Fraction | int]) -> tuple[float, float]:
        x, y = isometric(point, CUBE_EDGE)
        return (x + shift_x, y + shift_y)

    drawn = []
    for cell in sorted(solid.cells, key=lambda c: (sum(c), c)):
        for face, (step, offsets) in VISIBLE_FACES.items():
            if tuple(a + b for a, b in zip(cell, step, strict=True)) in solid.cells:
                continue
            ring = [at([a + b for a, b in zip(cell, offset, strict=True)]) for offset in offsets]
            drawn.append(
                f'<polygon points="{_points(ring)}" fill="{_FACE_FILL[face]}" {INK} '
                f'stroke-width="1.5" stroke-linejoin="round"/>'
            )
    badges, centres = [], []
    for index, cell in enumerate(solid.cells):
        spot = solid.label_point(cell)
        if spot is None:
            raise ValueError(f"cube {cell} shows not even half a face")
        centre = at(spot)
        centres.append(centre)
        badges.append(
            _badge(_letter(index), f"cube-{cell[0]}-{cell[1]}-{cell[2]}", _letter(index), centre, 11)
        )
    width = max(x for x, _ in corners) + shift_x + pad
    height = max(y for _, y in corners) + shift_y + pad
    painted = [solid.outside_faces(cell) for cell in solid.cells]
    return FigureTask(
        "wuerfel", "2009-9", _svg(width, height, "".join(drawn) + "".join(badges)),
        tuple(_letter(index) for index in range(len(solid.cells))),
        tuple(index for index, count in enumerate(painted) if count == PAINTED_FACES),
        {"painted": painted},
        tuple(centres),
    )


# ── nets ─────────────────────────────────────────────────────────────────────


class NetDrawing:
    """A net on the page: `unit` drawing units to one unit of length, its top-left
    corner at `origin`; `turned` draws it a quarter turn anticlockwise."""

    def __init__(
        self, net: Sequence[NetFace], unit: float, origin: tuple[float, float], *, turned: bool = False
    ) -> None:
        if overlapping_faces(net):
            raise ValueError(f"faces of the net overlap: {overlapping_faces(net)}")
        self.net, self.unit, self.turned = list(net), unit, turned
        flat = [self._turn(point) for face in net for point in face.points]
        self.left, self.top = min(x for x, _ in flat), max(y for _, y in flat)
        self.width = (max(x for x, _ in flat) - self.left) * unit
        self.height = (self.top - min(y for _, y in flat)) * unit
        self.origin = origin

    def _turn(self, point: Flat) -> tuple[float, float]:
        x, y = float(point[0]), float(point[1])
        return (-y, x) if self.turned else (x, y)

    def at(self, point: Flat) -> tuple[float, float]:
        x, y = self._turn(point)
        return (self.origin[0] + (x - self.left) * self.unit, self.origin[1] + (self.top - y) * self.unit)

    def faces(self, shaded: Sequence[str] = ()) -> str:
        parts = []
        for face in self.net:
            fill = "#bdbdbd" if face.name in shaded else "#f4f4f4"
            parts.append(
                f'<polygon id="face-{face.name}" points="{_points([self.at(p) for p in face.points])}" '
                f'fill="{fill}" {INK} stroke-width="0.8" stroke-dasharray="4 3"/>'
            )
        for edge in outline(self.net):
            (x1, y1), (x2, y2) = self.at(edge.a), self.at(edge.b)
            parts.append(
                f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" {INK} '
                f'stroke-width="2" stroke-linecap="round"/>'
            )
        return "".join(parts)

    def mark(self, name: str, edge: NetEdge, outward: tuple[float, float]) -> str:
        """An outline edge drawn heavy, its name beside it on the side `outward` points to."""
        (x1, y1), (x2, y2) = self.at(edge.a), self.at(edge.b)
        mx, my = self.at(edge.middle)
        return (
            f'<line id="mark-{name}" x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" {INK} '
            f'stroke-width="5" stroke-linecap="round"/>'
            f'<text x="{_n(mx + outward[0])}" y="{_n(my + outward[1] + 5)}" font-size="15" '
            f'font-style="italic" font-weight="bold" text-anchor="middle" fill="currentColor">{name}</text>'
        )


def _spread(
    places: Sequence[tuple[float, float]], required: Sequence[int], limit: int
) -> list[int]:
    """Up to `limit` of the places, the required ones first, then in order, each
    at least `MIN_HOTSPOT_GAP` from those already taken."""
    taken: list[int] = []
    for index in [*required, *(i for i in range(len(places)) if i not in required)]:
        if len(taken) < limit and all(
            max(abs(places[index][0] - places[other][0]), abs(places[index][1] - places[other][1]))
            >= MIN_HOTSPOT_GAP
            for other in taken
        ):
            taken.append(index)
    missing = [index for index in required if index not in taken]
    if missing:
        raise ValueError(f"required hotspots {missing} are too close to each other")
    return sorted(taken)


def _outward(drawing: NetDrawing, edge: NetEdge, by: float) -> tuple[float, float]:
    """A step of `by` drawing units from the middle of an outline edge away from its face."""
    face = next(f for f in drawing.net if f.name == edge.face)
    cx = sum(drawing.at(p)[0] for p in face.points) / len(face.points)
    cy = sum(drawing.at(p)[1] for p in face.points) / len(face.points)
    (x1, y1), (x2, y2) = drawing.at(edge.a), drawing.at(edge.b)
    nx, ny = y2 - y1, x1 - x2
    length = (nx * nx + ny * ny) ** 0.5
    nx, ny = nx / length, ny / length
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if (mx - cx) * nx + (my - cy) * ny < 0:
        nx, ny = -nx, -ny
    return (nx * by, ny * by)


#: 2023-6b and 6c: the cuboid and how each of its two nets hangs together.
BOX = cuboid(3, 2, 4)
EDGE_NET = ("front", (("right", "front"), ("top", "right"), ("back", "top"), ("left", "back"), ("bottom", "left")))
#: The two outline edges drawn heavy (their places in the outline), k then m.
EDGE_NET_MARKS = (0, 2)
POINT_NET = ("front", (("top", "front"), ("bottom", "front"), ("back", "top"), ("left", "top"), ("right", "bottom")))
#: The outline point named Z.
POINT_NET_MARK = 12


def net_edges_task() -> FigureTask:
    net = unfold(BOX, EDGE_NET[0], EDGE_NET[1])
    drawing = NetDrawing(net, 27, (18, 18))
    edges = outline(net)
    partners = [glued_to(edges, index) for index in EDGE_NET_MARKS]
    open_edges = [index for index in range(len(edges)) if index not in EDGE_NET_MARKS]
    places = [drawing.at(edges[index].middle) for index in open_edges]
    chosen = _spread(places, [open_edges.index(partner) for partner in partners], 12)
    body = drawing.faces()
    for name, index in zip("km", EDGE_NET_MARKS, strict=True):
        body += drawing.mark(name, edges[index], _outward(drawing, edges[index], 13))
    for number, place in enumerate(chosen, start=1):
        body += _badge(_letter(number - 1), f"net-edge-{open_edges[place]}", str(number), places[place])
    numbers = {open_edges[place]: number for number, place in enumerate(chosen, start=1)}
    return FigureTask(
        "netz-kanten", "2023-6b",
        _svg(drawing.width + 52, drawing.height + 36, body),
        tuple(str(number) for number in range(1, len(chosen) + 1)),
        tuple(sorted(numbers[partner] - 1 for partner in partners)),
        {"k": numbers[partners[0]], "m": numbers[partners[1]],
         "lengths": [_edge_length(edges[index]) for index in EDGE_NET_MARKS]},
        tuple(places[place] for place in chosen),
    )


def _edge_length(edge: NetEdge) -> Fraction:
    return abs(edge.a[0] - edge.b[0]) + abs(edge.a[1] - edge.b[1])


def _net_points_task(
    key: str, original: str, solid: Solid, tree: tuple[str, Sequence[tuple[str, str]]],
    drawing_of: Callable[[Sequence[NetFace]], NetDrawing], corner: str, *, mark: int | None,
    shaded: Sequence[str] = (), extra: Callable[[NetDrawing], tuple[str, float, float]] | None = None,
) -> FigureTask:
    """Which outline points of a net become the solid's `corner`. With `mark`, that
    outline point is named Z and is no option; without, every point is an option."""
    net = unfold(solid, tree[0], tree[1])
    drawing = drawing_of(net)
    points = outline_points(net)
    open_points = [index for index in range(len(points)) if index != mark]
    places = [drawing.at(points[index][0]) for index in open_points]
    right = [place for place, index in enumerate(open_points) if points[index][1] == corner]
    chosen = _spread(places, right, 12)
    body = drawing.faces(shaded)
    width, height = drawing.origin[0] + drawing.width + 18, drawing.origin[1] + drawing.height + 18
    if extra is not None:
        more, more_width, more_height = extra(drawing)
        body += more
        width, height = max(width, more_width), max(height, more_height)
    if mark is not None:
        zx, zy = drawing.at(points[mark][0])
        body += (
            f'<circle id="mark-Z" cx="{_n(zx)}" cy="{_n(zy)}" r="5" fill="currentColor"/>'
            f'<text x="{_n(zx - 9)}" y="{_n(zy - 7)}" font-size="15" font-style="italic" '
            f'font-weight="bold" text-anchor="end" fill="currentColor">Z</text>'
        )
    for number, place in enumerate(chosen, start=1):
        body += _badge(_letter(number - 1), f"net-point-{open_points[place]}", str(number), places[place])
    numbers = {place: number for number, place in enumerate(chosen, start=1)}
    return FigureTask(
        key, original, _svg(width, height, body),
        tuple(str(number) for number in range(1, len(chosen) + 1)),
        tuple(sorted(numbers[place] - 1 for place in right)),
        {"corner": corner},
        tuple(places[place] for place in chosen),
    )


def net_points_task() -> FigureTask:
    corner = outline_points(unfold(BOX, POINT_NET[0], POINT_NET[1]))[POINT_NET_MARK][1]
    return _net_points_task(
        "netz-ecken", "2023-6c", BOX, POINT_NET,
        lambda net: NetDrawing(net, 26, (26, 18)), corner, mark=POINT_NET_MARK,
    )


# ── 2017-9: a wedge and its net ──────────────────────────────────────────────

WEDGE = wedge(4, 3, 2)
#: How far a step into the depth is drawn to the right and upwards.
DEPTH_RIGHT, DEPTH_UP = 0.7, 0.45
WEDGE_EDGE_NET = ("slope", (("bottom", "slope"), ("upright", "slope"), ("front", "bottom"), ("back", "upright")))
#: The two outline edges of that net drawn heavy, k then m.
WEDGE_NET_MARKS = (0, 6)
WEDGE_POINT_NET = ("bottom", (("slope", "bottom"), ("upright", "bottom"), ("front", "bottom"), ("back", "bottom")))
#: The corner of the wedge named Z in the drawing of the solid: C, top front.
WEDGE_CORNER = "C"


class WedgeDrawing:
    """The wedge in an oblique view from the front, the right and above."""

    def __init__(self, unit: float, origin: tuple[float, float]) -> None:
        self.unit = unit
        flat = [self._flat(name) for name in WEDGE.corners]
        self.left, self.top = min(x for x, _ in flat), max(y for _, y in flat)
        self.width = (max(x for x, _ in flat) - self.left) * unit
        self.height = (self.top - min(y for _, y in flat)) * unit
        self.origin = origin

    @staticmethod
    def _flat(corner: str) -> tuple[float, float]:
        x, y, z = (float(value) for value in WEDGE.corners[corner])
        return (x + DEPTH_RIGHT * y, z + DEPTH_UP * y)

    def at(self, corner: str) -> tuple[float, float]:
        x, y = self._flat(corner)
        return (self.origin[0] + (x - self.left) * self.unit, self.origin[1] + (self.top - y) * self.unit)

    def faces_seen(self) -> list[str]:
        """The faces turned towards the viewer."""
        towards = (Fraction(str(DEPTH_RIGHT)), Fraction(-1), Fraction(str(DEPTH_UP)))
        return [
            name for name in WEDGE.faces
            if sum(a * b for a, b in zip(WEDGE.normal(name), towards, strict=True)) > 0
        ]

    def middle(self, edge: frozenset[str]) -> tuple[float, float]:
        (x1, y1), (x2, y2) = (self.at(corner) for corner in sorted(edge))
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def body(self) -> str:
        seen = self.faces_seen()
        parts = []
        for name in seen:
            fill = "#bdbdbd" if name == "slope" else "#f4f4f4"
            ring = [self.at(corner) for corner in WEDGE.faces[name]]
            parts.append(f'<polygon points="{_points(ring)}" fill="{fill}" stroke="none"/>')
        for edge in WEDGE.edges():
            (x1, y1), (x2, y2) = (self.at(corner) for corner in sorted(edge))
            hidden = not any(face in seen for face in WEDGE.faces_at(edge))
            look = 'stroke-width="1.2" stroke-dasharray="5 4"' if hidden else 'stroke-width="2"'
            parts.append(
                f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" {INK} {look} '
                f'stroke-linecap="round"/>'
            )
        return "".join(parts)


def wedge_edges_task() -> FigureTask:
    solid_drawing = WedgeDrawing(52, (40, 16))
    net = unfold(WEDGE, WEDGE_EDGE_NET[0], WEDGE_EDGE_NET[1])
    drawing = NetDrawing(net, 24, (36, solid_drawing.height + 52), turned=True)
    edges = outline(net)
    body = solid_drawing.body() + drawing.faces(["slope"])
    for name, index in zip("km", WEDGE_NET_MARKS, strict=True):
        body += drawing.mark(name, edges[index], _outward(drawing, edges[index], 13))
    solid_edges = WEDGE.edges()
    places = [solid_drawing.middle(edge) for edge in solid_edges]
    for index, edge in enumerate(solid_edges):
        body += _badge(_letter(index), "solid-edge-" + "-".join(sorted(edge)), str(index + 1), places[index])
    right = sorted(solid_edges.index(edges[index].solid) for index in WEDGE_NET_MARKS)
    width = max(solid_drawing.origin[0] + solid_drawing.width, drawing.origin[0] + drawing.width) + 30
    return FigureTask(
        "keil-kanten", "2017-9a", _svg(width, drawing.origin[1] + drawing.height + 18, body),
        tuple(str(index + 1) for index in range(len(solid_edges))),
        tuple(right),
        {"k": solid_edges.index(edges[WEDGE_NET_MARKS[0]].solid) + 1,
         "m": solid_edges.index(edges[WEDGE_NET_MARKS[1]].solid) + 1},
        tuple(places),
    )


def wedge_points_task() -> FigureTask:
    solid_drawing = WedgeDrawing(30, (110, 14))

    def solid_part(_net: NetDrawing) -> tuple[str, float, float]:
        zx, zy = solid_drawing.at(WEDGE_CORNER)
        mark = (
            f'<circle cx="{_n(zx)}" cy="{_n(zy)}" r="5" fill="currentColor"/>'
            f'<text x="{_n(zx - 9)}" y="{_n(zy + 2)}" font-size="15" font-style="italic" '
            f'font-weight="bold" text-anchor="end" fill="currentColor">Z</text>'
        )
        return (solid_drawing.body() + mark, 0, 0)

    return _net_points_task(
        "keil-ecken", "2017-9b", WEDGE, WEDGE_POINT_NET,
        lambda net: NetDrawing(net, 27, (22, solid_drawing.height + 44), turned=True),
        WEDGE_CORNER, mark=None, shaded=["slope"], extra=solid_part,
    )


# ── 2026-5: shapes put together from two pieces ──────────────────────────────

#: Eight shapes of six squares, lettered in this order.
SHAPES: tuple[tuple[str, ...], ...] = (
    ("###", "#..", "##."),
    ("###", "###"),
    (".#.", "###", ".#.", ".#."),
    ("##..", ".###", "..#."),
    ("##.", "###", "#.."),
    ("#...", "####", "#..."),
    (".##.", "####"),
    ("#.#", "###", "#.."),
)
CORNER_PIECE = ("##", "#.")
T_PIECE = ("###", ".#.")
DOMINO = ("##",)
SQUARE = 18


def _shape(rows: Sequence[str], left: float, top: float, fill: str) -> str:
    return "".join(
        f'<rect x="{_n(left + column * SQUARE)}" y="{_n(top + row * SQUARE)}" width="{SQUARE}" '
        f'height="{SQUARE}" fill="{fill}" {INK} stroke-width="1.2"/>'
        for column, row in sorted(squares(rows), key=lambda cell: (cell[1], cell[0]))
    )


def pieces_task(key: str, first: Sequence[str], second: Sequence[str]) -> FigureTask:
    """Which of the eight shapes can be put together from the two pieces."""
    slot_w, slot_h, top = 88, 104, 78
    body = (
        f'<g id="piece-1">{_shape(first, 16, 12, "#bdbdbd")}</g>'
        f'<g id="piece-2">{_shape(second, 16 + (len(first[0]) + 1) * SQUARE, 12, "#bdbdbd")}</g>'
        f'<line x1="8" y1="64" x2="{4 * slot_w + 8}" y2="64" {INK} stroke-width="0.8"/>'
    )
    centres = []
    for index, rows in enumerate(SHAPES):
        left = 16 + (index % 4) * slot_w + (4 - len(rows[0])) * SQUARE / 2
        slot_top = top + (index // 4) * slot_h
        shape_top = slot_top + (4 - len(rows)) * SQUARE / 2
        label_x = 16 + (index % 4) * slot_w + 2 * SQUARE
        body += (
            f'<g data-choice="{_letter(index)}" id="shape-{_letter(index)}">'
            f'{_shape(rows, left, shape_top, "#f4f4f4")}'
            f'<text x="{_n(label_x)}" y="{_n(slot_top + 4 * SQUARE + 16)}" font-size="13" '
            f'font-style="italic" text-anchor="middle" fill="currentColor">{_letter(index)}</text></g>'
        )
        centres.append((label_x, slot_top + 2 * SQUARE))
    fits = [splits_into(squares(rows), squares(first), squares(second)) for rows in SHAPES]
    return FigureTask(
        key, "2026-5", _svg(4 * slot_w + 16, top + 2 * slot_h, body),
        tuple(_letter(index) for index in range(len(SHAPES))),
        tuple(index for index, fit in enumerate(fits) if fit),
        {},
        tuple(centres),
    )


def tasks() -> list[FigureTask]:
    return [
        pieces_task("winkelstuecke", CORNER_PIECE, CORNER_PIECE),
        pieces_task("t-stueck", T_PIECE, DOMINO),
        cube_task(),
        net_edges_task(),
        net_points_task(),
        wedge_edges_task(),
        wedge_points_task(),
    ]
