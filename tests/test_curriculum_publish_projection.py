"""A lesson published through the curriculum workflow is one students can read and answer.

`put_published_projection` wrote `PRACTICE/CHALLENGE#` rows with no content hash or
version, no lookup pointer, and no subject or topic. The practice reads hold every
challenge row to its content hash, so one published lesson made the lesson query and
the whole-subject exercise list raise, and `get_challenge` found nothing to answer.
Republishing or rolling back to a version with fewer exercises left the dropped ones
live. The tests stubbed the projection out, so none of this was ever exercised.

Everything here runs the real workflow and the real practice reads against one shared
table double, seeded with the real seed rows.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
import pytest

from fakes.dynamodb import FakeTable
from scripts import seed_practice
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.services import (
    answer_judging,
    curriculum_analytics_service,
    curriculum_ops_service,
    curriculum_service,
    lesson_quiz_service,
    practice_projection_service,
)


LESSON_ID = "zap-brueche-addieren-001"
OPERATOR = {
    "sub": "operator-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    },
}


def _seed_rows() -> list[dict[str, Any]]:
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
    rows: list[dict[str, Any]] = [
        {"PK": "PRACTICE", "SK": f"SUBJECT#{subject['subject_id']}", **subject}
    ]
    rows += [{"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t} for t in topics]
    rows += [{"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u} for u in units]
    rows += [{"PK": "PRACTICE", "SK": f"LESSON#{row['lesson_id']}", **row} for row in lessons]
    rows += seed_practice.prepare_challenge_items(challenges)
    return rows


def install_seeded_table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    """One table double holding the seed, behind both repositories the workflow uses."""
    table = FakeTable()
    table.seed(*_seed_rows())
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(curriculum_ops_repo, "get_table", lambda: table)
    monkeypatch.setattr(curriculum_analytics_service, "record_publish_event", lambda *a, **k: None)
    return table


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def _exercise(number: int, answer: str = "1", **extra: Any) -> dict[str, Any]:
    return {
        "exerciseId": f"{LESSON_ID}-q{number:02d}",
        "type": "text_input",
        "prompt": f"Berechne {number}/4 + {4 - number}/4.",
        "answerKey": answer,
        "explanation": f"{number}/4 + {4 - number}/4 = 4/4 = 1.",
        "difficulty": "practice",
        "skills": ["brueche-addieren"],
        **extra,
    }


def _payload(*exercises: dict[str, Any]) -> dict[str, Any]:
    return {
        "publicLessonId": LESSON_ID,
        "title": "Brüche addieren",
        "objective": "Gleichnamige Brüche addieren.",
        "subjectId": "math",
        "topicId": "brueche",
        "unitId": "brueche-u2",
        "gradeLevel": "grade_6_primary",
        "language": "de",
        "difficulty": "practice",
        "exercises": list(exercises),
    }


def _approved(payload: dict[str, Any]) -> str:
    version_id = curriculum_ops_service.create_lesson_draft(payload, OPERATOR)["versionId"]
    curriculum_ops_service.submit_review(LESSON_ID, version_id, OPERATOR)
    curriculum_ops_service.approve(LESSON_ID, version_id, OPERATOR)
    return version_id


def _publish(payload: dict[str, Any], expected: str | None = None) -> str:
    version_id = _approved(payload)
    curriculum_ops_service.publish(
        LESSON_ID, version_id, OPERATOR, expected_published_version_id=expected
    )
    return version_id


def _published_ids() -> list[str]:
    return [row["challenge_id"] for row in practice_repo.get_challenges(LESSON_ID)]


def test_a_published_lesson_is_readable_and_answerable(table: FakeTable) -> None:
    _publish(_payload(_exercise(1), _exercise(3)))

    rows = practice_repo.get_challenges(LESSON_ID)
    assert [row["challenge_id"] for row in rows] == [f"{LESSON_ID}-q01", f"{LESSON_ID}-q03"]

    # The whole-subject list still reads every seeded row next to the new ones.
    listed = curriculum_service.list_exercises(subject_id="math")["items"]
    assert {f"{LESSON_ID}-q01", f"{LESSON_ID}-q03", "brueche-l1-c1"} <= {
        item["id"] for item in listed
    }
    new = next(item for item in listed if item["id"] == f"{LESSON_ID}-q01")
    assert new["subjectId"] == "math"
    assert new["topicId"] == "brueche"
    assert "answerKey" not in new and "correctAnswer" not in new

    challenge = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert challenge is not None
    assert challenge["unit_id"] == "brueche-u2"
    assert challenge["grade_level"] == "grade_6_primary"
    assert lesson_quiz_service.judge_answer(" 1 ", challenge["correct_answer"])

    preview = practice_projection_service.build_challenge_preview(challenge)
    assert preview["prompt"] == "Berechne 1/4 + 3/4."
    assert "explanation" not in preview and "correctAnswer" not in preview

    lesson = table.rows[("PRACTICE", f"LESSON#{LESSON_ID}")]
    assert lesson["challenge_count"] == 2


def test_accepted_answers_reach_the_runtime_row_and_count(table: FakeTable) -> None:
    _publish(_payload(_exercise(1, answer="59/12", acceptedAnswers=[" 4 11/12 ", "", "4 11/12"])))

    challenge = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert challenge is not None
    assert challenge["accepted_answers"] == ["4 11/12"]
    assert answer_judging.judge_challenge("4 11 / 12", challenge)
    assert not answer_judging.judge_challenge("118/24", challenge)
    preview = practice_projection_service.build_challenge_preview(challenge)
    assert "4 11/12" not in str(preview)


def test_free_text_hints_never_reach_the_runtime_row(table: FakeTable) -> None:
    _publish(_payload(_exercise(1, hint="Zähler addieren", hints=["Nenner bleibt"])))

    challenge = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert challenge is not None
    assert "hint" not in challenge and "hints" not in challenge


def test_republishing_retires_exercises_the_new_version_dropped(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1), _exercise(2), _exercise(3)))
    _publish(_payload(_exercise(1, answer="4/4"), _exercise(3)), expected=first)

    assert _published_ids() == [f"{LESSON_ID}-q01", f"{LESSON_ID}-q03"]
    assert practice_repo.get_challenge(f"{LESSON_ID}-q02") is None
    assert ("PRACTICE_CHALLENGE_LOOKUP", f"CHALLENGE#{LESSON_ID}-q02") not in table.rows
    changed = practice_repo.get_challenge(f"{LESSON_ID}-q01")
    assert changed is not None and changed["correct_answer"] == "4/4"


def test_a_new_draft_keeps_the_published_version_on_the_pointer(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1)))

    draft = curriculum_ops_service.create_lesson_draft(_payload(_exercise(2)), OPERATOR)

    pointer = curriculum_ops_repo.get_pointer(LESSON_ID)
    assert pointer is not None
    assert pointer["published_version_id"] == first
    assert pointer["draft_version_id"] == draft["versionId"]
    assert pointer["manifest_id"]


def test_rollback_restores_exactly_the_earlier_exercise_set(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1), _exercise(2)))
    second = _publish(_payload(_exercise(3)), expected=first)

    curriculum_ops_service.rollback(
        LESSON_ID, first, OPERATOR, expected_published_version_id=second, reason="Fehler in q03"
    )

    assert _published_ids() == [f"{LESSON_ID}-q01", f"{LESSON_ID}-q02"]
    assert practice_repo.get_challenge(f"{LESSON_ID}-q03") is None
    assert practice_repo.get_challenge(f"{LESSON_ID}-q02") is not None


def test_an_exercise_id_owned_by_another_lesson_is_refused_before_anything_moves(
    table: FakeTable,
) -> None:
    seeded = practice_repo.get_challenge("brueche-l1-c1")
    assert seeded is not None
    version_id = _approved(_payload(_exercise(1, exerciseId="brueche-l1-c1")))

    with pytest.raises(HTTPException) as refused:
        curriculum_ops_service.publish(
            LESSON_ID, version_id, OPERATOR, expected_published_version_id=None
        )

    assert refused.value.status_code == 409
    assert refused.value.detail == "exercise_id_conflict"
    assert practice_repo.get_challenge("brueche-l1-c1") == seeded
    assert "published_version_id" not in (curriculum_ops_repo.get_pointer(LESSON_ID) or {})
    assert ("PRACTICE", f"LESSON#{LESSON_ID}") not in table.rows


def test_one_exercise_id_twice_in_a_lesson_does_not_validate(table: FakeTable) -> None:
    with pytest.raises(HTTPException) as refused:
        _approved(_payload(_exercise(1), _exercise(2, exerciseId=f"{LESSON_ID}-q01")))

    assert refused.value.status_code == 422
    assert "exercises[1].exercise_id" in refused.value.detail["fields"]
