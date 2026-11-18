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
`c1cc6edb` on the same fixture and are compared field for field.
"""

from __future__ import annotations

import json
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

STUDENT = "student-1"
GOLDEN = Path(__file__).parent / "fixtures" / "memory_summary_reads_496.json"
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
def test_the_memory_reads_the_exercises_once_and_scans_nothing(
    monkeypatch: pytest.MonkeyPatch, subject: str | None
) -> None:
    small = _table(monkeypatch, SMALL)
    _memory(small, subject)
    large = _table(monkeypatch, LARGE)
    _memory(large, subject)

    reports = f"small:\n{small.report()}\n\nlarge:\n{large.report()}"
    for table in (small, large):
        assert not any(operation == "scan" for operation, *_ in table.reads), reports
    # Beyond one read of the exercises, the reads do not grow with the curriculum.
    assert (
        large.total_rows_scanned - _exercise_rows(large)
        == small.total_rows_scanned - _exercise_rows(small)
    ), reports


def test_more_weak_topics_do_not_read_the_exercises_again(monkeypatch: pytest.MonkeyPatch) -> None:
    few = _table(monkeypatch, SMALL, asked=ASKED[:1])
    _memory(few, "math")
    many = _table(monkeypatch, SMALL)
    _memory(many, "math")

    def exercise_reads(table: ReadCountingTable) -> int:
        return sum(
            rows
            for (operation, _inner, _caller), rows in table.rows_scanned.items()
            if operation == "query" and rows >= _exercise_rows(table) // 2
        )

    assert exercise_reads(many) == exercise_reads(few) == _exercise_rows(many), (
        f"few:\n{few.report()}\n\nmany:\n{many.report()}"
    )
