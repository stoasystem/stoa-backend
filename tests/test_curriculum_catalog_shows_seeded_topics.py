"""The seeded mathematics topics are visible to a student in the curriculum catalog.

`scripts/seed_practice.py` writes five topics with `status: "available"`, which is
the practice domain's student-facing availability of a row (`_lesson_status`
answers `completed` or `available`). The catalog's state reader fell through
`rollout_state`, `content_state` and then `status`, so every seeded topic read as
`available`, not `active`, and was hidden from students:
`/practice/curriculum/catalog?subjectId=mathematics` answered 0 topics and 0 units
while `includePreview` (teachers and admins) showed all five. stoasystem/stoa-backend#53.

A student-availability `status` is no longer read as a rollout state. A lifecycle
`status` - `draft`, `archived`, which the rollout contract lists for lessons and
exercises - still hides a row, so a row that only ever carried that keeps its
protection. Everything here goes through the real `practice_repo` against the
shared table double, seeded with the real seed builders.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.services import curriculum_service, practice_projection_service


def _seed_rows() -> list[dict[str, Any]]:
    """The rows `seed_practice.seed` would write, assembled the way it assembles them."""
    topics, units, lessons, challenges = [], [], [], []
    for build in (
        seed_practice._brueche_data,
        seed_practice._gleichungen_data,
        seed_practice._geometrie_data,
        seed_practice._prozent_data,
        seed_practice._textaufgaben_data,
    ):
        topic, topic_units, topic_lessons, topic_challenges = build()
        topics.append(topic)
        units.extend(topic_units)
        lessons.extend(topic_lessons)
        challenges.extend(topic_challenges)
    subject = seed_practice.SUBJECT
    rows: list[dict[str, Any]] = [{"PK": "PRACTICE", "SK": f"SUBJECT#{subject['subject_id']}", **subject}]
    rows += [{"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics]
    rows += [{"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units]
    rows += [{"PK": "PRACTICE", "SK": f"LESSON#{lesson['lesson_id']}", **lesson} for lesson in lessons]
    rows += seed_practice.prepare_challenge_items(challenges)
    return rows


def _seeded_table(monkeypatch: pytest.MonkeyPatch, *extra: dict[str, Any]) -> FakeTable:
    table = FakeTable()
    table.seed(*_seed_rows(), *extra)
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    return table


def test_every_seeded_topic_is_in_the_student_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    table = _seeded_table(monkeypatch)
    seeded_topics = [row for (_pk, sk), row in table.rows.items() if sk.startswith("TOPIC#")]
    assert {topic["status"] for topic in seeded_topics} == {"available"}

    catalog = curriculum_service.list_catalog(subject_id="mathematics")

    assert len(catalog["subjects"]) == 1
    assert len(catalog["topics"]) == 5
    assert len(catalog["units"]) == 10
    assert len(catalog["lessons"]) == 20
    assert {topic["rolloutState"] for topic in catalog["topics"]} == {"active"}
    assert sorted(topic["id"] for topic in catalog["topics"]) == sorted(
        topic["topic_id"] for topic in seeded_topics
    )


def test_a_lifecycle_status_alone_still_hides_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rows the rollout contract describes: `status` is their lifecycle state."""
    base = dict(seed_practice._brueche_data()[2][0])
    draft = {**base, "lesson_id": "lesson-draft", "status": "draft"}
    archived = {**base, "lesson_id": "lesson-archived", "status": "archived"}
    _seeded_table(
        monkeypatch,
        {"PK": "PRACTICE", "SK": "LESSON#lesson-draft", **draft},
        {"PK": "PRACTICE", "SK": "LESSON#lesson-archived", **archived},
        {"PK": "PRACTICE", "SK": "TOPIC#topic-draft", **seed_practice._brueche_data()[0], "topic_id": "topic-draft", "status": "draft"},
    )

    student = curriculum_service.list_catalog(subject_id="mathematics")
    preview = curriculum_service.list_catalog(subject_id="mathematics", include_preview=True)

    assert {lesson["id"] for lesson in student["lessons"]}.isdisjoint({"lesson-draft", "lesson-archived"})
    assert "topic-draft" not in {topic["id"] for topic in student["topics"]}
    assert curriculum_service.get_lesson_detail("lesson-draft") is None
    assert curriculum_service.get_lesson_detail("lesson-archived") is None
    assert {"lesson-draft", "lesson-archived"} <= {lesson["id"] for lesson in preview["lessons"]}
    assert curriculum_service.get_lesson_detail("lesson-draft", include_preview=True) is not None


def test_a_published_rollout_state_outranks_status(monkeypatch: pytest.MonkeyPatch) -> None:
    topic = dict(seed_practice._brueche_data()[0])
    _seeded_table(
        monkeypatch,
        {"PK": "PRACTICE", "SK": "TOPIC#topic-rollout-draft", **topic, "topic_id": "topic-rollout-draft", "rollout_state": "draft"},
    )

    student = curriculum_service.list_catalog(subject_id="mathematics")
    preview = curriculum_service.list_catalog(subject_id="mathematics", include_preview=True)

    assert "topic-rollout-draft" not in {t["id"] for t in student["topics"]}
    assert "topic-rollout-draft" in {t["id"] for t in preview["topics"]}


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ({"status": "available"}, "active"),
        ({"status": "completed"}, "active"),
        ({}, "active"),
        ({"status": "draft"}, "draft"),
        ({"status": "archived"}, "archived"),
        ({"rollout_state": "foundation", "status": "available"}, "foundation"),
        ({"content_state": "Draft", "status": "available"}, "draft"),
    ],
)
def test_both_state_readers_agree(row: dict[str, Any], state: str) -> None:
    assert curriculum_service._content_state(row) == state
    assert practice_projection_service.content_state(row) == state
