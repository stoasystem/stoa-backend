"""The learning memory reads the curriculum once, and a student's assignments by key (#496).

`GET /adaptive/students/me/memory` is loaded by the Ask page for every student,
by the parent's child-progress page and by the automation console. Its practice
recommendations listed the subject's exercises once per weak topic, and each
list read every exercise row of the practice partition; the student's
assignments were found by a filtered scan of the whole table, twice per
summary. With the knowledge base published that was some 160,000 rows per
request for a student with a dozen weak topics.

The exercises are now read once per summary and grouped by subject and topic
in memory; the assignments are read from `GSI-StudentId`, which holds every
assignment row (each carries `student_id` and `created_at`). What the reads
return is unchanged: the responses below were recorded from origin/main
`c1cc6edb` on the same fixture and are compared field for field. The weak
topics (`weakTopics`, the parent's `weakAreas`) were recorded again when they
began to come from `weak_topics` (#673): named as the catalog names them, each
with its `score`; the recommendations stayed as main gave them. The
`memorySnapshots` were recorded again when they began to be worked out from
the same weak topics on each read (#675): one per weak topic, in its order,
keyed as it is (a free name no longer made a slug); the recommendations,
again, stayed as they were. A subject's `label` in `subjectActivity` was
recorded again when it became the message catalog's `subject.<id>` in the
reader's language (#662).

To record them again: `STOA_RECORD_MEMORY_SUMMARY_READS=1 pytest
tests/test_memory_summary_reads.py -k responses_are_the_ones_main_gave`.

Since #673 the weak topics are resolved against the catalog, which a container
keeps (`curriculum_cache`): the table here carries the catalog stamp the seed
writes in production, and each summary is read in a container that has not
read the curriculum yet, so it loads the one stored copy (#669) rather than
the partition.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.admission import seed_plan
from fakes.ask_question import _actor
from fakes.published_curriculum import ReadCountingTable, curriculum_rows
from stoa.db import table as db_table
from stoa.db.repositories import asked_knowledge_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import adaptive
from stoa.services import adaptive_learning_service as service
from stoa.services import curriculum_cache, curriculum_service

STUDENT = "student-1"
GOLDEN = Path(__file__).parent / "fixtures" / "memory_summary_reads_496.json"
RECORD = bool(os.environ.get("STOA_RECORD_MEMORY_SUMMARY_READS"))
SMALL, LARGE = 0.05, 0.25
#: When the two assignments were made, and when the responses are read.
ASSIGNED_AT = ("2026-11-14T09:00:00+00:00", "2026-11-15T09:00:00+00:00")
READ_AT = "2026-11-18T12:00:00+00:00"

STUDENT_USER = {"sub": STUDENT, "user_id": STUDENT, "role": "student"}
TEACHER_USER = {"sub": "teacher-1", "user_id": "teacher-1", "role": "teacher"}
PARENT_USER = {"sub": "parent-1", "user_id": "parent-1", "role": "parent"}

#: What earlier Ask answers named: mathematics nebulae the curriculum has
#: exercises under, a physics star, and a point no exercise belongs to.
ASKED = [
    ("mathematics", ["brueche", "gleichungen"]),
    ("mathematics", ["brueche", "geometrie"]),
    ("mathematics", ["prozentrechnung", "zahlen"]),
    ("mathematics", ["groessen", "daten"]),
    ("physics", ["Kräfte", "Energie"]),
    ("mathematics", ["Kopfrechnen im Alltag"]),
]


def _table(monkeypatch: pytest.MonkeyPatch, scale: float, asked=ASKED) -> ReadCountingTable:
    table = ReadCountingTable()
    table.seed(*curriculum_rows(scale))
    table.seed_active_account(STUDENT)
    table.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "PROFILE",
            "user_id": STUDENT,
            "role": "student",
            "account_status": "active",
            "grade": "Grade 6",
            "subjects": ["mathematics", "physics"],
        }
    )
    for index, (subject, names) in enumerate(asked):
        put = asked_knowledge_repo.record_put(
            conversation_id=f"earlier-{index}",
            message_id="answer",
            student_id=STUDENT,
            subject=subject,
            points=[(name, None) for name in names],
            asked_at=f"2026-11-{10 + index % 7:02d}T10:00:00+00:00",
        )
        assert put is not None
        table.seed(put["Put"]["Item"])
    db_table.install(table)
    seed_plan(monkeypatch)
    # Through the real path: one assigned on a weak topic, one only recommended.
    with time_machine.travel(ASSIGNED_AT[0], tick=False):
        service.create_assignment(
            student_id=STUDENT,
            source_type="curriculum_exercise",
            source_id="brueche-l1-c1",
            user=TEACHER_USER,
        )
    with time_machine.travel(ASSIGNED_AT[1], tick=False):
        service.create_assignment(
            student_id=STUDENT,
            source_type="curriculum_exercise",
            source_id="geometrie-l1-c1",
            user=TEACHER_USER,
            status="recommended",
        )
    table.seed({**curriculum_cache.STAMP_KEY, "stamp": f"seed-{scale}"})
    # The first container to read the curriculum stores it; the summary is read in another.
    curriculum_cache.current()
    curriculum_cache.forget()
    table.reset_reads()
    return table


def _responses() -> dict[str, Any]:
    with time_machine.travel(READ_AT, tick=False):
        return _read_responses()


def _read_responses() -> dict[str, Any]:
    return {
        "memory_student_all": service.get_memory_summary(student_id=STUDENT, user=STUDENT_USER),
        "memory_student_math": service.get_memory_summary(
            student_id=STUDENT, user=STUDENT_USER, subject="math"
        ),
        "memory_student_physics": service.get_memory_summary(
            student_id=STUDENT, user=STUDENT_USER, subject="physics"
        ),
        "memory_teacher_math": service.get_memory_summary(
            student_id=STUDENT, user=TEACHER_USER, subject="math"
        ),
        "assignments_student": service.list_assignments(student_id=STUDENT, user=STUDENT_USER),
        "assignments_student_assigned": service.list_assignments(
            student_id=STUDENT, user=STUDENT_USER, status="assigned"
        ),
        "assignments_teacher": service.list_assignments(
            student_id=STUDENT, user=TEACHER_USER, include_archived=True
        ),
        "parent_progress": service.parent_progress_signal(STUDENT, PARENT_USER),
        "automation_preview": service.preview_assignment_automation_batch(
            student_id=STUDENT, policy={}, user=TEACHER_USER, subject="math"
        ),
    }


def _comparable(value: Any) -> Any:
    """The responses as JSON, with the random assignment ids numbered in order."""
    text = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    ids: dict[str, str] = {}
    for found in re.findall(r"assignment-[0-9a-f]{32}", text):
        ids.setdefault(found, f"assignment-{len(ids) + 1}")
    for found, numbered in ids.items():
        text = text.replace(found, numbered)
    return json.loads(text)


def test_the_responses_are_the_ones_main_gave(monkeypatch: pytest.MonkeyPatch) -> None:
    _table(monkeypatch, SMALL)

    responses = _comparable(_responses())

    if RECORD:
        GOLDEN.write_text(
            json.dumps(responses, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(responses) == set(recorded)
    for name in recorded:
        assert responses[name] == recorded[name], name
    # The fixture exercises what changed: exercises recommended for weak
    # topics, and assignments that suppress and are listed.
    kinds = {item["type"] for item in recorded["memory_student_math"]["recommendations"]}
    assert "curriculum_exercise" in kinds
    assert len(recorded["assignments_student"]["items"]) == 2


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_actor] = lambda: _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def _exercise_rows(table: ReadCountingTable) -> int:
    return sum(1 for (pk, sk) in table.rows if pk == "PRACTICE" and sk.startswith("CHALLENGE#"))


def _memory(table: ReadCountingTable, subject: str | None) -> None:
    table.reset_reads()
    response = _client().get(
        "/adaptive/students/me/memory", params={"subject": subject} if subject else None
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("subject", [None, "math"])
def test_the_memory_reads_the_same_rows_however_large_the_curriculum(
    monkeypatch: pytest.MonkeyPatch, subject: str | None
) -> None:
    """It recommends the first two published exercises of each weak topic, and
    reads those through GSI-TopicShelf, not every exercise row (#513)."""
    small = _table(monkeypatch, SMALL)
    _memory(small, subject)
    large = _table(monkeypatch, LARGE)
    _memory(large, subject)

    reports = f"small:\n{small.report()}\n\nlarge:\n{large.report()}"
    for table in (small, large):
        assert not any(operation == "scan" for operation, *_ in table.reads), reports
    assert large.total_rows_scanned == small.total_rows_scanned, reports
    assert large.total_rows_scanned < _exercise_rows(small), reports


def _shelf_reads(table: ReadCountingTable) -> tuple[int, int]:
    """(queries, rows) of the exercise shelves the memory read."""
    queries = rows = 0
    for (operation, _inner, caller), count in table.reads.items():
        if operation == "query" and caller.startswith("services/curriculum_service"):
            queries += count
            rows += table.rows_scanned[(operation, _inner, caller)]
    return queries, rows


def test_each_weak_topic_reads_a_page_of_its_own_exercises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    few = _table(monkeypatch, SMALL, asked=ASKED[:1])
    _memory(few, "math")
    many = _table(monkeypatch, SMALL)
    _memory(many, "math")

    reports = f"few:\n{few.report()}\n\nmany:\n{many.report()}"
    (few_queries, _few_rows), (many_queries, many_rows) = _shelf_reads(few), _shelf_reads(many)
    assert 0 < few_queries < many_queries, reports
    # A page per topic, not the topic's every exercise, let alone every exercise.
    assert many_rows <= many_queries * curriculum_service.TOPIC_EXERCISE_PAGE, reports
