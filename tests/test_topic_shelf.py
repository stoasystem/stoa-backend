"""Curriculum units, lessons and exercises sit on their topic's shelf (#513).

Their rows are keyed by their own id, with no topic in the key, so the roadmap,
the lesson page, lesson completion and the learning memory read every lesson or
exercise row to find one topic's. Each of these rows now also carries
`topic_shelf` and `topic_order`, the keys of GSI-TopicShelf, written by every
writer of the rows: the seed and the projection a curriculum publish writes.

The fields are derived from fields the row already has, so they stay out of the
exercise content hash (a backfill must not void a version) and out of the seed
hash (a table seeded before them is still in agreement with the code).
"""

from __future__ import annotations

import random
from typing import Any

import pytest
from boto3.dynamodb.conditions import Key

from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.services import curriculum_ops_service
from test_curriculum_publish_projection import (
    LESSON_ID,
    OPERATOR,
    _exercise,
    _payload,
    _publish,
    install_seeded_table,
)


def _shelf(table: FakeTable, kind: str, topic_id: str) -> list[dict[str, Any]]:
    return table.query(
        IndexName=practice_repo.TOPIC_SHELF_INDEX,
        KeyConditionExpression=Key("topic_shelf").eq(practice_repo.topic_shelf(kind, topic_id)),
    )["Items"]


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def test_a_published_lesson_and_its_exercises_sit_on_the_topic_shelf(table: FakeTable) -> None:
    _publish(_payload(_exercise(1), _exercise(3)))

    lessons = {row["lesson_id"] for row in _shelf(table, "LESSON", "brueche")}
    assert LESSON_ID in lessons
    exercises = [
        row["challenge_id"]
        for row in _shelf(table, "CHALLENGE", "brueche")
        if row["lesson_id"] == LESSON_ID
    ]
    assert exercises == [f"{LESSON_ID}-q01", f"{LESSON_ID}-q03"]
    # The fields leave the version alone: the practice reads still accept the rows.
    challenge = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert challenge is not None
    assert challenge["topic_shelf"] == "CHALLENGE#brueche"


def test_a_rollback_takes_the_dropped_exercises_off_the_shelf(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1), _exercise(2)))
    second = _publish(_payload(_exercise(3)), expected=first)
    assert [
        row["challenge_id"]
        for row in _shelf(table, "CHALLENGE", "brueche")
        if row["lesson_id"] == LESSON_ID
    ] == [f"{LESSON_ID}-q03"]

    curriculum_ops_service.rollback(
        LESSON_ID, first, OPERATOR, expected_published_version_id=second, reason="Fehler in q03"
    )

    assert [
        row["challenge_id"]
        for row in _shelf(table, "CHALLENGE", "brueche")
        if row["lesson_id"] == LESSON_ID
    ] == [f"{LESSON_ID}-q01", f"{LESSON_ID}-q02"]


def test_the_fields_are_outside_the_exercise_content_hash() -> None:
    row = next(
        r
        for r in seed_practice.seed_rows()
        if r["PK"] == "PRACTICE" and str(r["SK"]).startswith("CHALLENGE#")
    )
    assert row["topic_shelf"]
    bare = {k: v for k, v in row.items() if k not in practice_repo.TOPIC_SHELF_FIELDS}
    assert practice_repo.canonical_challenge_content_hash(
        row
    ) == practice_repo.canonical_challenge_content_hash(bare)


@pytest.mark.parametrize("knowledge_base", [None, seed_practice.KNOWLEDGE_BASE_LIVE])
def test_every_seeded_unit_lesson_and_exercise_sits_on_its_topic_shelf(
    knowledge_base: str | None,
) -> None:
    rows = seed_practice.seed_rows(knowledge_base=knowledge_base)
    curriculum = [
        row
        for row in rows
        if row["PK"] == "PRACTICE"
        and str(row["SK"]).split("#", 1)[0] in practice_repo.TOPIC_SHELF_KINDS
    ]
    assert curriculum
    for row in curriculum:
        kind = str(row["SK"]).split("#", 1)[0]
        assert row["topic_shelf"] == f"{kind}#{row['topic_id']}", row["SK"]
        assert row["topic_order"], row["SK"]
    others = [row for row in rows if row not in curriculum]
    assert others and not any("topic_shelf" in row for row in others)


@pytest.mark.parametrize("knowledge_base", [None, seed_practice.KNOWLEDGE_BASE_LIVE])
def test_the_fields_leave_the_seed_hash_as_it_was(knowledge_base: str | None) -> None:
    rows = seed_practice.seed_rows(knowledge_base=knowledge_base)
    bare = [
        {k: v for k, v in row.items() if k not in practice_repo.TOPIC_SHELF_FIELDS}
        for row in rows
    ]
    assert seed_practice.seed_hash(rows) == seed_practice.seed_hash(bare)


def test_a_row_without_a_topic_or_of_another_kind_sits_on_no_shelf() -> None:
    fields = practice_repo.topic_shelf_fields
    assert fields({"PK": "PRACTICE", "SK": "LESSON#l1", "lesson_id": "l1"}) == {}
    assert fields({"PK": "PRACTICE", "SK": "LESSON#l1", "topic_id": ""}) == {}
    assert fields({"PK": "PRACTICE", "SK": "TOPIC#t", "topic_id": "t"}) == {}
    assert fields({"PK": "PROGRESS#s", "SK": "LESSON#l1", "topic_id": "t"}) == {}
    assert fields({"PK": "PRACTICE", "SK": "UNIT#u1", "topic_id": "t"}) == {
        "topic_shelf": "UNIT#t",
        "topic_order": "UNIT#u1",
    }


#: Lesson ids that a plain `<lesson>#<order>` key would sort out of turn:
#: characters below and around `#`, prefixes of each other, and non-ASCII.
_AWKWARD_LESSON_IDS = [
    "a", "a!b", "a b", "a#b", "a$", "a$b", "a%", "a-b", "a\tb", "ab", "aä", "a\U0001f600",
    "", "b", "a!", "a#", "a##",
]


def _listed_order(rows: list[dict[str, Any]]) -> list[str]:
    """The order `list_exercises` gives: lesson id, then order, ties in key order."""
    by_key = sorted(rows, key=lambda row: f"CHALLENGE#{row['lesson_id']}#{row['challenge_id']}")
    by_lesson = sorted(by_key, key=lambda row: (row["lesson_id"], row["order"]))
    return [row["challenge_id"] for row in by_lesson]


def _stored_order(rows: list[dict[str, Any]]) -> list[str]:
    """The order GSI-TopicShelf gives: `topic_order` compared as UTF-8 bytes."""
    keyed = [
        (practice_repo.topic_shelf_fields(row)["topic_order"].encode("utf-8"), row)
        for row in rows
    ]
    return [row["challenge_id"] for _, row in sorted(keyed, key=lambda pair: pair[0])]


def _exercise_row(lesson_id: str, order: int, challenge_id: str) -> dict[str, Any]:
    return {
        "PK": "PRACTICE",
        "SK": f"CHALLENGE#{lesson_id}#{challenge_id}",
        "topic_id": "t",
        "lesson_id": lesson_id,
        "challenge_id": challenge_id,
        "order": order,
    }


def test_topic_order_lists_awkward_lesson_ids_as_list_exercises_does() -> None:
    rows = [
        _exercise_row(lesson_id, order, f"c{index}-{order}")
        for index, lesson_id in enumerate(_AWKWARD_LESSON_IDS)
        for order in (-3, 0, 2, 10, 11)
    ]
    assert _stored_order(rows) == _listed_order(rows)


def test_topic_order_lists_random_exercises_as_list_exercises_does() -> None:
    rng = random.Random(513)
    alphabet = "ab#$!-_ ä"
    for _ in range(200):
        rows = []
        for index in range(rng.randint(1, 12)):
            lesson_id = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 4)))
            rows.append(
                _exercise_row(
                    lesson_id, rng.randint(-5, 30), f"{rng.choice(alphabet)}{index}"
                )
            )
        assert _stored_order(rows) == _listed_order(rows), rows
