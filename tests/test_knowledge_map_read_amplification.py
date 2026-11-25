"""Card 133: what the student home page costs in DynamoDB round trips.

`GET /practice/knowledge-map/stars` read the whole `PRACTICE` partition - four
paged queries, two thousand lessons in production - on every request, though
the curriculum is the same for every student. It is kept per container now
(`curriculum_cache`) and asked after with one `GetItem` of the catalog stamp.

The counts are pinned exactly, in both directions, as in
`test_admin_user_list_read_amplification.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.db import table as db_table
from stoa.services import curriculum_cache
from test_curriculum_publish_projection import (
    LESSON_ID,
    _exercise,
    _payload,
    _publish,
    install_seeded_table,
)
from test_curriculum_reads import SMALL, _client, _get, _table

#: The profile, read by the authorization dependency and by the reader's locale.
PROFILE_READS = 2
#: Subjects, topics, units and lessons.
CURRICULUM_QUERIES = 4
#: Progress, attempts, star quiz outcomes and review cards.
STUDENT_QUERIES = 4
STAMP_READS = 1


def _partition(condition: Any) -> str | None:
    expression = condition.get_expression()
    if expression["operator"] == "=" and getattr(expression["values"][0], "name", "") == "PK":
        return str(expression["values"][1])
    for value in expression["values"]:
        if hasattr(value, "get_expression"):
            found = _partition(value)
            if found:
                return found
    return None


def _round_trips(table: Any, ask: Any) -> tuple[dict[str, int], list[str]]:
    """What one request asked the table: calls by operation, and the partitions queried."""
    table.calls.clear()
    table.requests.clear()
    ask()
    queried = [
        _partition(request["KeyConditionExpression"])
        for operation, request in table.requests
        if operation == "query"
    ]
    return dict(table.calls), [str(pk) for pk in queried]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(curriculum_cache, "_clock", lambda: now[0])
    return now


def _stars(lesson: dict[str, Any]) -> Any:
    return lambda: _get("stars_around", lesson)


def test_stars_read_the_curriculum_once_and_then_only_the_stamp(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    table, lesson = _table(monkeypatch, SMALL)

    cold, cold_queried = _round_trips(table, _stars(lesson))
    warm, warm_queried = _round_trips(table, _stars(lesson))

    assert cold == {
        "get_item": PROFILE_READS + STAMP_READS,
        "query": CURRICULUM_QUERIES + STUDENT_QUERIES,
    }
    assert cold_queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert warm == {"get_item": PROFILE_READS + STAMP_READS, "query": STUDENT_QUERIES}
    assert "PRACTICE" not in warm_queried
    assert sorted(warm_queried) == sorted(
        f"{prefix}#student-1" for prefix in ("PROGRESS", "ATTEMPTS", "QUIZ", "REVIEW")
    )


def test_the_answer_is_the_same_from_the_kept_curriculum(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    _table_, lesson = _table(monkeypatch, SMALL)
    assert _get("stars_around", lesson) == _get("stars_around", lesson)
    assert _get("catalog", lesson) == _get("catalog", lesson)


def _retitle(table: Any, lesson: dict[str, Any], title: str) -> None:
    row = dict(table.rows[("PRACTICE", f"LESSON#{lesson['lesson_id']}")])
    row["title"] = title
    table.seed(row)


def _title(lesson: dict[str, Any]) -> str:
    catalog = _get("catalog", lesson)
    return next(item["title"] for item in catalog["lessons"] if item["id"] == lesson["lesson_id"])


def test_a_new_stamp_is_read_on_the_next_request(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    """What a publish writes: the next request reads the curriculum again."""
    table, lesson = _table(monkeypatch, SMALL)
    table.seed({**curriculum_cache.STAMP_KEY, "stamp": "v1"})
    _get("catalog", lesson)
    _retitle(table, lesson, "Neu veröffentlicht")

    held, held_queried = _round_trips(table, lambda: _title(lesson))
    assert "PRACTICE" not in held_queried
    assert _title(lesson) != "Neu veröffentlicht"

    table.seed({**curriculum_cache.STAMP_KEY, "stamp": "v2"})
    _calls, queried = _round_trips(table, lambda: _title(lesson))
    assert queried.count("PRACTICE") == CURRICULUM_QUERIES
    assert _title(lesson) == "Neu veröffentlicht"


@pytest.mark.parametrize(
    ("stamp", "ttl"),
    [(None, curriculum_cache.UNSTAMPED_TTL), ("v1", curriculum_cache.STAMPED_TTL)],
)
def test_nothing_is_kept_past_its_ttl(
    monkeypatch: pytest.MonkeyPatch, clock: list[float], stamp: str | None, ttl: float
) -> None:
    """A writer that writes no stamp is seen once the TTL has passed."""
    table, lesson = _table(monkeypatch, SMALL)
    if stamp:
        table.seed({**curriculum_cache.STAMP_KEY, "stamp": stamp})
    _get("catalog", lesson)
    _retitle(table, lesson, "Ohne Stempel")

    clock[0] += ttl - 1
    assert _title(lesson) != "Ohne Stempel"
    clock[0] += 1
    assert _title(lesson) == "Ohne Stempel"


def test_a_preview_reader_always_reads_the_table(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    table, lesson = _table(monkeypatch, SMALL)
    _get("catalog", lesson)

    def preview() -> None:
        response = _client("teacher").get("/practice/curriculum/catalog?includePreview=true")
        assert response.status_code == 200, response.text

    # Its exercise counts also read every lesson's challenges, as before.
    rounds = [_round_trips(table, preview)[1].count("PRACTICE") for _ in range(2)]
    assert rounds[0] == rounds[1] > CURRICULUM_QUERIES


def test_a_kept_catalog_cannot_be_changed_by_its_reader(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    from stoa.services import curriculum_service

    _table(monkeypatch, SMALL)
    first = curriculum_service.list_catalog(locale="de")
    first["lessons"][0]["title"] = "verändert"
    first["units"].clear()
    second = curriculum_service.list_catalog(locale="de")
    assert second["lessons"][0]["title"] != "verändert"
    assert second["units"]


def test_lessons_without_an_index_are_read_with_the_curriculum_and_kept(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    """A lesson row written before the exercise index: its challenges once, not per request."""
    table, lesson = _table(monkeypatch, SMALL)
    unindexed = [
        row
        for (pk, sk), row in table.rows.items()
        if pk == "PRACTICE" and sk.startswith("LESSON#") and row.get("unit_id") == lesson["unit_id"]
    ]
    assert unindexed
    for row in unindexed:
        table.seed({key: value for key, value in row.items() if key != "exercise_index"})

    def challenge_queries() -> int:
        return sum(
            1
            for operation, request in table.requests
            if operation == "query"
            and "CHALLENGE#" in str(request["KeyConditionExpression"].get_expression()["values"][1].get_expression()["values"][1])
        )

    _round_trips(table, _stars(lesson))
    assert challenge_queries() == len(unindexed)
    _round_trips(table, _stars(lesson))
    assert challenge_queries() == 0


def test_a_read_side_by_side_is_metered_for_its_request() -> None:
    from stoa.db import read_metering

    with read_metering.measuring() as meter:
        seen = curriculum_cache.run_all([read_metering._meter.get for _ in range(4)])
    assert seen == [meter] * 4


def test_a_worker_reads_the_real_table_through_the_gateway_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boto3 resource is not thread safe: a worker never touches the request's."""
    import boto3

    from stoa.db import table as db_table
    from stoa.db.repositories import practice_repo

    shared = boto3.session.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name="eu-central-2"
    ).resource("dynamodb").Table("stoa-main")
    monkeypatch.setattr(shared.meta.client, "query", _refuse_the_shared_resource)
    db_table.install(shared)
    client = _WireClient()
    monkeypatch.setattr(db_table, "client", lambda: client)

    assert curriculum_cache.thread_table() is None
    _here, first, second = curriculum_cache.run_all(
        [
            lambda: None,
            lambda: curriculum_cache.with_table(practice_repo.get_progress, "student-1"),
            lambda: curriculum_cache.with_table(practice_repo.list_attempts, "student-1"),
        ]
    )

    assert first == second == [{"PK": "P", "SK": "LESSON#a", "order": 2}, {"PK": "P", "SK": "LESSON#b"}]
    assert [request["TableName"] for request in client.requests] == ["stoa-main"] * 4
    by_partition: dict[str, list[dict[str, Any]]] = {}
    for request in client.requests:
        by_partition.setdefault(request["ExpressionAttributeValues"][":v0"]["S"], []).append(request)
    progress, attempts = by_partition["PROGRESS#student-1"], by_partition["ATTEMPTS#student-1"]
    assert progress[0]["KeyConditionExpression"] == "(#n0 = :v0 AND begins_with(#n1, :v1))"
    assert progress[0]["ExpressionAttributeValues"][":v1"] == {"S": "LESSON#"}
    assert progress[1]["ExclusiveStartKey"] == {"PK": {"S": "P"}, "SK": {"S": "LESSON#a"}}
    assert [request.get("ConsistentRead") for request in attempts] == [True, True]


def _refuse_the_shared_resource(**_request: Any) -> Any:
    raise AssertionError("a worker read through the shared resource")


class _WireClient:
    """A low-level client: wire format in and out, two pages per query."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def query(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        if "ExclusiveStartKey" not in request:
            return {
                "Items": [{"PK": {"S": "P"}, "SK": {"S": "LESSON#a"}, "order": {"N": "2"}}],
                "LastEvaluatedKey": {"PK": {"S": "P"}, "SK": {"S": "LESSON#a"}},
            }
        return {"Items": [{"PK": {"S": "P"}, "SK": {"S": "LESSON#b"}}]}


# -- a publish writes the stamp ---------------------------------------------------------


def _published_table(monkeypatch: pytest.MonkeyPatch) -> Any:
    table = install_seeded_table(monkeypatch)
    table.seed(
        {
            "PK": "USER#student-1",
            "SK": "PROFILE",
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "grade": "Grade 6",
        }
    )
    return table


def _practice_set_ids() -> list[str]:
    response = _client("student").get(
        "/practice/knowledge-map/stars", params={"subjectId": "math", "around": "brueche-u2"}
    )
    assert response.status_code == 200, response.text
    focus = next(star for star in response.json()["stars"] if star["unitId"] == "brueche-u2")
    return [item["lessonId"] for item in focus["practiceSets"]]


def test_a_published_lesson_is_seen_at_once_by_every_container(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    """The clock stands still: only the stamp the publish writes can show the lesson."""
    table = _published_table(monkeypatch)
    assert LESSON_ID not in _practice_set_ids()
    other_container = curriculum_cache._kept

    _publish(_payload(_exercise(1)))

    stamp = table.get_item(Key=dict(curriculum_cache.STAMP_KEY))["Item"]
    assert stamp["entity_type"] == curriculum_cache.STAMP_ENTITY
    monkeypatch.setattr(curriculum_cache, "_kept", other_container)
    assert LESSON_ID in _practice_set_ids()


def test_a_publish_stands_when_its_stamp_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, clock: list[float]
) -> None:
    table = _published_table(monkeypatch)
    real_put = db_table.put

    def refuse_the_stamp(**request: Any) -> Any:
        if request["Item"]["PK"] == curriculum_cache.STAMP_KEY["PK"]:
            raise db_table.TableUnavailable("stamp")
        return real_put(**request)

    monkeypatch.setattr(curriculum_cache.db_table, "put", refuse_the_stamp)

    _publish(_payload(_exercise(1)))

    assert "Item" not in table.get_item(Key=dict(curriculum_cache.STAMP_KEY))
    assert table.get_item(Key={"PK": "PRACTICE", "SK": f"LESSON#{LESSON_ID}"}).get("Item")
    assert LESSON_ID in _practice_set_ids()
