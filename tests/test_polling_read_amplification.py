"""Card 133-A2: what the two endpoints every open tab polls cost in round trips.

The bell polls GET /notifications every 30 seconds and the chat indicator polls
GET /teacher-help/availability. Both used to grow with history rather than
with what they show: the bell read a person's every notification to show the
newest fifty, and the indicator read each seen teacher's profile and fence one
at a time. The counts are pinned exactly, in both directions, as
test_admin_user_list_read_amplification.py pins the admin list.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable

from actor_helpers import install_actor_overrides
from stoa.db import table as db_table
from stoa.db.repositories import notification_repo
from stoa.routers import conversations, notifications
from stoa.services import (
    notification_service,
    teacher_dispatch_service,
    teacher_support_allowance_service as allowance,
)

STUDENT = "student-133"
OWN = 300
FOR_ROLE = 200
START = datetime(2026, 1, 1, tzinfo=UTC)


class ScanCountingTable(FakeTable):
    """The shared double, also adding up the rows each query read."""

    def __init__(self) -> None:
        super().__init__()
        self.rows_read = 0

    def query(self, **kwargs: Any) -> dict[str, Any]:
        response = super().query(**kwargs)
        self.rows_read += int(response["ScannedCount"])
        return response


@pytest.fixture
def table() -> ScanCountingTable:
    counting = ScanCountingTable()
    db_table.install(counting)
    return counting


def _notification(index: int, *, recipient_id: str | None, status: str) -> dict[str, Any]:
    created_at = (START + timedelta(minutes=index)).isoformat()
    item = {
        "event_id": f"event-{index:04d}",
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "recipient_id": recipient_id,
        "recipient_role": "student",
        "event_type": "teacher_help_dispatched",
        "target_type": "conversation",
        "target_id": "conv-1",
        "title": "Eine Frage wartet",
        "summary": "",
        "status": status,
        "created_at": created_at,
        "metadata": {},
        "owner_id": recipient_id,
        "account_fence_generation": 1,
        "owner_classification": "private_owner" if recipient_id else "global_nonprivate",
    }
    return {
        **item,
        "PK": notification_repo.notification_pk(item["event_id"]),
        "SK": "META",
        **notification_repo.index_fields(item),
    }


def _seed_history(table: FakeTable) -> list[dict[str, Any]]:
    """Years of a student's notifications and their role's, one in three archived."""
    seeded = []
    for index in range(OWN + FOR_ROLE):
        mine = index % 5 != 0
        seeded.append(
            _notification(
                index,
                recipient_id=STUDENT if mine else None,
                status="archived" if index % 3 == 0 else ("read" if index % 2 else "created"),
            )
        )
    # Someone else's, in the same table: never read.
    seeded.append(_notification(10_000, recipient_id="student-other", status="created"))
    table.seed(*seeded)
    return seeded


def _bell(limit: int | None = None, status: str | None = None) -> list[str]:
    app = FastAPI()
    app.include_router(notifications.router, prefix="/notifications")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    params = {key: value for key, value in (("limit", limit), ("status", status)) if value}
    response = TestClient(app).get("/notifications", params=params)
    assert response.status_code == 200, response.text
    return [item["eventId"] for item in response.json()["items"]]


def _expected(seeded: list[dict[str, Any]], *, limit: int, status: str | None = None) -> list[str]:
    """What reading the whole inbox and cutting it afterwards showed."""
    shown = [
        item
        for item in seeded
        if notification_service._visible_to_user(item, user_id=STUDENT, role="student")
        and (status is None and item["status"] != "archived" or item["status"] == status)
    ]
    shown.sort(key=lambda item: item["created_at"], reverse=True)
    return [item["event_id"] for item in shown[:limit]]


@pytest.mark.parametrize("limit", [1, 20, 50, 100])
def test_the_bell_reads_what_it_shows_not_the_whole_history(table, limit) -> None:
    seeded = _seed_history(table)
    table.calls.clear()

    shown = _bell(limit)

    assert shown == _expected(seeded, limit=limit)
    # The reader's locale, then each inbox newest first until it holds `limit`.
    assert table.calls["get_item"] == 1
    assert table.calls["query"] <= 4
    assert table.rows_read <= 4 * max(2 * limit, 25)


def test_the_default_page_costs_two_queries_and_a_fraction_of_the_rows(table) -> None:
    seeded = _seed_history(table)
    table.calls.clear()

    assert _bell() == _expected(seeded, limit=50)
    assert dict(table.calls) == {"get_item": 1, "query": 2}
    # Each inbox's newest hundred rows; the whole history was 500.
    assert table.rows_read == 200


def test_a_status_filter_still_finds_the_older_rows_it_names(table) -> None:
    seeded = _seed_history(table)

    assert _bell(50, "archived") == _expected(seeded, limit=50, status="archived")
    assert _bell(100, "read") == _expected(seeded, limit=100, status="read")


def test_a_short_inbox_is_read_to_its_end(table) -> None:
    """Negative control: fewer than `limit` shown is every one of them."""
    seeded = [_notification(index, recipient_id=STUDENT, status="created") for index in range(7)]
    table.seed(*seeded)
    table.calls.clear()

    assert _bell(50) == _expected(seeded, limit=50)
    assert dict(table.calls) == {"get_item": 1, "query": 2}


TEACHERS = 40


def _seed_teachers_and_student(table: FakeTable) -> None:
    for index in range(TEACHERS):
        teacher_id = f"teacher-{index:02d}"
        table.seed(
            {
                "PK": f"USER#{teacher_id}",
                "SK": "PROFILE",
                "user_id": teacher_id,
                "role": "teacher",
                "account_status": "active",
                "version": 1,
                "dispatch_subjects": ["math"],
                "dispatch_availability": "available",
            },
            {"PK": f"USER#{teacher_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
        )
        teacher_dispatch_service.record_teacher_seen(teacher_id)
    table.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "PROFILE",
            "user_id": STUDENT,
            "role": "student",
            "account_status": "active",
            "version": 1,
        },
        {
            "PK": f"USER#{STUDENT}",
            "SK": allowance.ASSIGNED_ALLOWANCE_SK,
            "entity_type": "teacher_support_assigned_allowance",
            "schema_version": allowance.ASSIGNED_ALLOWANCE_SCHEMA_VERSION,
            "weekly_cases": Decimal(5),
            "state_version": Decimal(1),
        },
    )


def _indicator() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    install_actor_overrides(app, {"sub": STUDENT, "role": "student"})
    response = TestClient(app).get("/teacher-help/availability")
    assert response.status_code == 200, response.text
    return response.json()


# The student's parents, as `current_relationship.parents_of` reads them: one
# query of the student's links, none found. Card 133-B1 owns that read.
PARENT_LOOKUP = {"query": 1}


def test_the_indicator_reads_the_teachers_in_one_batch_however_many(table) -> None:
    _seed_teachers_and_student(table)
    table.calls.clear()

    body = _indicator()

    assert body["online"] is True
    assert body["availableTeachers"] == TEACHERS
    assert body["teacherSupport"]["remainingCases"] == 5
    assert dict(table.calls) == {
        # The heartbeat index, then the parents' links.
        "query": 1 + PARENT_LOOKUP["query"],
        # Every teacher's profile and fence; then the allowance row and both counters.
        "batch_get_item": 2,
        # The student's profile.
        "get_item": 1,
    }


def test_the_teachers_are_read_once_per_window_for_every_student(table) -> None:
    _seed_teachers_and_student(table)
    _indicator()
    table.calls.clear()

    assert _indicator()["availableTeachers"] == TEACHERS
    # Only the student's own standing: no heartbeat query, no teacher batch.
    assert dict(table.calls) == {"query": PARENT_LOOKUP["query"], "batch_get_item": 1, "get_item": 1}


def test_dispatch_never_reads_the_students_summary(table) -> None:
    """The planner reads the teachers itself each time, cache or no cache."""
    _seed_teachers_and_student(table)
    _indicator()
    table.rows[("USER#teacher-00", "ACCOUNT_FENCE")]["status"] = "deletion_pending"
    table.calls.clear()

    plan = teacher_dispatch_service.plan_dispatch({"question_id": "q", "subject": "math"})

    assert "teacher-00" not in [item["teacherId"] for item in plan["selected"]]
    assert len(plan["selected"]) == TEACHERS - 1
    assert table.calls["batch_get_item"] == 1
