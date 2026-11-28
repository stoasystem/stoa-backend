"""The teacher's assignment preview reads the student's own rows, once each (#691).

`POST /adaptive/students/{id}/assignment-automation/batches/preview` builds the
student's learning memory and judges its recommendations against the
student's assignments. On 2026-11-25 production metered one preview at about
22,000 RCU and 5.4 s, 136 of its reads Scans of the whole table. Those Scans
were gone with the reads #496, #513 and #669 changed; what was left read the
student's `GSI-StudentId` partition seven times, three of them for the same
assignment list - and that partition holds every row carrying the student's
id, their messages among them.

The assignments are now read once and handed to the memory, its
recommendations and the policy's refusals. What the preview returns is
unchanged: `test_memory_summary_reads` compares it, with the memory's other
responses, to what main gave.

The fixture is the learning memory's (`test_memory_summary_reads`): a
published curriculum, a student with weak topics, one assigned and one
recommended exercise. A teacher who took one of the student's help requests
asks, through the route and its authorization (#495). The larger table
publishes five times the curriculum and gives other students assignments,
help requests, drafts, Ask records and messages of their own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient

import test_memory_summary_reads as memory
from audit_helpers import MemoryAuthorizationAuditSink
from fakes.ask_question import _actor
from fakes.published_curriculum import ReadCountingTable
from stoa.db.repositories import (
    adaptive_learning_repo,
    ai_teacher_tools_repo,
    asked_knowledge_repo,
)
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import adaptive
from stoa.security.identity import CanonicalRole
from stoa.services import help_requests

TEACHER = "teacher-1"
STUDENT = memory.STUDENT
PREVIEW = f"/adaptive/students/{STUDENT}/assignment-automation/batches/preview"
OTHER_STUDENTS = 40


def _help_request(student_id: str, teacher_id: str, conversation_id: str) -> dict[str, Any]:
    """A request the teacher took and is helping with: the relationship #495 asks for."""
    return {
        **help_requests.key(conversation_id),
        "entity_type": help_requests.ENTITY_TYPE,
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": student_id,
        "teacher_id": teacher_id,
        "escalation_status": "in_progress",
        "dispatch_status": "accepted",
        "created_at": "2026-11-17T10:00:00+00:00",
    }


def _other_students_rows(count: int) -> list[dict[str, Any]]:
    """Rows of other students, each in `GSI-StudentId` like the student's own."""
    rows: list[dict[str, Any]] = []
    for index in range(count):
        student_id = f"other-student-{index}"
        stamp = f"2026-11-{10 + index % 7:02d}T09:00:00+00:00"
        rows.append(_help_request(student_id, TEACHER, f"other-conv-{index}"))
        for entity_type, kind in (
            (adaptive_learning_repo.ASSIGNMENT_ENTITY, "ASSIGNMENT"),
            (ai_teacher_tools_repo.DRAFT_ENTITY, "DRAFT"),
            (asked_knowledge_repo.ENTITY_TYPE, "ASKED"),
            ("message", "MSG"),
        ):
            rows.append(
                {
                    "PK": f"{kind}#{student_id}",
                    "SK": f"{kind}#{index}",
                    "entity_type": entity_type,
                    "student_id": student_id,
                    "created_at": stamp,
                    "status": "assigned",
                }
            )
    return rows


def _table(monkeypatch: pytest.MonkeyPatch, *, large: bool) -> ReadCountingTable:
    table = memory._table(monkeypatch, memory.LARGE if large else memory.SMALL)
    table.seed(
        _help_request(STUDENT, TEACHER, "conv-helped"),
        {
            "PK": f"USER#{TEACHER}",
            "SK": "PROFILE",
            "user_id": TEACHER,
            "role": "teacher",
            "account_status": "active",
        },
    )
    table.seed_active_account(TEACHER)
    if large:
        table.seed(*_other_students_rows(OTHER_STUDENTS))
    table.reset_reads()
    return table


def _client(role: CanonicalRole, user_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_actor] = lambda: _actor(role, user_id)
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def _preview(table: ReadCountingTable) -> dict[str, Any]:
    table.reset_reads()
    with time_machine.travel(memory.READ_AT, tick=False):
        response = _client(CanonicalRole.TEACHER, TEACHER).post(PREVIEW, json={"subject": "math"})
    assert response.status_code == 200, response.text
    return response.json()


def _memory(table: ReadCountingTable) -> dict[str, Any]:
    table.reset_reads()
    with time_machine.travel(memory.READ_AT, tick=False):
        response = _client(CanonicalRole.STUDENT, STUDENT).get("/adaptive/students/me/memory")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_preview_reads_the_same_rows_however_large_the_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    small = _table(monkeypatch, large=False)
    small_rows = len(small.rows)
    small_preview = _preview(small)
    large = _table(monkeypatch, large=True)
    large_preview = _preview(large)

    reports = f"small:\n{small.report()}\n\nlarge:\n{large.report()}"
    assert len(large.rows) > 3 * small_rows, "the larger table is not larger"
    for table in (small, large):
        assert not any(operation == "scan" for operation, *_ in table.reads), reports
    assert large.total_rows_scanned == small.total_rows_scanned, reports
    assert sum(large.reads.values()) == sum(small.reads.values()), reports
    # The fixture exercises the judgement: something is selected or refused.
    assert small_preview["selected"] or small_preview["refused"]
    assert large_preview["summary"]["selectedCount"] == small_preview["summary"]["selectedCount"]


def _counting_assignment_reads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    original: Callable[..., list[dict[str, Any]]] = adaptive_learning_repo.list_assignments

    def counted(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(adaptive_learning_repo, "list_assignments", counted)
    return calls


@pytest.mark.parametrize("read", [_preview, _memory], ids=["teacher-preview", "student-memory"])
def test_the_assignments_are_read_once(
    monkeypatch: pytest.MonkeyPatch, read: Callable[[ReadCountingTable], dict[str, Any]]
) -> None:
    """Each read walks the student's whole `GSI-StudentId` partition, messages included."""
    table = _table(monkeypatch, large=False)
    calls = _counting_assignment_reads(monkeypatch)

    read(table)

    assert calls == [{"student_id": STUDENT, "include_archived": True, "limit": None}]


def test_a_student_is_not_counted_their_archived_assignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read with the archived ones for the recommendations; counted for those who manage them."""
    table = _table(monkeypatch, large=False)
    archived = {
        "PK": f"ASSIGNMENT#{STUDENT}",
        "SK": "ASSIGNMENT#archived",
        "assignment_id": "assignment-archived",
        "entity_type": adaptive_learning_repo.ASSIGNMENT_ENTITY,
        "student_id": STUDENT,
        "created_at": "2026-11-16T09:00:00+00:00",
        "status": "archived",
        "source_type": "curriculum_exercise",
        "source_id": "brueche-l1-c2",
        "topic_ids": ["brueche"],
    }
    before = _memory(table)["sequencingSummary"]
    table.seed(archived)

    after_student = _memory(table)["sequencingSummary"]
    with time_machine.travel(memory.READ_AT, tick=False):
        teacher_summary = _client(CanonicalRole.TEACHER, TEACHER).get(
            f"/adaptive/students/{STUDENT}/memory"
        )

    assert after_student["archivedAssignments"] == before["archivedAssignments"] == 0
    assert teacher_summary.status_code == 200, teacher_summary.text
    assert teacher_summary.json()["sequencingSummary"]["archivedAssignments"] == 1
