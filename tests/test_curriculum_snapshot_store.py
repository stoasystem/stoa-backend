"""#669: a container without the curriculum loads the stored copy, not the partition.

Each Lambda container keeps the student curriculum (`curriculum_cache`, card
133); one that had none paged the whole `PRACTICE` partition, some two seconds
in production. The first container to page it under a stamp now stores a
compressed copy keyed by that stamp (`curriculum_snapshot_store`), and every
other container loads that instead. A container is played here by `forget()`:
the same table, nothing kept.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from boto3.dynamodb.types import Binary

from stoa.services import curriculum_cache, curriculum_snapshot_store
from test_curriculum_reads import SMALL, _client, _get, _table
from test_knowledge_map_read_amplification import CURRICULUM_QUERIES, _retitle, _round_trips

STAMP = "v1"
NOW = 1_800_000_000.0


@pytest.fixture
def clocks(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    monotonic, wall = [1000.0], [NOW]
    monkeypatch.setattr(curriculum_cache, "_clock", lambda: monotonic[0])
    monkeypatch.setattr(curriculum_cache, "_wall", lambda: wall[0])
    return {"monotonic": monotonic, "wall": wall}


def _stamped(monkeypatch: pytest.MonkeyPatch, stamp: str = STAMP) -> tuple[Any, dict[str, Any]]:
    table, lesson = _table(monkeypatch, SMALL)
    _stamp(table, stamp)
    return table, lesson


def _stamp(table: Any, stamp: str, **fields: Any) -> None:
    table.seed({**curriculum_cache.STAMP_KEY, "stamp": stamp, **fields})


def _new_container() -> None:
    curriculum_cache.forget()


def _catalog(lesson: dict[str, Any]) -> Any:
    return lambda: _get("catalog", lesson)


def _title(lesson: dict[str, Any]) -> str:
    catalog = _get("catalog", lesson)
    return next(item["title"] for item in catalog["lessons"] if item["id"] == lesson["lesson_id"])


def _snapshot_rows(table: Any) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        key: row
        for key, row in table.rows.items()
        if row.get("entity_type") == curriculum_snapshot_store.ENTITY
    }


def _head(table: Any, stamp: str = STAMP) -> dict[str, Any]:
    key = curriculum_snapshot_store.head_key(stamp)
    return table.rows[(key["PK"], key["SK"])]


def _asked_for(table: Any, operation: str) -> list[str]:
    return [
        str(request["Key"]["SK"])
        for name, request in table.requests
        if name == operation
        and str(request["Key"]["PK"]) == curriculum_snapshot_store.PK
        and str(request["Key"]["SK"]).startswith("SNAPSHOT#")
    ]


# -- the three paths ----------------------------------------------------------------------


def test_a_miss_without_a_stored_copy_pages_the_partition_and_stores_it(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)

    _calls, queried = _round_trips(table, _catalog(lesson))

    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert f"SNAPSHOT#{STAMP}" in _asked_for(table, "get_item")
    head = _head(table)
    assert head["stamp"] == STAMP
    assert head["format"] == curriculum_snapshot_store.FORMAT
    assert head["parts"] == 1
    assert head["written_at"] == int(NOW)
    assert head["expires_at"] == int(NOW) + curriculum_snapshot_store.MAX_AGE + (
        curriculum_snapshot_store.EXPIRY_MARGIN
    )
    assert list(_snapshot_rows(table)) == [(head["PK"], head["SK"])]


def test_a_miss_with_a_stored_copy_reads_only_that(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    paged = _get("catalog", lesson)
    stars = _get("stars_around", lesson)
    _new_container()

    calls, queried = _round_trips(table, _catalog(lesson))

    assert "PRACTICE" not in queried
    assert _asked_for(table, "get_item") == [f"SNAPSHOT#{STAMP}"]
    assert "put_item" not in calls
    _new_container()
    assert _get("catalog", lesson) == paged
    _new_container()
    assert _get("stars_around", lesson) == stars


def test_a_large_copy_is_stored_in_parts_and_read_in_one_batch(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    monkeypatch.setattr(curriculum_snapshot_store, "PART_BYTES", 4_000)
    table, lesson = _stamped(monkeypatch)
    paged = _get("catalog", lesson)
    parts = int(_head(table)["parts"])
    assert parts > 2
    assert len(_snapshot_rows(table)) == parts
    _new_container()

    calls, queried = _round_trips(table, _catalog(lesson))

    assert "PRACTICE" not in queried
    assert calls["batch_get_item"] == 1
    _new_container()
    assert _get("catalog", lesson) == paged


def test_a_new_stamp_takes_a_new_copy(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    _get("catalog", lesson)
    _retitle(table, lesson, "Neu veröffentlicht")
    _stamp(table, "v2")
    _new_container()

    _calls, queried = _round_trips(table, lambda: _title(lesson))
    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert _head(table, "v2")

    _new_container()
    _calls, queried = _round_trips(table, lambda: _title(lesson))
    assert "PRACTICE" not in queried
    assert _asked_for(table, "get_item") == ["SNAPSHOT#v2"]
    _new_container()
    assert _title(lesson) == "Neu veröffentlicht"


def test_a_copy_under_another_stamp_is_never_asked_for(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    _get("catalog", lesson)
    _stamp(table, "v2")
    _new_container()

    _round_trips(table, _catalog(lesson))

    assert "SNAPSHOT#v1" not in _asked_for(table, "get_item")


def test_without_a_stamp_nothing_is_stored_or_asked_for(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _table(monkeypatch, SMALL)
    _get("catalog", lesson)
    _new_container()

    _calls, queried = _round_trips(table, _catalog(lesson))

    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert not _asked_for(table, "get_item")
    assert not _snapshot_rows(table)


# -- a copy that cannot be used ---------------------------------------------------------


def _drop_a_part(table: Any) -> None:
    head = _head(table)
    key = curriculum_snapshot_store.part_key(STAMP, head["write_id"], 1)
    del table.rows[(key["PK"], key["SK"])]


def _flip_a_byte(table: Any) -> None:
    head = _head(table)
    data = bytearray(head["data"])
    data[len(data) // 2] ^= 0xFF
    head["data"] = bytes(data)


def _wrong_format(table: Any) -> None:
    _head(table)["format"] = Decimal(curriculum_snapshot_store.FORMAT + 1)


def _not_gzip(table: Any) -> None:
    import hashlib

    head = _head(table)
    head["data"] = b"not gzip"
    head["parts"] = Decimal(1)
    head["digest"] = hashlib.sha256(b"not gzip").hexdigest()


@pytest.mark.parametrize("damage", [_drop_a_part, _flip_a_byte, _wrong_format, _not_gzip])
def test_a_copy_that_cannot_be_used_is_paged_past_and_replaced(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]], damage: Any
) -> None:
    monkeypatch.setattr(curriculum_snapshot_store, "PART_BYTES", 4_000)
    table, lesson = _stamped(monkeypatch)
    paged = _get("catalog", lesson)
    damage(table)
    broken = _head(table)["write_id"]
    _new_container()

    _calls, queried = _round_trips(table, _catalog(lesson))
    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert _head(table)["write_id"] != broken

    _new_container()
    _calls, queried = _round_trips(table, _catalog(lesson))
    assert "PRACTICE" not in queried
    _new_container()
    assert _get("catalog", lesson) == paged


def test_an_unreadable_head_pages_and_stores_nothing(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    real_get = table.get_item

    def refuse_the_head(**request: Any) -> Any:
        if str(request["Key"]["SK"]).startswith("SNAPSHOT#"):
            raise RuntimeError("throttled")
        return real_get(**request)

    monkeypatch.setattr(table, "get_item", refuse_the_head)

    _calls, queried = _round_trips(table, _catalog(lesson))

    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert not _snapshot_rows(table)


def test_an_old_copy_is_paged_past_and_replaced(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    """The bound for a writer that changes the curriculum without a new stamp."""
    table, lesson = _stamped(monkeypatch)
    _get("catalog", lesson)
    _retitle(table, lesson, "Ohne Stempel")

    clocks["wall"][0] += curriculum_snapshot_store.MAX_AGE - 1
    _new_container()
    assert _title(lesson) != "Ohne Stempel"

    clocks["wall"][0] += 1
    _new_container()
    assert _title(lesson) == "Ohne Stempel"
    assert _head(table)["written_at"] == int(clocks["wall"][0])
    _new_container()
    _calls, queried = _round_trips(table, lambda: _title(lesson))
    assert "PRACTICE" not in queried


def test_a_stamp_written_a_moment_ago_is_not_stored_yet(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    """The partition is read eventually consistently: rows a publish has just
    written might be missing, and a stored copy would keep them missing."""
    from datetime import UTC, datetime

    table, lesson = _table(monkeypatch, SMALL)
    written = datetime.fromtimestamp(NOW - curriculum_snapshot_store.SETTLE + 1, UTC)
    _stamp(table, STAMP, updated_at=written.isoformat())
    _get("catalog", lesson)
    assert not _snapshot_rows(table)

    clocks["wall"][0] += 1
    _new_container()
    _get("catalog", lesson)
    assert _head(table)


def test_the_first_of_two_racing_containers_keeps_its_copy(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    _get("catalog", lesson)
    first = _head(table)["write_id"]
    rows = curriculum_cache._rows(curriculum_cache.current())

    # The second paged while the first's head was not there yet.
    stored = curriculum_snapshot_store.store(STAMP, rows, replacing=None, table=table, now=NOW)

    assert stored is False
    assert _head(table)["write_id"] == first


def test_lessons_whose_challenges_could_not_be_read_are_not_stored(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, _lesson = _stamped(monkeypatch)
    rows = {
        "subjects": [],
        "topics": [],
        "units": [],
        "lessons": [],
        "challenges": {"lesson-1": RuntimeError("throttled")},
    }

    assert not curriculum_snapshot_store.store(STAMP, rows, replacing=None, table=table, now=NOW)
    assert not _snapshot_rows(table)


def test_a_preview_reader_reads_the_table_with_a_stored_copy_there(
    monkeypatch: pytest.MonkeyPatch, clocks: dict[str, list[float]]
) -> None:
    table, lesson = _stamped(monkeypatch)
    _get("catalog", lesson)
    assert _head(table)

    def preview() -> None:
        response = _client("teacher").get("/practice/curriculum/catalog?includePreview=true")
        assert response.status_code == 200, response.text

    for _ in range(2):
        _new_container()
        _calls, queried = _round_trips(table, preview)
        assert queried.count("PRACTICE") > CURRICULUM_QUERIES
        assert not _asked_for(table, "get_item")


# -- the encoding -------------------------------------------------------------------------


def test_every_value_the_table_holds_comes_back_as_it_went_in() -> None:
    row = {
        "PK": "PRACTICE",
        "SK": "LESSON#a",
        "order": Decimal("3"),
        "weight": Decimal("0.125"),
        "big": Decimal("1E+30"),
        "flag": True,
        "none": None,
        "tags": {"a", "b"},
        "counts": {Decimal("1"), Decimal("2.5")},
        "blob": b"\x00\x01",
        "wire": Binary(b"\xff"),
        "nested": {"list": [Decimal("1"), {"deep": ["x", None]}], "empty": {}},
        "text": "Brüche \u0000 und 分数",
    }
    rows = {
        "subjects": [row],
        "topics": [],
        "units": [],
        "lessons": [row, {"PK": "PRACTICE", "SK": "LESSON#b"}],
        "challenges": {"a": [row], "b": []},
    }

    back = curriculum_snapshot_store.decode(curriculum_snapshot_store.encode(rows))

    assert back == rows
    assert isinstance(back["lessons"][0]["wire"], Binary)
    assert isinstance(back["lessons"][0]["blob"], bytes)
    assert isinstance(back["lessons"][0]["order"], Decimal)


@pytest.mark.parametrize(
    "value", [{"\u0000n": "1"}, float("nan"), object()], ids=["tag_name", "nan", "object"]
)
def test_a_value_without_a_form_is_not_stored(value: Any) -> None:
    rows = {"subjects": [{"x": value}], "topics": [], "units": [], "lessons": [], "challenges": {}}
    with pytest.raises(curriculum_snapshot_store.Unstorable):
        curriculum_snapshot_store.encode(rows)


@pytest.mark.parametrize(
    "text",
    [
        b'{"subjects":[{"x":{"\\u0000q":"1"}}],"topics":[],"units":[],"lessons":[],"challenges":{}}',
        b'{"subjects":[],"topics":[],"units":[],"lessons":{},"challenges":{}}',
        b'{"subjects":[{"x":{"\\u0000n":"one"}}],"topics":[],"units":[],"lessons":[],"challenges":{}}',
        b"[]",
    ],
    ids=["unknown_tag", "shape", "bad_number", "not_a_map"],
)
def test_what_was_not_written_by_encode_is_broken(text: bytes) -> None:
    import gzip

    with pytest.raises(curriculum_snapshot_store.Broken):
        curriculum_snapshot_store.decode(gzip.compress(text))


def test_a_truncated_copy_is_broken() -> None:
    rows = {"subjects": [], "topics": [], "units": [], "lessons": [], "challenges": {}}
    blob = curriculum_snapshot_store.encode(rows)
    with pytest.raises(curriculum_snapshot_store.Broken):
        curriculum_snapshot_store.decode(blob[:-4])
