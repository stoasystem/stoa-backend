"""The star map, the catalog and the learning profile read the curriculum once (#496).

The routes a student, a parent or a school opens built the student catalog
with `curriculum_service.list_catalog`, which read every unit row once per
topic (27 queries of all 237 units), and `student_evidence.Content` then read
every lesson row a second time for the exercise index. At production size the
star map read some 9,600 rows per load, the parent pages some 8,000, though the
curriculum they draw is under 2,000 rows.

The curriculum is still read whole where a route draws it whole - the bar is
one read of each kind of row per request, not none. The responses are
unchanged: they were recorded from origin/main `85d92d76` on the same fixture
and are compared field for field.
"""

from __future__ import annotations

import json
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
from stoa.routers import parents, practice, students
from stoa.security.authorization import AuthorizedResource, ResourceRef, ResourceType
from stoa.security.identity import CanonicalRole

STUDENT = "student-1"
PARENT = "parent-1"
GOLDEN = Path(__file__).parent / "fixtures" / "curriculum_reads_496.json"
SMALL, LARGE = 0.05, 0.25
READ_AT = "2026-11-18T12:00:00+00:00"
#: Lessons the student finished, the first of each of these many mathematics lessons.
FINISHED = 12

#: name -> (who asks, path). `{lesson}` is a mathematics lesson the student has
#: not finished, `{topic}` its topic.
ROUTES: dict[str, tuple[str, str]] = {
    "star_map": ("student", "/practice/knowledge-map"),
    "star_map_skeleton": ("student", "/practice/knowledge-map?view=skeleton"),
    "star_map_math": ("student", "/practice/knowledge-map?subjectId=math"),
    "stars_around": ("student", "/practice/knowledge-map/stars?subjectId=math"),
    "catalog": ("student", "/practice/curriculum/catalog"),
    "catalog_math": ("student", "/practice/curriculum/catalog?subjectId=math"),
    "lesson": ("student", "/practice/lessons/{lesson}"),
    "roadmap": ("student", "/practice/math/{topic}/roadmap"),
    "learning_history": ("student", "/students/me/learning-history"),
    "learning_profile": ("teacher", f"/students/{STUDENT}/learning-profile"),
    "parent_summary": ("parent", f"/parents/me/children/{STUDENT}/summary"),
    "parent_learning_profile": ("parent", f"/parents/me/children/{STUDENT}/learning-profile"),
    "parent_history": ("parent", f"/parents/me/children/{STUDENT}/history"),
}


def _table(monkeypatch: pytest.MonkeyPatch, scale: float) -> tuple[ReadCountingTable, dict[str, Any]]:
    table = ReadCountingTable()
    rows = curriculum_rows(scale)
    table.seed(*rows)
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
    maths = sorted(
        (
            row
            for row in rows
            if str(row["SK"]).startswith("LESSON#")
            and str(row["lesson_id"]).startswith("kb-mathematics-")
        ),
        key=lambda row: int(str(row["lesson_id"]).rsplit("l", 1)[1]),
    )
    for index, lesson in enumerate(maths[:FINISHED]):
        table.seed(
            {
                "PK": f"PROGRESS#{STUDENT}",
                "SK": f"LESSON#{lesson['lesson_id']}",
                "entity_type": "practice_progress",
                "student_id": STUDENT,
                "lesson_id": lesson["lesson_id"],
                "subject_id": lesson["subject_id"],
                "topic_id": lesson["topic_id"],
                "unit_id": lesson["unit_id"],
                "status": "completed",
                "completed_at": f"2026-11-{1 + index:02d}T10:00:00+00:00",
            }
        )
    for index, (subject, names) in enumerate(
        [("mathematics", ["brueche", "gleichungen"]), ("physics", ["Energie"])]
    ):
        put = asked_knowledge_repo.record_put(
            conversation_id=f"earlier-{index}",
            message_id="answer",
            student_id=STUDENT,
            subject=subject,
            points=[(name, None) for name in names],
            asked_at=f"2026-11-1{index}T10:00:00+00:00",
        )
        assert put is not None
        table.seed(put["Put"]["Item"])
    db_table.install(table)
    seed_plan(monkeypatch)
    table.reset_reads()
    return table, maths[FINISHED + 1]


def _client(who: str) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    app.include_router(students.router, prefix="/students")
    app.include_router(parents.router, prefix="/parents")
    actor = {
        "student": lambda: _actor(),
        "teacher": lambda: _actor(role=CanonicalRole.TEACHER, user_id="teacher-1"),
        "parent": lambda: _actor(role=CanonicalRole.PARENT, user_id=PARENT),
    }[who]
    app.dependency_overrides[get_actor] = actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    if who == "parent":
        # Who may see the child is not what these tests are about: the child is given.
        child = AuthorizedResource(
            ref=ResourceRef(ResourceType.STUDENT, STUDENT, STUDENT),
            value={"user_id": STUDENT, "role": "student", "grade": "Grade 6", "name": "Mia"},
        )
        app.dependency_overrides[parents._parent_child_read] = lambda: child
    if who == "teacher":
        _let_the_teacher_read(app)
    return TestClient(app, raise_server_exceptions=False)


def _let_the_teacher_read(app: FastAPI) -> None:
    for route in students.router.routes:
        if getattr(route, "path", "") == "/{student_id}/learning-profile":
            for dependency in route.dependant.dependencies:
                if dependency.call is not None and dependency.name not in {"actor", "user"}:
                    app.dependency_overrides[dependency.call] = lambda: AuthorizedResource(
                        ref=ResourceRef(ResourceType.STUDENT, STUDENT, STUDENT),
                        value={"user_id": STUDENT, "role": "student"},
                    )


def _get(name: str, lesson: dict[str, Any]) -> Any:
    who, template = ROUTES[name]
    path = template.format(lesson=lesson["lesson_id"], topic=lesson["topic_id"])
    response = _client(who).get(path)
    assert response.status_code == 200, f"{name}: {response.status_code} {response.text}"
    return response.json()


def test_the_responses_are_the_ones_main_gave(monkeypatch: pytest.MonkeyPatch) -> None:
    _table_, lesson = _table(monkeypatch, SMALL)

    with time_machine.travel(READ_AT, tick=False):
        responses = json.loads(
            json.dumps({name: _get(name, lesson) for name in ROUTES}, sort_keys=True)
        )

    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(responses) == set(recorded)
    for name in recorded:
        assert responses[name] == recorded[name], name
    # The fixture draws what changed: units under their topics, lessons with
    # their exercises counted from the lesson rows.
    assert recorded["catalog"]["units"] and recorded["catalog"]["lessons"]


def _catalog_rows(table: ReadCountingTable) -> int:
    """Subjects, topics, units and lessons: what one read of the curriculum is."""
    return sum(
        1
        for (pk, sk) in table.rows
        if pk == "PRACTICE" and sk.split("#", 1)[0] in {"SUBJECT", "TOPIC", "UNIT", "LESSON"}
    )


#: What a route reads beyond the curriculum: the student's own rows and the
#: one lesson's exercises. It does not grow with the curriculum.
OWN_ROWS = 120


@pytest.mark.parametrize("name", list(ROUTES))
def test_the_curriculum_is_read_at_most_once(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    read: dict[float, tuple[int, int, str]] = {}
    for scale in (SMALL, LARGE):
        table, lesson = _table(monkeypatch, scale)
        with time_machine.travel(READ_AT, tick=False):
            _get(name, lesson)
        read[scale] = (table.total_rows_scanned, _catalog_rows(table), table.report())

    reports = "\n\n".join(f"scale {scale}:\n{report}" for scale, (_, _, report) in read.items())
    for rows, catalog, _report in read.values():
        assert rows <= catalog + OWN_ROWS, reports
    # And what it reads grows with the curriculum by no more than one read of it.
    (small_rows, small_catalog, _), (large_rows, large_catalog, _) = read[SMALL], read[LARGE]
    assert large_rows - small_rows <= large_catalog - small_catalog, reports


def test_the_learning_history_reads_only_the_finished_lessons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Their titles, each by its key: not every lesson row (#513)."""
    read: dict[float, ReadCountingTable] = {}
    for scale in (SMALL, LARGE):
        table, lesson = _table(monkeypatch, scale)
        with time_machine.travel(READ_AT, tick=False):
            _get("learning_history", lesson)
        read[scale] = table

    reports = "\n\n".join(f"scale {scale}:\n{table.report()}" for scale, table in read.items())
    assert read[SMALL].total_rows_scanned == read[LARGE].total_rows_scanned, reports
    lessons = [
        rows
        for (operation, _inner, _caller), rows in read[LARGE].items_read.items()
        if operation == "get_item"
    ]
    assert sum(lessons) >= FINISHED, reports
