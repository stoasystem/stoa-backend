"""One student's evidence, read once per request (#214, #291, #292).

The star map used to query the same student partitions about seventeen times
for one sky, and several of those reads stopped at the first 1 MB page. These
pin the two promises that replaced that: every student partition is queried at
most once per request, and every partition is read to its last page.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from boto3.dynamodb.conditions import ConditionBase
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.routers import practice
from stoa.security import declared_authorization
from stoa.services import (
    adaptive_learning_service,
    curriculum_service,
    knowledge_mastery_service,
    star_map_candidates,
)
from stoa.services import student_evidence

STUDENT = "student-a"
NOW = datetime.now(UTC)
MOMENT = (NOW - timedelta(days=1)).isoformat()

CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": "u1", "subjectId": "math", "topicId": "t1", "title": "Kürzen", "order": 0},
        {"id": "u2", "subjectId": "math", "topicId": "t1", "title": "Erweitern", "order": 1,
         "prerequisiteUnitIds": ["u1"]},
        {"id": "u3", "subjectId": "math", "topicId": "t1", "title": "Teilen", "order": 2},
    ],
    "lessons": [
        {"id": "l1", "unitId": "u1", "subjectId": "math", "topicId": "t1", "order": 0},
        {"id": "l2", "unitId": "u2", "subjectId": "math", "topicId": "t1", "order": 0},
        {"id": "l3", "unitId": "u3", "subjectId": "math", "topicId": "t1", "order": 0},
    ],
    "rolloutSubjects": ["math"],
}


def _student_rows(student: str = STUDENT) -> list[dict[str, Any]]:
    """Something in every student partition the evidence reads."""
    return [
        {"PK": f"PROGRESS#{student}", "SK": "LESSON#l1", "lesson_id": "l1", "unit_id": "u1",
         "subject_id": "mathematics", "status": "completed", "completed_at": MOMENT},
        {"PK": f"ATTEMPTS#{student}", "SK": "ATTEMPT#1", "challenge_id": "l1-c1", "unit_id": "u1",
         "lesson_id": "l1", "correct": True, "created_at": MOMENT},
        {"PK": f"ATTEMPTS#{student}", "SK": "ATTEMPT#2", "challenge_id": "l2-c1", "unit_id": "u2",
         "lesson_id": "l2", "topic_id": "t1", "correct": False, "created_at": MOMENT},
        {"PK": f"ACTIVITY#{student}", "SK": f"DAY#{NOW.date().isoformat()}", "entity_type": "study_day",
         "day": NOW.date().isoformat()},
        {"PK": f"ACTIVITY#{student}", "SK": "LIT_LEDGER", "entity_type": "lit_ledger"},
        {"PK": f"QUIZ#{student}", "SK": "STARQUIZ_PASSED#u3", "entity_type": "practice_star_quiz_pass",
         "unit_id": "u3"},
        {"PK": f"QUIZ#{student}", "SK": "STARQUIZ_COOLDOWN#u2#q1", "unit_id": "u2",
         "retry_at": (NOW + timedelta(hours=3)).isoformat()},
        {"PK": f"REVIEW#{student}", "SK": "CARD#l2-c1", "challenge_id": "l2-c1", "lesson_id": "l2",
         "due_at": MOMENT},
    ]


def _table(
    monkeypatch: pytest.MonkeyPatch, *, rollups: str = "complete", **options: Any
) -> FakeTable:
    """`rollups`: the answer rollups under their marker (`complete`), without it
    (`unmarked`), or none at all (`none`, as before the backfill)."""
    table = FakeTable(**options)
    table.seed_active_account(STUDENT)
    rows = _student_rows()
    if rollups != "none":
        rows += fake_evidence.rollup_rows(
            STUDENT,
            [row for row in rows if str(row["SK"]).startswith("ATTEMPT#")],
            complete=rollups == "complete",
        )
    table.seed(
        *({"PK": "PRACTICE", "SK": f"CHALLENGE#{lesson}-c1", "challenge_id": f"{lesson}-c1",
           "lesson_id": lesson, "status": "active"} for lesson in ("l1", "l2", "l3")),
        *rows,
    )
    db_table.install(table)
    monkeypatch.setattr(curriculum_service, "list_catalog", lambda **_k: CATALOG)
    return table


def _partition_of(condition: object) -> str:
    """The `PK` a key condition names."""
    assert isinstance(condition, ConditionBase)
    expression = condition.get_expression()
    if expression["operator"] == "=":
        key, value = expression["values"]
        if getattr(key, "name", None) == "PK":
            return str(value)
    for part in expression["values"]:
        if isinstance(part, ConditionBase):
            found = _partition_of(part)
            if found:
                return found
    return ""


def _student_queries(table: FakeTable, student: str = STUDENT) -> Counter[str]:
    """How many queries each of this student's partitions took, by partition prefix."""
    counted: Counter[str] = Counter()
    for operation, request in table.requests:
        if operation != "query":
            continue
        partition = _partition_of(request["KeyConditionExpression"])
        if partition.endswith(f"#{student}"):
            counted[partition.removesuffix(f"#{student}")] += 1
    return counted


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    monkeypatch.setattr(practice, "_actor_locale", lambda _actor: "de")
    monkeypatch.setattr(
        declared_authorization.user_repo,
        "get_user",
        lambda user_id, **_kw: {"user_id": user_id, "role": "student", "account_status": "active"},
    )
    return TestClient(app)


# ── once per partition ─────────────────────────────────────────────────────


def test_the_full_star_map_queries_each_student_partition_at_most_once(monkeypatch) -> None:
    """The acceptance check of #291, through the real route and repositories."""
    table = _table(monkeypatch)

    response = _client(monkeypatch).get("/practice/knowledge-map", params={"view": "full"})

    assert response.status_code == 200, response.text
    assert _student_queries(table) == {
        "PROGRESS": 1,
        "ATTEMPTS": 1,
        "ACTIVITY": 1,
        "QUIZ": 1,
        "REVIEW": 1,
    }
    # The negative control: the facts did reach the sky, so the reads were not skipped.
    stars = {star["unitId"]: star for star in response.json()["stars"]}
    assert stars["u1"]["state"] == "lit"
    assert stars["u3"]["state"] == "lit"
    assert stars["u2"]["reviewDue"] == 1
    assert stars["u2"]["starQuizRetryAt"] is not None
    assert response.json()["summary"]["streakDays"] >= 1
    assert {galaxy["subjectId"]: galaxy["enrolled"] for galaxy in response.json()["galaxies"]} == {
        "math": True
    }


def _marker(table: FakeTable) -> dict[str, Any] | None:
    return table.rows.get((f"ATTEMPTS#{STUDENT}", "ROLLUP#!STATE"))


@pytest.mark.parametrize("rollups", ["unmarked", "none"])
def test_without_the_marker_the_star_map_reads_every_answer(monkeypatch, rollups) -> None:
    """Card 135: rollups are trusted only under their marker; the sky is the same either way."""
    def sky(variant: str) -> tuple[FakeTable, list[dict[str, Any]]]:
        table = _table(monkeypatch, rollups=variant)
        response = _client(monkeypatch).get("/practice/knowledge-map", params={"view": "full"})
        assert response.status_code == 200, response.text
        # When a lighting was first seen is the moment of the request.
        return table, [{**star, "litAt": None} for star in response.json()["stars"]]

    _marked, expected = sky("complete")
    table, stars = sky(rollups)

    # The rollups, then every answer: two queries of ATTEMPTS#.
    assert _student_queries(table)["ATTEMPTS"] == 2
    assert stars == expected
    assert {star["unitId"] for star in stars if star["state"] == "lit"} == {"u1", "u3"}


def test_rollups_that_agree_with_every_answer_get_their_marker(monkeypatch) -> None:
    """A student with no marker but rollups that say what the answers say: marked once."""
    table = _table(monkeypatch, rollups="unmarked")
    client = _client(monkeypatch)

    assert client.get("/practice/knowledge-map").status_code == 200
    marker = _marker(table)
    assert marker is not None
    assert marker["rollup_version"] == 1
    assert marker["owner_id"] == STUDENT

    table.requests.clear()
    assert client.get("/practice/knowledge-map").status_code == 200
    assert _student_queries(table)["ATTEMPTS"] == 1


def test_rollups_missing_an_answer_get_no_marker(monkeypatch) -> None:
    table = _table(monkeypatch, rollups="none")

    assert _client(monkeypatch).get("/practice/knowledge-map").status_code == 200

    assert _marker(table) is None


def test_the_neighbourhood_queries_each_student_partition_at_most_once(monkeypatch) -> None:
    table = _table(monkeypatch)

    response = _client(monkeypatch).get("/practice/knowledge-map/stars", params={"around": "u2"})

    assert response.status_code == 200, response.text
    assert set(_student_queries(table).values()) == {1}
    assert response.json()["focus"] == "u2"


def test_the_ask_candidates_read_only_lessons_answers_and_star_quizzes(monkeypatch) -> None:
    """A star's three states need three facts; nothing else of the student is read."""
    table = _table(monkeypatch)
    monkeypatch.setattr(star_map_candidates, "_content", {})

    candidates = star_map_candidates.for_student(STUDENT, locale="de")

    assert candidates is not None
    assert {item["unitId"]: item["state"] for item in candidates} == {
        "u1": "lit",
        "u2": "ready",
        "u3": "lit",
    }
    assert _student_queries(table) == {"PROGRESS": 1, "ATTEMPTS": 1, "QUIZ": 1}


def test_a_fact_asked_for_twice_is_read_once() -> None:
    evidence = fake_evidence.evidence(answered_right=["c1"], completed=["l1"])

    assert evidence.answered_right == {"c1"}
    assert evidence.mistakes == ()
    assert evidence.last_activity_by_unit == {}
    assert evidence.completed_lesson_ids == {"l1"}
    assert evidence.study_streak == 1

    assert sorted(evidence.source.reads) == ["activity", "attempts", "progress"]


def test_nothing_is_read_until_a_fact_is_asked_for() -> None:
    evidence = fake_evidence.evidence(answered_right=["c1"])

    assert evidence.source.reads == []
    knowledge_mastery_service.unit_states(evidence)
    assert sorted(evidence.source.reads) == ["attempts", "progress", "star_quiz_outcomes"]


# ── every page ─────────────────────────────────────────────────────────────


def test_every_partition_is_read_to_its_last_page(monkeypatch) -> None:
    """Pages of one row each: nothing past the first page may go missing."""
    table = _table(monkeypatch, page_item_cap=1)
    table.seed(
        *({"PK": f"ATTEMPTS#{STUDENT}", "SK": f"ATTEMPT#x{i}", "challenge_id": f"x{i}",
           "correct": True, "created_at": MOMENT} for i in range(5)),
        *({"PK": f"ACTIVITY#{STUDENT}", "SK": f"DAY#2026-01-0{i}", "day": f"2026-01-0{i}"}
          for i in range(1, 6)),
        *({"PK": f"REVIEW#{STUDENT}", "SK": f"CARD#l1-x{i}", "challenge_id": f"l1-x{i}",
           "lesson_id": "l1", "due_at": MOMENT} for i in range(4)),
    )

    evidence = student_evidence.for_student(STUDENT, now=NOW)

    assert {f"x{i}" for i in range(5)} | {"l1-c1"} == evidence.answered_right
    assert {f"2026-01-0{i}" for i in range(1, 6)} <= evidence.study_days
    assert evidence.lit_ledger_open is True
    assert evidence.star_quiz_passed == {"u3"}
    assert set(evidence.star_quiz_retry_at) == {"u2"}
    assert evidence.review_due_by_unit == {"u1": 4, "u2": 1}
    assert evidence.completed_lesson_ids == {"l1"}


def test_more_due_cards_than_the_old_ceiling_are_all_counted() -> None:
    evidence = fake_evidence.evidence(catalog=CATALOG, review_due={"u1": 650})

    assert evidence.review_due_by_unit == {"u1": 650}


# ── what degrades and what does not ────────────────────────────────────────


def test_a_partition_that_fails_is_not_read_again_and_its_fragile_facts_say_none() -> None:
    evidence = fake_evidence.evidence(
        completed=["l1"], study_days=["2026-01-04"], failing=["activity", "star_quiz_outcomes"]
    )

    assert evidence.study_days == frozenset()
    assert evidence.star_quiz_retry_at == {}
    with pytest.raises(RuntimeError):
        _ = evidence.lit_ledger_open
    with pytest.raises(RuntimeError):
        _ = evidence.star_quiz_passed
    assert evidence.source.reads.count("activity") == 1
    assert evidence.source.reads.count("star_quiz_outcomes") == 1


def test_a_self_reported_answer_counts_for_nothing_but_the_mistake_pages() -> None:
    evidence = fake_evidence.evidence(
        attempts=[
            {"challenge_id": "c1", "correct": True, "self_reported": True, "unit_id": "u1",
             "created_at": MOMENT},
            {"challenge_id": "c2", "correct": False, "self_reported": True, "unit_id": "u2",
             "created_at": MOMENT},
        ]
    )

    assert evidence.answered_right == frozenset()
    assert evidence.last_activity_by_unit == {}
    assert [item["challenge_id"] for item in evidence.mistakes] == ["c2"]


def test_mistakes_come_newest_first() -> None:
    evidence = fake_evidence.evidence(
        attempts=[
            {"attempt_id": "a", "challenge_id": "old", "correct": False, "created_at": "2026-01-01T00:00:00+00:00"},
            {"attempt_id": "b", "challenge_id": "new", "correct": False, "created_at": "2026-01-03T00:00:00+00:00"},
            {"attempt_id": "c", "challenge_id": "mid", "correct": False, "created_at": "2026-01-02T00:00:00+00:00"},
        ]
    )

    assert [item["challenge_id"] for item in evidence.mistakes] == ["new", "mid", "old"]


# ── the facts the outer readers need (#292) ───────────────────────────────


def test_a_window_holds_what_happened_inside_it_and_nothing_else() -> None:
    evidence = fake_evidence.evidence(
        progress=[
            {"lesson_id": "before", "status": "completed", "completed_at": "2026-05-31T23:59:59+00:00"},
            {"lesson_id": "first", "status": "completed", "completed_at": "2026-06-01T00:00:00+00:00"},
            {"lesson_id": "last", "status": "completed", "completed_at": "2026-06-07T23:59:59Z"},
            {"lesson_id": "after", "status": "completed", "completed_at": "2026-06-08T00:00:00+00:00"},
            {"lesson_id": "unread", "status": "completed", "completed_at": "not a time"},
        ],
        attempts=[
            {"attempt_id": "a", "challenge_id": "in", "correct": False, "created_at": "2026-06-03T08:00:00Z"},
            {"attempt_id": "b", "challenge_id": "out", "correct": False, "created_at": "2026-06-09T08:00:00Z"},
            {"attempt_id": "c", "challenge_id": "right", "correct": True, "created_at": "2026-06-03T09:00:00Z"},
        ],
    )
    week = (datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 8, tzinfo=UTC))

    assert [item.lesson_id for item in evidence.completions_between(*week)] == ["first", "last"]
    assert [item["challenge_id"] for item in evidence.mistakes_between(*week)] == ["in"]


def test_a_finished_lesson_keeps_its_topic_and_any_title_stored_with_it() -> None:
    evidence = fake_evidence.evidence(
        progress=[
            {"lesson_id": "l1", "subject_id": "mathematics", "topic_id": "fractions",
             "lesson_title": "Brüche", "status": "completed", "completed_at": MOMENT},
            {"lesson_id": "l2", "subject_id": "math", "topic_id": "ratios",
             "status": "completed", "completed_at": MOMENT},
            {"lesson_id": "l3", "subject_id": "physics", "topic_id": "fractions",
             "status": "completed", "completed_at": MOMENT},
        ]
    )

    by_lesson = {item.lesson_id: item for item in evidence.completions}
    assert (by_lesson["l1"].topic_id, by_lesson["l1"].title) == ("fractions", "Brüche")
    assert by_lesson["l2"].title == ""
    # Either spelling of the subject, then the topic.
    assert [item.lesson_id for item in evidence.completions_in("math")] == ["l1", "l2"]
    assert [item.lesson_id for item in evidence.completions_in("math", topic_id="fractions")] == ["l1"]
    assert [item.lesson_id for item in evidence.completions_in(None, topic_id="fractions")] == ["l1", "l3"]


def test_one_adaptive_memory_summary_reads_progress_once(monkeypatch) -> None:
    """Each memory snapshot used to query `PROGRESS#` for itself, up to twenty a summary."""
    topics = ("angles", "fractions", "ratios")
    table = FakeTable()
    table.seed(
        *(
            {"PK": f"PROGRESS#{STUDENT}", "SK": f"LESSON#{topic}-l1", "lesson_id": f"{topic}-l1",
             "subject_id": "mathematics", "topic_id": topic, "status": "completed",
             "completed_at": MOMENT}
            for topic in topics
        ),
        *(
            {"PK": f"ATTEMPTS#{STUDENT}", "SK": f"ATTEMPT#{topic}", "challenge_id": f"{topic}-c1",
             "lesson_id": f"{topic}-l1", "subject_id": "math", "topic_id": topic, "correct": False,
             "created_at": MOMENT}
            for topic in topics
        ),
    )
    db_table.install(table)
    service = adaptive_learning_service
    monkeypatch.setattr(
        service.question_repo, "list_questions_by_student", lambda *_a, **_k: {"Items": []}
    )
    monkeypatch.setattr(service.asked_knowledge_repo, "list_for_student", lambda *_a, **_k: [])
    monkeypatch.setattr(service.adaptive_learning_repo, "list_memory_snapshots", lambda *_a, **_k: [])
    monkeypatch.setattr(service.adaptive_learning_repo, "list_assignments", lambda *_a, **_k: [])
    monkeypatch.setattr(service.curriculum_service, "topic_exercise_reader", lambda **_k: lambda *_a: [])

    summary = service.get_memory_summary(
        student_id=STUDENT, user={"sub": STUDENT, "role": "student"}
    )

    assert _student_queries(table) == {"PROGRESS": 1, "ATTEMPTS": 1}
    # The negative control: every snapshot did get its own topic's lessons.
    snapshots = {item["topic_id"]: item for item in summary["memorySnapshots"]}
    assert set(snapshots) == set(topics)
    for topic in topics:
        assert [item["lessonId"] for item in snapshots[topic]["recent_curriculum_progress"]] == [
            f"{topic}-l1"
        ]
        assert [item["challengeId"] for item in snapshots[topic]["recent_exercise_attempts"]] == [
            f"{topic}-c1"
        ]


# ── independent and asked-AI right answers (#449) ──────────────────────────


def _right(challenge: str, unit: str = "u1", **fields: Any) -> dict[str, Any]:
    return {"challenge_id": challenge, "correct": True, "unit_id": unit, "created_at": MOMENT, **fields}


def test_right_answers_per_star_are_split_by_whether_the_student_asked_ai() -> None:
    evidence = fake_evidence.evidence(
        catalog=CATALOG,
        attempts=[
            _right("c1"),
            # A receipt written before the mark existed reads as independent.
            _right("c2", asked_ai=None),
            _right("c3", asked_ai=True),
            _right("c4", asked_ai=True),
            # Answered right both ways: the exercise was shown independently.
            _right("c4"),
            # Twice after asking is still one exercise.
            _right("c5", "u2", asked_ai=True),
            _right("c5", "u2", asked_ai=True),
            # Wrong, or never checked, counts for neither.
            {"challenge_id": "c6", "correct": False, "unit_id": "u2", "asked_ai": True},
            _right("c7", "u2", self_reported=True),
            # A receipt without its star is counted under its lesson's.
            {"challenge_id": "c8", "correct": True, "lesson_id": "l3"},
        ],
    )

    counts = evidence.right_answers_by_unit

    assert counts == {
        "u1": student_evidence.RightAnswers(independent=3, asked_ai=1),
        "u2": student_evidence.RightAnswers(independent=0, asked_ai=1),
        "u3": student_evidence.RightAnswers(independent=1, asked_ai=0),
    }
    # The split is of the same right answers the stars are lit by.
    assert sum(item.independent + item.asked_ai for item in counts.values()) == len(
        evidence.answered_right
    )


def test_the_split_reads_the_answers_once_with_the_other_answer_facts() -> None:
    evidence = fake_evidence.evidence(attempts=[_right("c1", asked_ai=True)])

    assert evidence.right_answers_by_unit == {
        "u1": student_evidence.RightAnswers(independent=0, asked_ai=1)
    }
    assert evidence.answered_right == {"c1"}
    assert evidence.right_answers_by_unit is evidence.right_answers_by_unit

    assert evidence.source.reads == ["attempts"]


def test_a_star_answered_right_only_after_asking_ai_lights_as_before() -> None:
    """The split is for showing; it never changes whether a star lights (#449)."""
    facts = {
        "catalog": CATALOG,
        "exercises": {"l1": ["l1-c1", "l1-c2"]},
        "completed": ["l1"],
    }
    independent = fake_evidence.evidence(attempts=[_right("l1-c1"), _right("l1-c2")], **facts)
    helped = fake_evidence.evidence(
        attempts=[_right("l1-c1", asked_ai=True), _right("l1-c2", asked_ai=True)], **facts
    )

    judged = knowledge_mastery_service.unit_states(helped)

    assert judged["u1"].state is knowledge_mastery_service.LearningState.LIT
    assert {unit: item.state for unit, item in judged.items()} == {
        unit: item.state for unit, item in knowledge_mastery_service.unit_states(independent).items()
    }
