"""The offline starmap layout: one deterministic 2D map per subject.

stoasystem/stoa-backend#60. The frontend only renders what is written here; it
runs no force layout and computes no coordinates of its own. So every property
the renderer depends on has to hold in the stored rows: nebulae that do not
overlap, stars inside their own nebula, coordinates inside the unit square, and
the same answer every time the script is run.
"""

from __future__ import annotations

import hashlib
import json
import math
from itertools import combinations
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import layout_starmap, seed_practice
from stoa.db import table as db_table
from stoa.db.repositories import curriculum_ops_repo
from stoa.services import curriculum_service


def _seed_rows() -> list[dict[str, Any]]:
    """The rows `seed_practice.seed` would write, assembled the way it assembles them."""
    topics, units, lessons = [], [], []
    for build in (
        *seed_practice.TOPIC_BUILDERS,
        *seed_practice.RETIRED_BUILDERS,
    ):
        topic, topic_units, topic_lessons, _challenges = build()
        topics.append(topic)
        units.extend(topic_units)
        lessons.extend(topic_lessons)
    subject = seed_practice.SUBJECT
    rows: list[dict[str, Any]] = [
        {"PK": "PRACTICE", "SK": f"SUBJECT#{subject['subject_id']}", **subject}
    ]
    rows += [{"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics]
    rows += [{"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units]
    rows += [{"PK": "PRACTICE", "SK": f"LESSON#{le['lesson_id']}", **le} for le in lessons]
    return rows


def _made_up_rows(
    shape: dict[str, int],
    *,
    prerequisites: dict[str, list[str]] | None = None,
    skills: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """A subject built to order: `shape` maps a topic id to how many units it has."""
    rows: list[dict[str, Any]] = [
        {"PK": "PRACTICE", "SK": "SUBJECT#math", "subject_id": "math", "name": "Math"}
    ]
    for order, (topic_id, unit_count) in enumerate(sorted(shape.items()), start=1):
        rows.append(
            {
                "PK": "PRACTICE",
                "SK": f"TOPIC#{topic_id}",
                "topic_id": topic_id,
                "subject_id": "math",
                "title": topic_id,
                "order": order,
            }
        )
        for index in range(1, unit_count + 1):
            unit_id = f"{topic_id}-u{index}"
            unit: dict[str, Any] = {
                "PK": "PRACTICE",
                "SK": f"UNIT#{unit_id}",
                "unit_id": unit_id,
                "topic_id": topic_id,
                "subject_id": "math",
                "title": unit_id,
                "order": index,
            }
            if prerequisites and unit_id in prerequisites:
                unit["prerequisite_unit_ids"] = list(prerequisites[unit_id])
            rows.append(unit)
            rows.append(
                {
                    "PK": "PRACTICE",
                    "SK": f"LESSON#{unit_id}-l1",
                    "lesson_id": f"{unit_id}-l1",
                    "unit_id": unit_id,
                    "topic_id": topic_id,
                    "subject_id": "math",
                    "title": f"{unit_id}-l1",
                    "order": 1,
                }
            )
    for skill_id, unit_id in sorted((skills or {}).items()):
        rows.append(
            {
                "PK": "PRACTICE",
                "SK": f"SKILL#{skill_id}",
                "skill_id": skill_id,
                "unit_id": unit_id,
                "subject_id": "math",
            }
        )
    return rows


def _table(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> FakeTable:
    table = FakeTable()
    table.seed(*rows)
    db_table.install(table)
    return table


def _centres(layout: layout_starmap.Layout) -> dict[str, tuple[float, float, float]]:
    return {n.topic_id: (n.x, n.y, n.radius) for n in layout.nebulae}


def _stars(layout: layout_starmap.Layout) -> dict[str, tuple[float, float, str]]:
    return {s.unit_id: (s.x, s.y, s.nebula_id) for s in layout.stars}


def test_two_runs_of_the_layout_agree_digit_for_digit(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, _seed_rows())
    first = layout_starmap.run("math")
    second = layout_starmap.run("math")

    assert _centres(first.layout) == _centres(second.layout)
    assert _stars(first.layout) == _stars(second.layout)
    assert first.writes == second.writes


def test_no_two_nebulae_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, _seed_rows())
    nebulae = layout_starmap.run("math").layout.nebulae

    assert len(nebulae) == 5
    for one, other in combinations(nebulae, 2):
        gap = math.hypot(one.x - other.x, one.y - other.y)
        assert gap > one.radius + other.radius, f"{one.topic_id} overlaps {other.topic_id}"


def test_an_empty_prerequisite_graph_still_lays_out_without_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before #56 lands there are no edges at all, and the map still has to work."""
    _table(monkeypatch, _made_up_rows({"a": 3, "b": 1, "c": 4, "d": 2}))
    layout = layout_starmap.run("math").layout

    assert [n.topic_id for n in layout.nebulae] == ["a", "b", "c", "d"]
    for one, other in combinations(layout.nebulae, 2):
        gap = math.hypot(one.x - other.x, one.y - other.y)
        needed = layout_starmap.NEBULA_CLEARANCE * (one.radius + other.radius)
        assert gap >= needed - layout_starmap.COORD_TOLERANCE


def test_related_nebulae_sit_closer_than_unrelated_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(
        monkeypatch,
        _made_up_rows(
            {"a": 2, "b": 2, "c": 2, "d": 2},
            prerequisites={"b-u1": ["a-u1"], "b-u2": ["a-u1", "a-u2"]},
        ),
    )
    centres = _centres(layout_starmap.run("math").layout)

    linked = math.dist(centres["a"][:2], centres["b"][:2])
    for unrelated in ("c", "d"):
        assert linked < math.dist(centres["a"][:2], centres[unrelated][:2])
        assert linked < math.dist(centres["b"][:2], centres[unrelated][:2])


def test_the_prerequisite_reader_is_used_once_it_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#56 adds `curriculum_service.get_prerequisites`; the links come from it then."""
    _table(monkeypatch, _made_up_rows({"a": 2, "b": 2, "c": 2, "d": 2}))
    monkeypatch.setattr(
        curriculum_service,
        "get_prerequisites",
        lambda _subject: {"b-u1": ["a-u1"], "b-u2": ["a-u1", "a-u2"]},
        raising=False,
    )
    centres = _centres(layout_starmap.run("math").layout)

    linked = math.dist(centres["a"][:2], centres["b"][:2])
    assert linked < math.dist(centres["a"][:2], centres["c"][:2])
    assert linked < math.dist(centres["a"][:2], centres["d"][:2])


def test_a_unit_with_no_active_lesson_is_not_laid_out(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _made_up_rows({"a": 2, "b": 2})
    for row in rows:
        if row["SK"] == "LESSON#a-u2-l1":
            row["rollout_state"] = "draft"
    _table(monkeypatch, rows)
    layout = layout_starmap.run("math").layout

    assert "a-u2" not in _stars(layout)
    assert sorted(_stars(layout)) == ["a-u1", "b-u1", "b-u2"]


def test_a_topic_whose_units_are_all_dark_gets_no_nebula(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _made_up_rows({"a": 2, "b": 2})
    for row in rows:
        if row["SK"].startswith("LESSON#a-"):
            row["rollout_state"] = "draft"
    _table(monkeypatch, rows)
    layout = layout_starmap.run("math").layout

    assert [n.topic_id for n in layout.nebulae] == ["b"]


def test_every_coordinate_is_normalised_into_the_unit_square(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _table(
        monkeypatch,
        _made_up_rows({"a": 6, "b": 1, "c": 3}, skills={"s1": "a-u1", "s2": "b-u1"}),
    )
    layout = layout_starmap.run("math").layout

    points = (
        [(n.x, n.y) for n in layout.nebulae]
        + [(s.x, s.y) for s in layout.stars]
        + [(p.x, p.y) for p in layout.skill_points]
    )
    assert points
    for x, y in points:
        assert 0.0 <= x <= 1.0, x
        assert 0.0 <= y <= 1.0, y
    assert layout_starmap.validate_layout(layout) == []


def test_every_star_sits_inside_its_own_nebula(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, _made_up_rows({"a": 7, "b": 2, "c": 1}))
    layout = layout_starmap.run("math").layout
    centres = _centres(layout)

    for star in layout.stars:
        cx, cy, radius = centres[star.nebula_id]
        assert math.hypot(star.x - cx, star.y - cy) <= radius + 1e-9


def test_stars_in_one_nebula_keep_their_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, _made_up_rows({"a": 9}))
    layout = layout_starmap.run("math").layout
    nebula = layout.nebulae[0]
    stars = [s for s in layout.stars if s.nebula_id == nebula.topic_id]

    floor = 0.5 * nebula.radius / math.sqrt(len(stars))
    for one, other in combinations(stars, 2):
        assert math.hypot(one.x - other.x, one.y - other.y) >= floor


def test_the_first_unit_of_a_topic_is_its_innermost_star(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _table(monkeypatch, _made_up_rows({"a": 5}))
    layout = layout_starmap.run("math").layout
    nebula = layout.nebulae[0]
    ordered = [s for s in layout.stars if s.nebula_id == "a"]

    spans = [math.hypot(s.x - nebula.x, s.y - nebula.y) for s in ordered]
    assert spans == sorted(spans)
    assert [s.unit_id for s in ordered] == [f"a-u{i}" for i in range(1, 6)]


def test_a_second_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _table(monkeypatch, _made_up_rows({"a": 3, "b": 2}, skills={"s1": "a-u1"}))
    first = layout_starmap.run("math", apply=True)
    assert first.writes

    writes_before = table.calls["update_item"]
    second = layout_starmap.run("math", apply=True)

    assert second.writes == []
    assert table.calls["update_item"] == writes_before
    assert second.layout.layout_version == first.layout.layout_version


def test_the_written_rows_carry_the_version_that_made_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _table(monkeypatch, _made_up_rows({"a": 2, "b": 2}, skills={"s1": "a-u1"}))
    layout = layout_starmap.run("math", apply=True).layout

    version = layout.layout_version
    assert table.rows[("PRACTICE", "SUBJECT#math")]["layout_version"] == version
    assert table.rows[("PRACTICE", "TOPIC#a")]["layout_version"] == version
    assert table.rows[("PRACTICE", "TOPIC#a")]["radius"] is not None
    assert table.rows[("PRACTICE", "UNIT#a-u1")]["nebula_id"] == "a"
    assert table.rows[("PRACTICE", "UNIT#a-u1")]["layout_version"] == version
    assert table.rows[("PRACTICE", "SKILL#s1")]["layout_version"] == version


def test_adding_a_unit_leaves_the_other_nebulae_where_they_were(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _made_up_rows({"a": 2, "b": 2, "c": 2})
    table = _table(monkeypatch, rows)
    before = layout_starmap.run("math", apply=True).layout

    table.seed(
        {
            "PK": "PRACTICE",
            "SK": "UNIT#a-u3",
            "unit_id": "a-u3",
            "topic_id": "a",
            "subject_id": "math",
            "title": "a-u3",
            "order": 3,
        },
        {
            "PK": "PRACTICE",
            "SK": "LESSON#a-u3-l1",
            "lesson_id": "a-u3-l1",
            "unit_id": "a-u3",
            "topic_id": "a",
            "subject_id": "math",
            "order": 1,
        },
    )
    after = layout_starmap.run("math", apply=True).layout

    assert after.layout_version == before.layout_version
    assert "a-u3" in _stars(after)
    for topic_id in ("b", "c"):
        assert _centres(after)[topic_id] == _centres(before)[topic_id]
    for unit_id, star in _stars(before).items():
        if not unit_id.startswith("a-"):
            assert _stars(after)[unit_id] == star


def test_a_new_topic_gets_a_nebula_without_moving_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _table(monkeypatch, _made_up_rows({"a": 2, "b": 2}))
    before = layout_starmap.run("math", apply=True).layout

    added = _made_up_rows({"c": 2})[1:]
    for row in added:
        if row["SK"] == "TOPIC#c":
            row["order"] = 3
    table.seed(*added)
    report = layout_starmap.run("math", apply=True)
    after = report.layout

    assert report.problems == []
    assert after.layout_version == before.layout_version
    assert [n.topic_id for n in after.nebulae] == ["a", "b", "c"]
    for topic_id in ("a", "b"):
        assert _centres(after)[topic_id] == _centres(before)[topic_id]
    assert {k: v for k, v in _stars(after).items() if not k.startswith("c-")} == _stars(before)
    assert layout_starmap.validate_layout(after) == []
    stored = table.rows[("PRACTICE", "SUBJECT#math")]["starmap_layout"]["nebula_centres"]
    assert sorted(stored) == ["a", "b", "c"]


def test_relayout_on_demand_bumps_the_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, _made_up_rows({"a": 2, "b": 2}))
    before = layout_starmap.run("math", apply=True).layout
    after = layout_starmap.run("math", apply=True, relayout=True).layout

    assert after.layout_version != before.layout_version


def test_skill_rows_orbit_the_unit_they_belong_to(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(
        monkeypatch,
        _made_up_rows({"a": 2}, skills={"s1": "a-u1", "s2": "a-u1", "s3": "a-u2"}),
    )
    layout = layout_starmap.run("math").layout
    stars = _stars(layout)

    assert [p.skill_id for p in layout.skill_points] == ["s1", "s2", "s3"]
    for point in layout.skill_points:
        star = stars[point.unit_id]
        assert 0.0 < math.hypot(point.x - star[0], point.y - star[1]) < 0.5


def test_a_subject_with_no_skill_rows_lays_out_anyway(monkeypatch: pytest.MonkeyPatch) -> None:
    """#58 may not have landed; a missing skill row is not an error."""
    _table(monkeypatch, _seed_rows())
    report = layout_starmap.run("math", apply=True)

    assert report.layout.skill_points == ()
    assert len(report.layout.stars) == 10


def test_a_skill_on_a_dark_unit_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _made_up_rows({"a": 2}, skills={"s1": "a-u1", "s2": "a-u2"})
    for row in rows:
        if row["SK"] == "LESSON#a-u2-l1":
            row["rollout_state"] = "draft"
    _table(monkeypatch, rows)
    layout = layout_starmap.run("math").layout

    assert [p.skill_id for p in layout.skill_points] == ["s1"]


def test_the_layout_ignores_the_order_the_table_hands_rows_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Input is sorted before it is laid out, so row order cannot move a star."""
    _table(monkeypatch, _made_up_rows({"a": 3, "b": 2, "c": 2}))
    straight = layout_starmap.run("math").layout

    forwards = curriculum_ops_repo.list_practice_rows
    monkeypatch.setattr(
        curriculum_ops_repo, "list_practice_rows", lambda: list(reversed(forwards()))
    )
    backwards = layout_starmap.run("math").layout

    assert _centres(straight) == _centres(backwards)
    assert _stars(straight) == _stars(backwards)


def test_the_order_field_decides_the_layout_not_the_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`order` runs against the alphabet here, and `order` is what has to win."""
    rows = _made_up_rows({"alpha": 3, "beta": 3, "gamma": 3})
    ranks = {"TOPIC#alpha": 3, "TOPIC#beta": 2, "TOPIC#gamma": 1}
    for row in rows:
        if row["SK"] in ranks:
            row["order"] = ranks[row["SK"]]
        if row["SK"].startswith("UNIT#"):
            row["order"] = 4 - int(str(row["unit_id"])[-1])
    _table(monkeypatch, rows)
    layout = layout_starmap.run("math").layout

    assert [n.topic_id for n in layout.nebulae] == ["gamma", "beta", "alpha"]
    nebula = next(n for n in layout.nebulae if n.topic_id == "alpha")
    spans = {
        star.unit_id: math.hypot(star.x - nebula.x, star.y - nebula.y)
        for star in layout.stars
        if star.nebula_id == "alpha"
    }
    assert spans["alpha-u3"] < spans["alpha-u2"] < spans["alpha-u1"]


def test_a_report_only_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _table(monkeypatch, _made_up_rows({"a": 2, "b": 2}))
    report = layout_starmap.run("math")

    assert report.writes
    assert report.applied is False
    assert table.calls["update_item"] == 0
    assert table.calls["put_item"] == 0


# ── Keeping the placed stars (stoa-backend#376) ───────────────────────────


def _new_star(topic_id: str, unit_id: str, *, order: int = 0) -> list[dict[str, Any]]:
    """A unit with one active lesson in the seed's `mathematics` subject.

    `order` 0 sorts it before the stars already there: a full layout would put it
    at the centre of its nebula and push the others out, so keeping them is
    something the default mode has to do on purpose.
    """
    return [
        {
            "PK": "PRACTICE",
            "SK": f"UNIT#{unit_id}",
            "unit_id": unit_id,
            "topic_id": topic_id,
            "subject_id": "mathematics",
            "title": unit_id,
            "order": order,
        },
        {
            "PK": "PRACTICE",
            "SK": f"LESSON#{unit_id}-l1",
            "lesson_id": f"{unit_id}-l1",
            "unit_id": unit_id,
            "topic_id": topic_id,
            "subject_id": "mathematics",
            "title": unit_id,
            "order": 1,
        },
    ]


_NEW_STARS = {"brueche": 2, "geometrie": 1, "gleichungen": 1, "prozentrechnung": 1}


def _placed_seed_table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """The ten ZAP stars placed and written, plus new stars with lessons and no place."""
    table = _table(monkeypatch, _seed_rows())
    placed = layout_starmap.run("math", apply=True)
    assert placed.problems == [] and len(placed.layout.stars) == 10
    for topic_id, count in sorted(_NEW_STARS.items()):
        for index in range(1, count + 1):
            table.seed(*_new_star(topic_id, f"{topic_id}-kb{index}"))
    return table


def _layout_fields(table: FakeTable) -> dict[str, dict[str, object]]:
    """Every position field the layout owns, per row, as the table stores it."""
    fields = ("x", "y", "radius", "nebula_id", "layout_version", "starmap_layout")
    return {
        str(sk): {name: row[name] for name in fields if name in row}
        for (_pk, sk), row in table.rows.items()
        if str(sk).split("#")[0] in {"SUBJECT", "TOPIC", "UNIT", "SKILL"}
    }


def test_the_default_keeps_every_placed_star_and_places_only_the_new_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _placed_seed_table(monkeypatch)
    before = _layout_fields(table)
    old_units = sorted(
        sk for sk, fields in before.items() if sk.startswith("UNIT#") and "x" in fields
    )
    assert len(old_units) == 10

    report = layout_starmap.run("math", apply=True)

    assert report.problems == []
    assert report.applied is True
    after = _layout_fields(table)
    for sort_key in old_units:
        assert after[sort_key] == before[sort_key], sort_key
    for sort_key, fields in before.items():
        if sort_key.startswith("TOPIC#") and "x" in fields:
            assert (after[sort_key]["x"], after[sort_key]["y"]) == (fields["x"], fields["y"])

    new_units = [f"{t}-kb{i}" for t, n in sorted(_NEW_STARS.items()) for i in range(1, n + 1)]
    assert sorted(report.layout.added_stars) == sorted(new_units)
    gap = layout_starmap.STAR_MIN_GAP * report.layout.transform.scale
    old_points = [(float(after[sk]["x"]), float(after[sk]["y"])) for sk in old_units]
    for unit_id in new_units:
        row = after[f"UNIT#{unit_id}"]
        assert row["nebula_id"] == unit_id.split("-kb")[0]
        point = (float(row["x"]), float(row["y"]))
        for other in old_points:
            assert math.dist(point, other) >= gap, unit_id
        nebula = after[f"TOPIC#{row['nebula_id']}"]
        centre = (float(nebula["x"]), float(nebula["y"]))
        assert math.dist(point, centre) <= float(nebula["radius"])
    assert layout_starmap.validate_layout(report.layout) == []


def test_keeping_the_placed_stars_gives_the_same_answer_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [dict(row) for row in _placed_seed_table(monkeypatch).rows.values()]

    first_table = _table(monkeypatch, [dict(row) for row in rows])
    first = layout_starmap.run("math", apply=True)
    second_table = _table(monkeypatch, [dict(row) for row in rows])
    second = layout_starmap.run("math", apply=True)

    assert first.writes
    assert _stars(first.layout) == _stars(second.layout)
    assert _centres(first.layout) == _centres(second.layout)
    assert first.writes == second.writes
    assert _layout_fields(first_table) == _layout_fields(second_table)

    again = layout_starmap.run("math", apply=True)
    assert again.writes == []
    assert again.layout.added_stars == ()


def test_stars_that_do_not_fit_write_nothing_and_exit_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = _table(monkeypatch, _seed_rows())
    layout_starmap.run("math", apply=True)
    for index in range(1, 9):
        table.seed(*_new_star("brueche", f"brueche-kb{index}"))
    before = _layout_fields(table)
    writes_before = table.calls["update_item"]

    monkeypatch.setattr("sys.argv", ["layout_starmap.py", "--apply"])
    code = layout_starmap.main()

    assert code != 0
    assert table.calls["update_item"] == writes_before
    assert _layout_fields(table) == before
    printed = capsys.readouterr().out
    assert "brueche-kb1" in printed
    assert "--relayout" in printed


def test_explicit_relayout_still_recomputes_the_whole_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _placed_seed_table(monkeypatch)
    before = _layout_fields(table)

    report = layout_starmap.run("math", apply=True, relayout=True)

    assert report.problems == []
    assert report.layout.recomputed is True
    assert report.layout.relayout_reason == "relayout requested"
    assert report.layout.layout_version == "L2"
    after = _layout_fields(table)
    assert any(
        after[sk] != fields for sk, fields in before.items() if sk.startswith("UNIT#") and "x" in fields
    )


def _fingerprint(report: layout_starmap.Report) -> str:
    layout = report.layout
    blob = {
        "version": layout.layout_version,
        "reason": layout.relayout_reason,
        "nebulae": [[n.topic_id, n.x, n.y, n.radius] for n in layout.nebulae],
        "stars": [[s.unit_id, s.nebula_id, s.x, s.y] for s in layout.stars],
        "skills": [[p.skill_id, p.x, p.y] for p in layout.skill_points],
        "writes": [[sort_key, sorted(attributes)] for sort_key, attributes in report.writes],
    }
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()


def test_relayout_matches_what_it_computed_before_376(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--relayout` is the old full layout, digit for digit.

    The fingerprints were taken from origin/main 2e7ab899, before the default
    changed; a full layout that drifts from them has changed behaviour.
    """
    rows = _made_up_rows(
        {"a": 3, "b": 2, "c": 4},
        prerequisites={"b-u1": ["a-u1"]},
        skills={"s1": "a-u1", "s2": "c-u2"},
    )
    table = _table(monkeypatch, rows)
    first = layout_starmap.run("math", apply=True, relayout=True)
    table.seed(*_made_up_rows({"d": 2})[1:])
    second = layout_starmap.run("math", apply=True, relayout=True)
    _table(monkeypatch, _seed_rows())
    seed = layout_starmap.run("math", relayout=True)

    assert _fingerprint(first) == "c879807549e1a44d13a7fa6bae928eed6ac7c0db3a35589234721e913c4cb8aa"
    assert _fingerprint(second) == "ddfe61cd432e8ec854ac23c677201affce869bf168784d6105510826aaa9f427"
    assert _fingerprint(seed) == "6879b570e7aa92ab47cfb62cb53119ccbfa6d6cbcfba9fd7d5aa7c5507f84aa2"


def test_the_default_subject_math_finds_the_seeded_mathematics_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seed writes `mathematics`; `--subject` defaults to `math`. Both are one subject."""
    assert seed_practice.SUBJECT["subject_id"] == "mathematics"
    table = _table(monkeypatch, _seed_rows())
    monkeypatch.setattr("sys.argv", ["layout_starmap.py", "--apply"])

    assert layout_starmap.main() == 0
    subject_row = table.rows[("PRACTICE", "SUBJECT#mathematics")]
    assert subject_row["starmap_layout"]["layout_version"] == "L1"
    assert layout_starmap.run("mathematics").writes == []


def test_placed_rows_without_a_layout_record_ask_for_a_relayout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _table(monkeypatch, _made_up_rows({"a": 2, "b": 2}))
    layout_starmap.run("math", apply=True)
    table.rows[("PRACTICE", "SUBJECT#math")].pop("starmap_layout")
    writes_before = table.calls["update_item"]

    report = layout_starmap.run("math", apply=True)

    assert report.problems and "--relayout" in report.problems[0]
    assert report.applied is False
    assert table.calls["update_item"] == writes_before
