#!/usr/bin/env python
"""Compute one subject's starmap offline and write it back as normalised 2D points.

A subject is a starmap, a topic is a nebula, a unit is a star in that nebula and
a skill point is a speck beside its star (stoasystem/stoa-frontend#72, 2026-09-28,
which retired the sphere: there is no `lat`, no `lng`, no equal-area projection
and no spherical cap packing here). The frontend only renders; it runs no force
layout and computes no coordinates, so everything it needs has to be in the rows.

What it writes:

  TOPIC#<id>    x, y, radius, layout_version
  UNIT#<id>     x, y, nebula_id, layout_version
  SKILL#<id>    x, y, unit_id's offset, layout_version
  SUBJECT#<id>  layout_version, starmap_layout

Every coordinate is in `[0, 1]` in one shared normalised frame, so a nebula's
radius and a star's position are in the same units.

Determinism, which the frontend depends on more than it looks:

  * Topics are laid out in `(order, topic_id)` order, units in `(order, unit_id)`
    order, before anything is computed.
  * The one random draw - the jitter that breaks the symmetry of the initial
    ring - comes from `random.Random(SEED)` with SEED fixed below.
  * Coordinates are rounded to COORD_DIGITS before they are compared or written,
    so a re-run writes nothing.

Stability is documented in `docs/starmap-layout.md`. By default a star or
nebula that already has a position keeps it and only the new ones are placed
(`keep_placed_layout`, stoa-backend#376); the whole map is recomputed only with
`--relayout` (`build_layout`). When the new stars do not fit, the script says
which, writes nothing and exits 1.

Usage:
    python scripts/layout_starmap.py                        # report only
    python scripts/layout_starmap.py --subject math         # `mathematics` too
    python scripts/layout_starmap.py --apply                # place new stars, write
    python scripts/layout_starmap.py --relayout --apply     # move every star

The table and region come from the application settings, so `DYNAMODB_TABLE_NAME`
and `AWS_REGION` select which table is read and written.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.db.repositories import curriculum_ops_repo  # noqa: E402
from stoa.services import curriculum_service, practice_projection_service  # noqa: E402


SEED = 20260928
COORD_DIGITS = 6

GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))

# A nebula's area grows with the number of stars, so its radius grows with their
# square root and the star density stays the same everywhere on the map.
NEBULA_RADIUS_PER_STAR = 1.0
# Two nebulae keep this multiple of their summed radii between their centres.
# The part above 1.0 is the growth headroom: a nebula that gains a star or two
# grows into it rather than into its neighbour.
NEBULA_CLEARANCE = 1.35
# How far an unrelated pair is asked to sit, as a multiple of the longest
# distance the prerequisite graph does constrain.
UNRELATED_SPREAD = 1.9
BASE_EDGE = 5.0

STRESS_ITERATIONS = 400
SEPARATION_PASSES = 400
# Separation overshoots by this much so that rounding the result to COORD_DIGITS
# cannot put a pair back under the clearance it was just given.
SEPARATION_SLACK = BASE_EDGE * 1e-4
# What two coordinates may differ by and still count as the same point.
COORD_TOLERANCE = 5.0 * 10.0**-COORD_DIGITS

# Stars fill this much of their nebula, leaving the rim for the glow.
STAR_FILL = 0.78
# The least distance between two stars of one nebula, in raw units. The spiral
# keeps every pair at least this far apart; a star placed next to stars that are
# already on the map has to keep it too.
STAR_MIN_GAP = 0.5 * NEBULA_RADIUS_PER_STAR
# How many steps across the frame a new nebula's centre is searched on, when it
# has to fit between nebulae that may not move.
CENTRE_GRID_STEPS = 200
# Spiral slots tried for a new star before its nebula counts as full.
MAX_STAR_SLOTS = 10_000
# A skill point's offset from its star, in the same raw units.
SKILL_ORBIT = 0.22

# Share of the longest side left as margin when the raw layout is normalised.
FRAME_PAD = 0.04
# Extra raw space added around the content so a nebula that grows later still
# fits inside the same frame.
FRAME_HEADROOM = 0.12


class LayoutError(RuntimeError):
    """Raised when a subject cannot be laid out at all."""


# ── Input ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnitInput:
    unit_id: str
    topic_id: str
    order: int
    active_lessons: int


@dataclass(frozen=True)
class TopicInput:
    topic_id: str
    order: int
    units: tuple[UnitInput, ...]


@dataclass(frozen=True)
class SkillInput:
    skill_id: str
    unit_id: str
    sort_key: str


@dataclass(frozen=True)
class SubjectInput:
    subject_id: str
    sort_key: str
    topics: tuple[TopicInput, ...]
    skills: tuple[SkillInput, ...]
    prerequisites: Mapping[str, tuple[str, ...]]


# ── Output ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Nebula:
    topic_id: str
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class Star:
    unit_id: str
    nebula_id: str
    x: float
    y: float


@dataclass(frozen=True)
class SkillPoint:
    skill_id: str
    unit_id: str
    sort_key: str
    x: float
    y: float


@dataclass(frozen=True)
class Transform:
    offset_x: float
    offset_y: float
    scale: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (
            _rounded(x * self.scale + self.offset_x),
            _rounded(y * self.scale + self.offset_y),
        )

    def length(self, value: float) -> float:
        return _rounded(value * self.scale)


@dataclass(frozen=True)
class Layout:
    subject_id: str
    sort_key: str
    layout_version: str
    transform: Transform
    raw_centres: Mapping[str, tuple[float, float]]
    nebulae: tuple[Nebula, ...]
    stars: tuple[Star, ...]
    skill_points: tuple[SkillPoint, ...]
    relayout_reason: str = ""
    recomputed: bool = True
    # The sort keys this layout may write. None is every row it owns, which is
    # what a full layout does; keeping the placed stars writes only what it added.
    owned_keys: frozenset[str] | None = None
    added_stars: tuple[str, ...] = ()
    added_nebulae: tuple[str, ...] = ()


@dataclass(frozen=True)
class Placed:
    """What the rows already carry: the stars and nebulae that are on the map.

    Nebulae are keyed by topic id as `(x, y, radius)`, stars by unit id as
    `(x, y, nebula_id)` and skill points by sort key as `(x, y)`, all in the
    normalised frame they were written in.
    """

    nebulae: Mapping[str, tuple[float, float, float]]
    stars: Mapping[str, tuple[float, float, str]]
    skills: Mapping[str, tuple[float, float]]


@dataclass(frozen=True)
class PreviousLayout:
    layout_version: str
    transform: Transform
    raw_centres: Mapping[str, tuple[float, float]]
    relayout_reason: str = ""


@dataclass
class Report:
    subject_id: str
    layout: Layout
    writes: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    applied: bool = False


# ── Reading the subject ───────────────────────────────────────────────────


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, Decimal, float)):
        return int(value)
    try:
        return int(str(value))
    except ValueError:
        return default


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    raise LayoutError("a stored layout number is not a number")


def _prerequisites(subject_id: str, units: Sequence[Mapping[str, object]]) -> dict[str, tuple[str, ...]]:
    """What each unit requires first, from #56's service when it is there.

    Before #56 lands the service has no such reader and the unit rows have no
    `prerequisite_unit_ids`, so this answers nothing and the nebula graph has no
    edges - which the layout is required to survive.
    """
    reader = getattr(curriculum_service, "get_prerequisites", None)
    if callable(reader):
        stored = reader(subject_id)
        return {
            str(unit_id): tuple(str(before) for before in (requires or []))
            for unit_id, requires in sorted(dict(stored).items())
        }
    found: dict[str, tuple[str, ...]] = {}
    for unit in units:
        raw = unit.get("prerequisite_unit_ids")
        if isinstance(raw, (list, tuple)) and raw:
            found[str(unit["unit_id"])] = tuple(str(before) for before in raw)
    return found


def collect(subject_id: str) -> SubjectInput:
    """Read one subject's topics, units and skills, dropping the dark units."""
    rows = curriculum_ops_repo.list_practice_rows()
    wanted = curriculum_service.subject_key(subject_id)

    def mine(row: Mapping[str, object]) -> bool:
        return curriculum_service.subject_key(row.get("subject_id", "")) == wanted

    subject_rows = [r for r in rows if str(r.get("SK", "")).startswith("SUBJECT#") and mine(r)]
    if not subject_rows:
        raise LayoutError(f"no subject row for {subject_id}")
    subject_row = subject_rows[0]

    topic_rows = [r for r in rows if str(r.get("SK", "")).startswith("TOPIC#") and mine(r)]
    unit_rows = [r for r in rows if str(r.get("SK", "")).startswith("UNIT#") and mine(r)]
    lesson_rows = [r for r in rows if str(r.get("SK", "")).startswith("LESSON#")]
    skill_rows = [r for r in rows if str(r.get("SK", "")).startswith("SKILL#")]

    active: dict[str, int] = {}
    for lesson in lesson_rows:
        if practice_projection_service.content_state(lesson) != "active":
            continue
        unit_id = str(lesson.get("unit_id", ""))
        if unit_id:
            active[unit_id] = active.get(unit_id, 0) + 1

    topic_ids = {str(r["topic_id"]) for r in topic_rows}
    units_by_topic: dict[str, list[UnitInput]] = {}
    for row in unit_rows:
        unit_id = str(row.get("unit_id", ""))
        topic_id = str(row.get("topic_id", ""))
        if not unit_id or topic_id not in topic_ids or active.get(unit_id, 0) == 0:
            continue
        units_by_topic.setdefault(topic_id, []).append(
            UnitInput(
                unit_id=unit_id,
                topic_id=topic_id,
                order=_as_int(row.get("order")),
                active_lessons=active[unit_id],
            )
        )

    topics: list[TopicInput] = []
    for row in topic_rows:
        topic_id = str(row["topic_id"])
        units = units_by_topic.get(topic_id, [])
        if not units:
            continue
        topics.append(
            TopicInput(
                topic_id=topic_id,
                order=_as_int(row.get("order")),
                units=tuple(sorted(units, key=lambda u: (u.order, u.unit_id))),
            )
        )
    topics.sort(key=lambda t: (t.order, t.topic_id))

    laid_out_units = {unit.unit_id for topic in topics for unit in topic.units}
    skills = [
        SkillInput(
            skill_id=str(row["skill_id"]),
            unit_id=str(row["unit_id"]),
            sort_key=str(row["SK"]),
        )
        for row in skill_rows
        if str(row.get("unit_id", "")) in laid_out_units and row.get("skill_id")
    ]
    skills.sort(key=lambda s: s.skill_id)

    return SubjectInput(
        subject_id=wanted,
        sort_key=str(subject_row["SK"]),
        topics=tuple(topics),
        skills=tuple(skills),
        prerequisites=_prerequisites(subject_id, unit_rows),
    )


def previous_layout(subject_row: Mapping[str, object]) -> PreviousLayout | None:
    stored = subject_row.get("starmap_layout")
    if not isinstance(stored, Mapping):
        return None
    transform = stored.get("transform")
    centres = stored.get("nebula_centres")
    version = stored.get("layout_version")
    if not isinstance(transform, Mapping) or not isinstance(centres, Mapping) or not version:
        return None
    if _as_int(stored.get("seed"), -1) != SEED:
        return None
    return PreviousLayout(
        layout_version=str(version),
        transform=Transform(
            offset_x=_as_float(transform["offset_x"]),
            offset_y=_as_float(transform["offset_y"]),
            scale=_as_float(transform["scale"]),
        ),
        raw_centres={
            str(topic_id): (_as_float(point["x"]), _as_float(point["y"]))
            for topic_id, point in sorted(centres.items())
            if isinstance(point, Mapping)
        },
        relayout_reason=str(stored.get("relayout_reason", "")),
    )


def _stored_number(value: object) -> float | None:
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    return None


def placed_positions(subject_id: str, rows: Sequence[Mapping[str, object]]) -> Placed:
    """The nebulae, stars and skill points of one subject that already have a place.

    A nebula is placed when its topic row has `x`, `y` and `radius`. A star is
    placed when its unit row has `x`, `y` and a `nebula_id` that is still its
    topic and that topic is placed; a star whose topic changed has to be placed
    again, in its new nebula. Every topic row of the subject counts, including a
    topic that is dark today, so a nebula that comes back finds its place free.
    """
    wanted = curriculum_service.subject_key(subject_id)

    def mine(row: Mapping[str, object]) -> bool:
        return curriculum_service.subject_key(row.get("subject_id", "")) == wanted

    nebulae: dict[str, tuple[float, float, float]] = {}
    for row in rows:
        if not str(row.get("SK", "")).startswith("TOPIC#") or not mine(row):
            continue
        x, y, radius = (_stored_number(row.get(name)) for name in ("x", "y", "radius"))
        if x is not None and y is not None and radius is not None:
            nebulae[str(row["topic_id"])] = (x, y, radius)

    stars: dict[str, tuple[float, float, str]] = {}
    for row in rows:
        if not str(row.get("SK", "")).startswith("UNIT#") or not mine(row):
            continue
        unit_id = str(row.get("unit_id", ""))
        topic_id = str(row.get("topic_id", ""))
        x, y = _stored_number(row.get("x")), _stored_number(row.get("y"))
        if x is None or y is None or str(row.get("nebula_id", "")) != topic_id:
            continue
        if topic_id in nebulae:
            stars[unit_id] = (x, y, topic_id)

    skills: dict[str, tuple[float, float]] = {}
    for row in rows:
        sort_key = str(row.get("SK", ""))
        if not sort_key.startswith("SKILL#") or str(row.get("unit_id", "")) not in stars:
            continue
        x, y = _stored_number(row.get("x")), _stored_number(row.get("y"))
        if x is not None and y is not None:
            skills[sort_key] = (x, y)
    return Placed(nebulae=nebulae, stars=stars, skills=skills)


# ── The layout itself ─────────────────────────────────────────────────────


def _rounded(value: float) -> float:
    return round(value + 0.0, COORD_DIGITS)


def _phase(token: str) -> float:
    """A fixed angle per topic, the same in every process.

    `hash()` is salted per interpreter, so a layout keyed on it would differ
    between two runs of this very script.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return (int.from_bytes(digest, "big") / float(1 << 64)) * 2.0 * math.pi


def nebula_radius(star_count: int) -> float:
    return NEBULA_RADIUS_PER_STAR * math.sqrt(star_count)


def nebula_edges(subject: SubjectInput) -> dict[tuple[str, str], int]:
    """How many prerequisite edges cross each pair of topics."""
    topic_of = {
        unit.unit_id: topic.topic_id for topic in subject.topics for unit in topic.units
    }
    weights: dict[tuple[str, str], int] = {}
    for unit_id, requires in sorted(subject.prerequisites.items()):
        here = topic_of.get(unit_id)
        if here is None:
            continue
        for before in requires:
            there = topic_of.get(before)
            if there is None or there == here:
                continue
            pair = (here, there) if here < there else (there, here)
            weights[pair] = weights.get(pair, 0) + 1
    return weights


def _target_distances(
    topic_ids: Sequence[str], weights: Mapping[tuple[str, str], int]
) -> list[list[float]]:
    """How far each pair of nebulae would like to be, in raw units.

    A heavier link is a shorter edge, and the shortest path through the graph
    gives every other pair a target. Pairs with no path at all - which is every
    pair while #56 has not landed - are pushed out to `UNRELATED_SPREAD` times
    the longest distance the graph did constrain.
    """
    size = len(topic_ids)
    index = {topic_id: position for position, topic_id in enumerate(topic_ids)}
    far = float("inf")
    distances = [[0.0 if i == j else far for j in range(size)] for i in range(size)]
    for (left, right), weight in sorted(weights.items()):
        if left not in index or right not in index:
            continue
        length = BASE_EDGE / math.sqrt(weight)
        i, j = index[left], index[right]
        distances[i][j] = distances[j][i] = min(distances[i][j], length)
    for through in range(size):
        for i in range(size):
            for j in range(size):
                relayed = distances[i][through] + distances[through][j]
                if relayed < distances[i][j]:
                    distances[i][j] = relayed
    finite = [
        distances[i][j] for i in range(size) for j in range(size) if i != j and distances[i][j] < far
    ]
    unrelated = max(finite) * UNRELATED_SPREAD if finite else BASE_EDGE
    for i in range(size):
        for j in range(size):
            if i != j and distances[i][j] == far:
                distances[i][j] = unrelated
    return distances


def _initial_ring(size: int) -> list[tuple[float, float]]:
    """A ring, nudged by the seeded draw so no two targets start identical."""
    draw = random.Random(SEED)
    jitter = BASE_EDGE * 0.05
    radius = BASE_EDGE * max(1.0, size / (2.0 * math.pi))
    points: list[tuple[float, float]] = []
    for position in range(size):
        angle = 2.0 * math.pi * position / max(size, 1)
        points.append(
            (
                radius * math.cos(angle) + draw.uniform(-jitter, jitter),
                radius * math.sin(angle) + draw.uniform(-jitter, jitter),
            )
        )
    return points


def _stress_majorise(
    points: list[tuple[float, float]], distances: list[list[float]]
) -> list[tuple[float, float]]:
    """Stress majorisation (SMACOF), weighted the Kamada-Kawai way.

    Chosen over a force-directed step because it has no step size, no cooling
    schedule and no stopping rule to tune: a fixed iteration count from a fixed
    start is the whole of its state, which is what makes the map reproducible.
    """
    size = len(points)
    if size < 2:
        return list(points)
    weights = [
        [0.0 if i == j else 1.0 / (distances[i][j] ** 2) for j in range(size)] for i in range(size)
    ]
    current = list(points)
    for _step in range(STRESS_ITERATIONS):
        moved: list[tuple[float, float]] = []
        for i in range(size):
            total = 0.0
            sum_x = 0.0
            sum_y = 0.0
            for j in range(size):
                if i == j:
                    continue
                dx = current[i][0] - current[j][0]
                dy = current[i][1] - current[j][1]
                span = math.hypot(dx, dy) or 1e-9
                ratio = distances[i][j] / span
                sum_x += weights[i][j] * (current[j][0] + ratio * dx)
                sum_y += weights[i][j] * (current[j][1] + ratio * dy)
                total += weights[i][j]
            moved.append((sum_x / total, sum_y / total))
        current = moved
    return current


def _separate(
    points: list[tuple[float, float]], radii: Sequence[float]
) -> list[tuple[float, float]]:
    """Push overlapping nebulae apart until every pair clears NEBULA_CLEARANCE."""
    current = list(points)
    for _pass in range(SEPARATION_PASSES):
        moved = False
        for i, j in combinations(range(len(current)), 2):
            needed = NEBULA_CLEARANCE * (radii[i] + radii[j])
            dx = current[j][0] - current[i][0]
            dy = current[j][1] - current[i][1]
            span = math.hypot(dx, dy)
            if span >= needed:
                continue
            if span < 1e-9:
                angle = GOLDEN_ANGLE * i
                dx, dy, span = math.cos(angle), math.sin(angle), 1.0
            push = (needed - span) / 2.0 + SEPARATION_SLACK
            unit_x, unit_y = dx / span, dy / span
            current[i] = (current[i][0] - unit_x * push, current[i][1] - unit_y * push)
            current[j] = (current[j][0] + unit_x * push, current[j][1] + unit_y * push)
            moved = True
        if not moved:
            return current
    return current


def _star_offsets(topic_id: str, count: int, radius: float) -> list[tuple[float, float]]:
    """A golden-angle spiral: even, never a grid, innermost star first.

    The n-th star sits at `radius * STAR_FILL * sqrt(n / count)`, so the first
    unit of a topic is at the centre and the last one at the rim, and because
    the radius already grows with the square root of the count the gap between
    neighbouring stars is the same in a big nebula as in a small one.
    """
    phase = _phase(topic_id)
    span = radius * STAR_FILL
    return [
        (
            span * math.sqrt(position / count) * math.cos(position * GOLDEN_ANGLE + phase),
            span * math.sqrt(position / count) * math.sin(position * GOLDEN_ANGLE + phase),
        )
        for position in range(count)
    ]


def _skill_offsets(unit_id: str, count: int) -> list[tuple[float, float]]:
    phase = _phase(unit_id)
    return [
        (
            SKILL_ORBIT * math.cos(position * GOLDEN_ANGLE + phase),
            SKILL_ORBIT * math.sin(position * GOLDEN_ANGLE + phase),
        )
        for position in range(count)
    ]


def _frame(
    centres: Mapping[str, tuple[float, float]], radii: Mapping[str, float]
) -> Transform:
    """The scale and shift that put the raw layout in `[0, 1]`, once.

    It is stored with the layout and reused by every later incremental run. A
    frame recomputed from the current bounding box would shift the whole map
    whenever one star appeared, which is the thing stability is supposed to
    prevent.
    """
    if not centres:
        raise LayoutError("nothing to normalise")
    lows_x = [centres[t][0] - radii[t] for t in centres]
    highs_x = [centres[t][0] + radii[t] for t in centres]
    lows_y = [centres[t][1] - radii[t] for t in centres]
    highs_y = [centres[t][1] + radii[t] for t in centres]
    min_x, max_x = min(lows_x), max(highs_x)
    min_y, max_y = min(lows_y), max(highs_y)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    headroom = FRAME_HEADROOM * max(width, height)
    min_x -= headroom
    min_y -= headroom
    width += 2.0 * headroom
    height += 2.0 * headroom
    usable = 1.0 - 2.0 * FRAME_PAD
    scale = usable / max(width, height)
    return Transform(
        offset_x=FRAME_PAD + (usable - width * scale) / 2.0 - min_x * scale,
        offset_y=FRAME_PAD + (usable - height * scale) / 2.0 - min_y * scale,
        scale=scale,
    )


def _render(
    subject: SubjectInput,
    *,
    layout_version: str,
    transform: Transform,
    raw_centres: Mapping[str, tuple[float, float]],
    raw_radii: Mapping[str, float],
    reason: str,
    recomputed: bool,
) -> Layout:
    nebulae: list[Nebula] = []
    stars: list[Star] = []
    star_points: dict[str, tuple[float, float]] = {}
    for topic in subject.topics:
        centre = raw_centres[topic.topic_id]
        radius = raw_radii[topic.topic_id]
        x, y = transform.apply(*centre)
        nebulae.append(Nebula(topic.topic_id, x, y, transform.length(radius)))
        offsets = _star_offsets(topic.topic_id, len(topic.units), radius)
        for unit, (dx, dy) in zip(topic.units, offsets, strict=True):
            star_x, star_y = transform.apply(centre[0] + dx, centre[1] + dy)
            stars.append(Star(unit.unit_id, topic.topic_id, star_x, star_y))
            star_points[unit.unit_id] = (centre[0] + dx, centre[1] + dy)

    by_unit: dict[str, list[SkillInput]] = {}
    for skill in subject.skills:
        by_unit.setdefault(skill.unit_id, []).append(skill)
    points: list[SkillPoint] = []
    for unit_id, owned in sorted(by_unit.items()):
        anchor = star_points.get(unit_id)
        if anchor is None:
            continue
        for skill, (dx, dy) in zip(owned, _skill_offsets(unit_id, len(owned)), strict=True):
            x, y = transform.apply(anchor[0] + dx, anchor[1] + dy)
            points.append(SkillPoint(skill.skill_id, unit_id, skill.sort_key, x, y))
    points.sort(key=lambda p: p.skill_id)

    return Layout(
        subject_id=subject.subject_id,
        sort_key=subject.sort_key,
        layout_version=layout_version,
        transform=transform,
        raw_centres=dict(raw_centres),
        nebulae=tuple(nebulae),
        stars=tuple(stars),
        skill_points=tuple(points),
        relayout_reason=reason,
        recomputed=recomputed,
    )


def _next_version(previous: PreviousLayout | None) -> str:
    if previous is None:
        return "L1"
    digits = previous.layout_version.lstrip("L")
    return f"L{_as_int(digits, 0) + 1}" if digits.isdigit() else "L1"


def validate_layout(layout: Layout) -> list[str]:
    """What is wrong with a finished layout; an empty list is a good one."""
    problems: list[str] = []
    for nebula in layout.nebulae:
        if not (0.0 <= nebula.x <= 1.0 and 0.0 <= nebula.y <= 1.0):
            problems.append(f"nebula {nebula.topic_id} is outside the frame")
    for star in layout.stars:
        if not (0.0 <= star.x <= 1.0 and 0.0 <= star.y <= 1.0):
            problems.append(f"star {star.unit_id} is outside the frame")
    for point in layout.skill_points:
        if not (0.0 <= point.x <= 1.0 and 0.0 <= point.y <= 1.0):
            problems.append(f"skill point {point.skill_id} is outside the frame")
    for one, other in combinations(layout.nebulae, 2):
        needed = NEBULA_CLEARANCE * (one.radius + other.radius)
        if math.hypot(one.x - other.x, one.y - other.y) < needed - COORD_TOLERANCE:
            problems.append(f"nebulae {one.topic_id} and {other.topic_id} are too close")
    return problems


def build_layout(
    subject: SubjectInput,
    previous: PreviousLayout | None = None,
    *,
    relayout: bool = False,
    reason: str = "",
) -> Layout:
    """The whole map, computed from nothing: every centre, the frame, every star.

    This is `--relayout`, and the first layout of a subject. It moves every star
    that is already on the map, raises `layout_version` and records why. Without
    `--relayout` the script keeps the placed stars instead (`keep_placed_layout`).
    """
    if not subject.topics:
        raise LayoutError(f"subject {subject.subject_id} has no topic with an active lesson")

    topic_ids = [topic.topic_id for topic in subject.topics]
    radii = {topic.topic_id: nebula_radius(len(topic.units)) for topic in subject.topics}

    if previous is None:
        reason = "no previous layout"
    elif relayout:
        reason = "relayout requested"
    reason = reason or "relayout requested"

    ring = _initial_ring(len(topic_ids))
    targets = _target_distances(topic_ids, nebula_edges(subject))
    centres = _separate(_stress_majorise(ring, targets), [radii[t] for t in topic_ids])
    raw_centres = dict(zip(topic_ids, centres, strict=True))
    transform = _frame(raw_centres, radii)
    return _render(
        subject,
        layout_version=_next_version(previous),
        transform=transform,
        raw_centres=raw_centres,
        raw_radii=radii,
        reason=reason,
        recomputed=True,
    )


# ── Keeping the stars that are already placed ─────────────────────────────


def _slot(topic_id: str, position: int, scale: float) -> tuple[float, float]:
    """The n-th spiral slot of a nebula, as an offset in the normalised frame.

    The same spiral `_star_offsets` draws. Because a nebula's radius grows with
    the square root of its star count, the n-th star sits
    `STAR_FILL * NEBULA_RADIUS_PER_STAR * sqrt(n)` raw units from the centre
    whatever the count is, so a slot does not move when the nebula gains a star.
    """
    span = STAR_FILL * NEBULA_RADIUS_PER_STAR * math.sqrt(position) * scale
    angle = position * GOLDEN_ANGLE + _phase(topic_id)
    return span * math.cos(angle), span * math.sin(angle)


def _free_slots(
    topic_id: str,
    centre: tuple[float, float],
    taken: Sequence[tuple[float, float]],
    count: int,
    scale: float,
) -> list[tuple[float, float]] | None:
    """The first `count` spiral slots that keep `STAR_MIN_GAP` from every star.

    Slots are tried innermost first. A slot a placed star already sits on is
    closer to it than the gap, so it is skipped, and new stars go into the
    spiral after the stars that are there.
    """
    gap = STAR_MIN_GAP * scale
    occupied = list(taken)
    found: list[tuple[float, float]] = []
    for position in range(MAX_STAR_SLOTS):
        if len(found) == count:
            break
        dx, dy = _slot(topic_id, position, scale)
        point = (_rounded(centre[0] + dx), _rounded(centre[1] + dy))
        if all(math.dist(point, other) >= gap for other in occupied):
            found.append(point)
            occupied.append(point)
    return found if len(found) == count else None


def _free_centre(
    radius: float,
    target: tuple[float, float],
    nebulae: Mapping[str, tuple[float, float, float]],
) -> tuple[float, float] | None:
    """The grid point nearest `target` where a nebula of `radius` fits.

    It has to lie wholly inside the frame and keep `NEBULA_CLEARANCE` from every
    nebula already there; none of those moves.
    """
    steps = CENTRE_GRID_STEPS
    candidates = [
        (_rounded(i / steps), _rounded(j / steps))
        for i in range(steps + 1)
        for j in range(steps + 1)
    ]
    candidates.sort(key=lambda point: (math.dist(point, target), point[1], point[0]))
    for point in candidates:
        if not (radius <= point[0] <= 1.0 - radius and radius <= point[1] <= 1.0 - radius):
            continue
        if all(
            math.dist(point, (x, y)) >= NEBULA_CLEARANCE * (radius + other)
            for x, y, other in nebulae.values()
        ):
            return point
    return None


def keep_placed_layout(
    subject: SubjectInput,
    previous: PreviousLayout | None,
    placed: Placed,
) -> tuple[Layout, list[str]]:
    """The map with every placed star and nebula where it is, and the rest added.

    The default without `--relayout` (stoa-backend#376). A star or nebula that
    already has a position keeps it digit for digit. A new star goes into the
    first free slots of its nebula's spiral, after the stars already there; its
    nebula's radius grows to hold it but its centre stays. A new nebula gets the
    free centre nearest the nebulae it shares prerequisites with (else nearest
    the middle of the map), without moving any other.

    What does not fit is returned as a problem - a nebula that would grow into a
    neighbour or past the frame, a new nebula with nowhere to go - and nothing is
    then written; `--relayout` is the way out. Returns the layout and those
    problems.
    """
    if not subject.topics:
        raise LayoutError(f"subject {subject.subject_id} has no topic with an active lesson")
    if not placed.nebulae:
        layout = build_layout(subject, previous, reason="nothing was placed yet")
        return layout, validate_layout(layout)
    if previous is None:
        layout = build_layout(subject, None)
        return layout, [
            "the rows carry star positions but the subject row has no starmap_layout "
            f"for seed {SEED}, so new stars cannot be put in the same frame; "
            "run with --relayout"
        ]

    transform = previous.transform
    scale = transform.scale
    nebulae: dict[str, tuple[float, float, float]] = dict(placed.nebulae)
    star_at: dict[str, tuple[float, float]] = {}
    owned: set[str] = set()
    added_stars: list[str] = []
    added_nebulae: list[str] = []
    grown: dict[str, list[str]] = {}
    problems: list[str] = []

    def stars_of(topic_id: str) -> list[tuple[float, float]]:
        """Every placed star of a nebula, dark ones included: they keep their slot."""
        return [(x, y) for x, y, nebula_id in placed.stars.values() if nebula_id == topic_id]

    def place_stars(topic: TopicInput, centre: tuple[float, float], new: list[UnitInput]) -> bool:
        points = _free_slots(topic.topic_id, centre, stars_of(topic.topic_id), len(new), scale)
        if points is None:
            problems.append(
                f"nebula {topic.topic_id}: no free spiral slot for "
                + ", ".join(unit.unit_id for unit in new)
            )
            return False
        for unit, point in zip(new, points, strict=True):
            star_at[unit.unit_id] = point
            added_stars.append(unit.unit_id)
            owned.add(f"UNIT#{unit.unit_id}")
        return True

    for topic in subject.topics:
        if topic.topic_id not in placed.nebulae:
            continue
        x, y, radius = placed.nebulae[topic.topic_id]
        new = [unit for unit in topic.units if unit.unit_id not in placed.stars]
        for unit in topic.units:
            if unit.unit_id in placed.stars:
                star_at[unit.unit_id] = placed.stars[unit.unit_id][:2]
        if not new or not place_stars(topic, (x, y), new):
            continue
        members = stars_of(topic.topic_id) + [star_at[unit.unit_id] for unit in new]
        reach = max(math.dist((x, y), point) for point in members)
        grown_radius = _rounded(
            max(radius, scale * nebula_radius(len(members)), reach / STAR_FILL)
        )
        nebulae[topic.topic_id] = (x, y, grown_radius)
        grown[topic.topic_id] = [unit.unit_id for unit in new]
        owned.add(f"TOPIC#{topic.topic_id}")

    edges = nebula_edges(subject)
    for topic in subject.topics:
        if topic.topic_id in placed.nebulae:
            continue
        radius = _rounded(scale * nebula_radius(len(topic.units)))
        linked = sorted(
            {
                other
                for pair in edges
                if topic.topic_id in pair
                for other in pair
                if other != topic.topic_id and other in nebulae
            }
        )
        target = (
            (
                sum(nebulae[other][0] for other in linked) / len(linked),
                sum(nebulae[other][1] for other in linked) / len(linked),
            )
            if linked
            else (0.5, 0.5)
        )
        centre = _free_centre(radius, target, nebulae)
        if centre is None:
            problems.append(
                f"new nebula {topic.topic_id} ({len(topic.units)} stars: "
                + ", ".join(unit.unit_id for unit in topic.units)
                + ") has no free space between the nebulae already placed"
            )
            continue
        nebulae[topic.topic_id] = (centre[0], centre[1], radius)
        added_nebulae.append(topic.topic_id)
        owned.add(f"TOPIC#{topic.topic_id}")
        place_stars(topic, centre, list(topic.units))

    for topic_id, new_units in sorted(grown.items()):
        x, y, radius = nebulae[topic_id]
        for other, (ox, oy, other_radius) in sorted(nebulae.items()):
            if other == topic_id:
                continue
            needed = NEBULA_CLEARANCE * (radius + other_radius)
            if math.dist((x, y), (ox, oy)) < needed - COORD_TOLERANCE:
                problems.append(
                    f"nebula {topic_id}: the new stars {', '.join(new_units)} grow it to "
                    f"radius {radius:.6f}, too close to nebula {other}"
                )
                break

    by_unit: dict[str, list[SkillInput]] = {}
    for skill in subject.skills:
        by_unit.setdefault(skill.unit_id, []).append(skill)
    points: list[SkillPoint] = []
    for unit_id, skills in sorted(by_unit.items()):
        anchor = star_at.get(unit_id)
        if anchor is None:
            continue
        for skill, (dx, dy) in zip(skills, _skill_offsets(unit_id, len(skills)), strict=True):
            if skill.sort_key in placed.skills:
                x, y = placed.skills[skill.sort_key]
            else:
                x, y = _rounded(anchor[0] + dx * scale), _rounded(anchor[1] + dy * scale)
                owned.add(skill.sort_key)
            points.append(SkillPoint(skill.skill_id, unit_id, skill.sort_key, x, y))
    points.sort(key=lambda p: p.skill_id)

    raw_centres = dict(previous.raw_centres)
    for topic_id in added_nebulae:
        x, y, _radius = nebulae[topic_id]
        raw_centres[topic_id] = (
            (x - transform.offset_x) / scale,
            (y - transform.offset_y) / scale,
        )
    if added_nebulae:
        owned.add(subject.sort_key)

    layout = Layout(
        subject_id=subject.subject_id,
        sort_key=subject.sort_key,
        layout_version=previous.layout_version,
        transform=transform,
        raw_centres=raw_centres,
        nebulae=tuple(
            Nebula(topic.topic_id, *nebulae[topic.topic_id])
            for topic in subject.topics
            if topic.topic_id in nebulae
        ),
        stars=tuple(
            Star(unit.unit_id, topic.topic_id, *star_at[unit.unit_id])
            for topic in subject.topics
            for unit in topic.units
            if unit.unit_id in star_at
        ),
        skill_points=tuple(points),
        relayout_reason=previous.relayout_reason,
        recomputed=False,
        owned_keys=frozenset(owned),
        added_stars=tuple(added_stars),
        added_nebulae=tuple(added_nebulae),
    )
    problems += [problem for problem in validate_layout(layout) if problem not in problems]
    return layout, problems


# ── Writing it back ───────────────────────────────────────────────────────


def _comparable(value: object) -> object:
    """One value in the form the table would hand it back, for comparison."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _comparable(member) for key, member in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_comparable(member) for member in value]
    return value


def layout_record(layout: Layout) -> dict[str, object]:
    return {
        "layout_version": layout.layout_version,
        "seed": SEED,
        "coordinate_digits": COORD_DIGITS,
        "relayout_reason": layout.relayout_reason,
        "transform": {
            "offset_x": layout.transform.offset_x,
            "offset_y": layout.transform.offset_y,
            "scale": layout.transform.scale,
        },
        "nebula_centres": {
            topic_id: {"x": point[0], "y": point[1]}
            for topic_id, point in sorted(layout.raw_centres.items())
        },
    }


def desired_attributes(layout: Layout) -> dict[str, dict[str, object]]:
    """Every row the layout owns, keyed by sort key."""
    wanted: dict[str, dict[str, object]] = {
        layout.sort_key: {
            "layout_version": layout.layout_version,
            "starmap_layout": layout_record(layout),
        }
    }
    for nebula in layout.nebulae:
        wanted[f"TOPIC#{nebula.topic_id}"] = {
            "x": nebula.x,
            "y": nebula.y,
            "radius": nebula.radius,
            "layout_version": layout.layout_version,
        }
    for star in layout.stars:
        wanted[f"UNIT#{star.unit_id}"] = {
            "x": star.x,
            "y": star.y,
            "nebula_id": star.nebula_id,
            "layout_version": layout.layout_version,
        }
    for point in layout.skill_points:
        wanted[point.sort_key] = {
            "x": point.x,
            "y": point.y,
            "layout_version": layout.layout_version,
        }
    return wanted


def plan_writes(
    layout: Layout, rows: Sequence[Mapping[str, object]]
) -> list[tuple[str, dict[str, object]]]:
    """The rows whose stored values differ from the layout, and nothing else.

    A layout that keeps the placed stars owns only the rows it added or grew;
    every other row is left exactly as it is.
    """
    stored = {str(row.get("SK", "")): row for row in rows}
    plan: list[tuple[str, dict[str, object]]] = []
    for sort_key, attributes in sorted(desired_attributes(layout).items()):
        if layout.owned_keys is not None and sort_key not in layout.owned_keys:
            continue
        row = stored.get(sort_key)
        if row is None:
            continue
        if all(_comparable(row.get(name)) == _comparable(value) for name, value in attributes.items()):
            continue
        plan.append((sort_key, attributes))
    return plan


def run(subject_id: str = "math", *, apply: bool = False, relayout: bool = False) -> Report:
    rows = curriculum_ops_repo.list_practice_rows()
    subject = collect(subject_id)
    subject_row = next(row for row in rows if str(row.get("SK", "")) == subject.sort_key)
    previous = previous_layout(subject_row)
    if relayout:
        layout = build_layout(subject, previous, relayout=True)
        problems = validate_layout(layout)
    else:
        layout, problems = keep_placed_layout(
            subject, previous, placed_positions(subject.subject_id, rows)
        )
    report = Report(
        subject_id=subject.subject_id,
        layout=layout,
        writes=plan_writes(layout, rows),
        problems=problems,
    )
    if apply and not report.problems:
        for sort_key, attributes in report.writes:
            curriculum_ops_repo.set_practice_attributes(sort_key, attributes)
        report.applied = True
    return report


def describe(report: Report) -> str:
    layout = report.layout
    lines = [
        f"subject {report.subject_id} — layout {layout.layout_version}"
        + (
            f" (recomputed: {layout.relayout_reason})"
            if layout.recomputed
            else f" (placed stars kept; {len(layout.added_stars)} new stars, "
            f"{len(layout.added_nebulae)} new nebulae)"
        ),
        f"  {len(layout.nebulae)} nebulae, {len(layout.stars)} stars, "
        f"{len(layout.skill_points)} skill points",
    ]
    for nebula in layout.nebulae:
        count = sum(1 for star in layout.stars if star.nebula_id == nebula.topic_id)
        lines.append(
            f"  nebula {nebula.topic_id:<20} centre ({nebula.x:.6f}, {nebula.y:.6f}) "
            f"radius {nebula.radius:.6f}  {count} stars"
        )
    for star in layout.stars:
        lines.append(
            f"  star   {star.unit_id:<20} ({star.x:.6f}, {star.y:.6f})  nebula {star.nebula_id}"
        )
    for point in layout.skill_points:
        lines.append(
            f"  skill  {point.skill_id:<20} ({point.x:.6f}, {point.y:.6f})  unit {point.unit_id}"
        )
    for problem in report.problems:
        lines.append(f"  PROBLEM: {problem}")
    if report.problems:
        lines.append(
            "  nothing written: "
            + (
                "the new stars do not fit around the placed ones; run with --relayout to "
                "recompute the whole map (it moves every star)"
                if not layout.recomputed
                else "the layout is not valid"
            )
        )
    elif report.applied:
        lines.append(f"  wrote {len(report.writes)} rows")
    elif report.writes:
        lines.append(f"  {len(report.writes)} rows would change; re-run with --apply to write them")
    else:
        lines.append("  nothing to write; the stored layout already matches")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="math")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--keep-placed",
        action="store_true",
        help="the default: keep every placed star and nebula, place only the new ones",
    )
    mode.add_argument(
        "--relayout", action="store_true", help="recompute the whole map; moves every star"
    )
    parser.add_argument("--apply", action="store_true", help="write the coordinates")
    args = parser.parse_args()

    report = run(args.subject, apply=args.apply, relayout=args.relayout)
    print(describe(report))
    return 1 if report.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
