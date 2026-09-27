"""The seeded mathematics topics are visible to a student in the curriculum catalog.

`scripts/seed_practice.py` writes five topics with `status: "available"`, which is
the practice domain's student-facing availability of a row, not a rollout state.
The catalog's state reader fell through `rollout_state`, `content_state` and then
`status`, so every seeded topic read as `available`, not `active`, and was hidden
from students: `/practice/curriculum/catalog?subjectId=mathematics` answered 0
topics and 0 units while `includePreview` (teachers and admins) showed all five.
stoasystem/stoa-backend#53.

Only the two publishing attributes are rollout states now; a row without them is
active, as a row without any state always was.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.services import curriculum_service, practice_projection_service


def _seed() -> dict[str, list[dict[str, Any]]]:
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
    return {
        "subjects": [dict(seed_practice.SUBJECT)],
        "topics": topics,
        "units": units,
        "lessons": lessons,
        "challenges": challenges,
    }


def _install(monkeypatch: pytest.MonkeyPatch, rows: dict[str, list[dict[str, Any]]]) -> None:
    def same_subject(row: dict[str, Any], subject_id: str | None) -> bool:
        return subject_id is None or curriculum_service._normal_subject_id(
            row["subject_id"]
        ) == curriculum_service._normal_subject_id(subject_id)

    monkeypatch.setattr(practice_repo, "get_subjects", lambda: list(rows["subjects"]))
    monkeypatch.setattr(
        practice_repo,
        "get_topics",
        lambda subject_id=None: [t for t in rows["topics"] if same_subject(t, subject_id)],
    )
    monkeypatch.setattr(
        practice_repo,
        "get_units",
        lambda topic_id: [u for u in rows["units"] if u["topic_id"] == topic_id],
    )
    monkeypatch.setattr(
        practice_repo,
        "get_lessons",
        lambda topic_id=None, unit_id=None: [
            lesson
            for lesson in rows["lessons"]
            if (topic_id is None or lesson["topic_id"] == topic_id)
            and (unit_id is None or lesson["unit_id"] == unit_id)
        ],
    )
    monkeypatch.setattr(
        practice_repo,
        "get_challenges",
        lambda lesson_id: [c for c in rows["challenges"] if c["lesson_id"] == lesson_id],
    )


def test_every_seeded_topic_is_in_the_student_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _seed()
    _install(monkeypatch, rows)
    assert all(topic["status"] == "available" for topic in rows["topics"])

    catalog = curriculum_service.list_catalog(subject_id="mathematics")

    assert len(catalog["subjects"]) == 1
    assert len(catalog["topics"]) == 5
    assert len(catalog["units"]) == 10
    assert len(catalog["lessons"]) == 20
    assert {topic["rolloutState"] for topic in catalog["topics"]} == {"active"}
    assert [topic["id"] for topic in catalog["topics"]] == [t["topic_id"] for t in rows["topics"]]


def test_the_subject_alias_sees_the_same_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _seed())

    by_alias = curriculum_service.list_catalog(subject_id="math")
    by_name = curriculum_service.list_catalog(subject_id="mathematics")

    assert [t["id"] for t in by_alias["topics"]] == [t["id"] for t in by_name["topics"]]
    assert len(by_alias["units"]) == len(by_name["units"]) == 10


def test_a_published_state_still_governs_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: `rollout_state` hides a draft; `status` alone hides nothing."""
    rows = _seed()
    draft = {**rows["topics"][0], "topic_id": "draft-topic", "rollout_state": "draft", "order": 99}
    only_status = {**rows["topics"][0], "topic_id": "status-only", "status": "completed", "order": 98}
    rows["topics"].extend([draft, only_status])
    _install(monkeypatch, rows)

    student = curriculum_service.list_catalog(subject_id="mathematics")
    preview = curriculum_service.list_catalog(subject_id="mathematics", include_preview=True)

    student_ids = [t["id"] for t in student["topics"]]
    assert "draft-topic" not in student_ids
    assert "status-only" in student_ids
    assert "draft-topic" in [t["id"] for t in preview["topics"]]


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ({"status": "available"}, "active"),
        ({"status": "completed"}, "active"),
        ({}, "active"),
        ({"rollout_state": "foundation"}, "foundation"),
        ({"content_state": "Draft", "status": "available"}, "draft"),
    ],
)
def test_both_state_readers_ignore_status(row: dict[str, Any], state: str) -> None:
    """The catalog and the practice projection read the same two attributes."""
    assert curriculum_service._content_state(row) == state
    assert practice_projection_service._content_state(row) == state
