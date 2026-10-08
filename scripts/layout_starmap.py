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

Stability is documented in `docs/starmap-layout.md`; the rules it states are
implemented in `build_layout` below.

Usage:
    python scripts/layout_starmap.py                        # report only
    python scripts/layout_starmap.py --subject math
    python scripts/layout_starmap.py --relayout             # recompute every centre
    python scripts/layout_starmap.py --apply                # write the rows

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

from stoa.db.repositories import curriculum_ops_repo, practice_repo  # noqa: E402
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
    wanted = practice_repo.normal_subject_id(subject_id)

    def mine(row: Mapping[str, object]) -> bool:
        return practice_repo.normal_subject_id(row.get("subject_id", "")) == wanted

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
) -> Layout:
    """The whole map, reusing the previous nebula centres where the rules allow.

    The stability rules, stated in `docs/starmap-layout.md`:

      * Nebula centres and the normalising frame carry over from the previous
        layout. They are recomputed only when the set of topics changes, when
        `--relayout` is passed, or when carrying them over would break the
        clearance or push a point out of the frame.
      * A unit appearing or disappearing re-spirals only its own nebula. Every
        other nebula's centre, radius and stars come out identical.
      * A full recompute raises `layout_version` and records why.
    """
    if not subject.topics:
        raise LayoutError(f"subject {subject.subject_id} has no topic with an active lesson")

    topic_ids = [topic.topic_id for topic in subject.topics]
    radii = {topic.topic_id: nebula_radius(len(topic.units)) for topic in subject.topics}

    reason = ""
    if previous is None:
        reason = "no previous layout"
    elif relayout:
        reason = "relayout requested"
    elif set(previous.raw_centres) != set(topic_ids):
        reason = "the set of topics changed"

    if not reason and previous is not None:
        carried = _render(
            subject,
            layout_version=previous.layout_version,
            transform=previous.transform,
            raw_centres=previous.raw_centres,
            raw_radii=radii,
            reason=previous.relayout_reason,
            recomputed=False,
        )
        problems = validate_layout(carried)
        if not problems:
            return carried
        reason = f"a nebula outgrew the previous layout: {problems[0]}"

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
    """The rows whose stored values differ from the layout, and nothing else."""
    stored = {str(row.get("SK", "")): row for row in rows}
    plan: list[tuple[str, dict[str, object]]] = []
    for sort_key, attributes in sorted(desired_attributes(layout).items()):
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
    layout = build_layout(subject, previous_layout(subject_row), relayout=relayout)
    report = Report(
        subject_id=subject.subject_id,
        layout=layout,
        writes=plan_writes(layout, rows),
        problems=validate_layout(layout),
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
        + (f" (recomputed: {layout.relayout_reason})" if layout.recomputed else " (carried over)"),
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
    if report.applied:
        lines.append(f"  wrote {len(report.writes)} rows")
    elif report.writes:
        lines.append(f"  {len(report.writes)} rows would change; re-run with --apply to write them")
    else:
        lines.append("  nothing to write; the stored layout already matches")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="math")
    parser.add_argument("--relayout", action="store_true", help="recompute every nebula centre")
    parser.add_argument("--apply", action="store_true", help="write the coordinates")
    args = parser.parse_args()

    report = run(args.subject, apply=args.apply, relayout=args.relayout)
    print(describe(report))
    return 1 if report.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
