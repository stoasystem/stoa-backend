"""Only a teacher who is online is counted and offered a request (#472).

A teacher whose stored status still said available, but who had closed STOA
days ago, was counted in the student's "a teacher is available now" and was
offered every request, each offer waiting out its ten minutes. A teacher is now
on dispatch only while seen in the last five minutes: the bell and the queue
poll while the teacher's tab is shown, and each such read is the heartbeat, as
a driver's app reports while the driver is online.

Being offline is read, never stored: the teacher's own status is left alone and
counts again the moment they are back. What pauses a teacher - an offer they let
lapse - is in test_help_requests.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fakes.dynamodb import FakeTable

from actor_helpers import install_actor_overrides
from stoa.db import table as db_table
from stoa.services import teacher_dispatch_service

NOW = datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)
QUESTION = {"question_id": "q-472", "subject": "math"}
TEACHER = "teacher-472"
STUDENT = "student-472"


def at(minutes: float = 0) -> str:
    return (NOW + timedelta(minutes=minutes)).isoformat()


def _account(user_id: str, role: str = "teacher", availability: str = "available") -> list[dict]:
    profile = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "version": 1,
    }
    if role == "teacher":
        profile.update(dispatch_subjects=["math"], dispatch_availability=availability)
    return [profile, {"PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1}]


@pytest.fixture
def table() -> FakeTable:
    built = FakeTable()
    db_table.install(built)
    return built


def _offered(now: str) -> list[str]:
    return [item["teacherId"] for item in teacher_dispatch_service.plan_dispatch(QUESTION, now=now)["selected"]]


def _refusals(now: str) -> dict[str, str]:
    plan = teacher_dispatch_service.plan_dispatch(QUESTION, now=now)
    return {item["teacherId"]: item["refusalCode"] for item in plan["refused"]}


def test_an_available_teacher_never_seen_is_neither_counted_nor_offered(table) -> None:
    """The bug as reported: status alone put an absent teacher on dispatch."""
    table.seed(*_account(TEACHER))

    plan = teacher_dispatch_service.plan_dispatch(QUESTION, now=at())

    assert plan["selected"] == []
    assert plan["summary"]["noCandidateReason"] == "not_online"
    summary = teacher_dispatch_service.teacher_availability_summary(now=at())
    assert summary["online"] is False
    assert summary["availableTeachers"] == 0


def test_only_a_teacher_seen_in_the_last_five_minutes_is_online(table) -> None:
    table.seed(*_account("teacher-away"), *_account("teacher-here"))
    teacher_dispatch_service.record_teacher_seen("teacher-away", now=at(-6))
    teacher_dispatch_service.record_teacher_seen("teacher-here", now=at(-4))

    assert _offered(at()) == ["teacher-here"]
    assert _refusals(at()) == {"teacher-away": "not_online"}
    summary = teacher_dispatch_service.teacher_availability_summary(now=at())
    assert summary["online"] is True
    assert summary["availableTeachers"] == 1


def test_being_offline_leaves_the_teachers_own_status_alone(table) -> None:
    table.seed(*_account(TEACHER))
    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at())

    assert _refusals(at(10)) == {TEACHER: "not_online"}
    assert table.rows[(f"USER#{TEACHER}", "PROFILE")]["dispatch_availability"] == "available"
    assert table.rows[(f"USER#{TEACHER}", "PROFILE")]["version"] == 1

    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at(10))

    assert _offered(at(10)) == [TEACHER]


def test_a_paused_teacher_who_is_online_is_still_not_offered(table) -> None:
    table.seed(*_account(TEACHER, availability="paused"))
    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at())

    assert _refusals(at()) == {TEACHER: "not_available"}


def test_the_heartbeat_is_written_at_most_once_a_minute(table) -> None:
    """Every poll would otherwise be a write; one a minute is enough for five."""
    table.seed(*_account(TEACHER))
    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at(0))
    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at(0.5))

    # Still seen at 0: five minutes and a bit later it is offline.
    assert _refusals(at(5.2)) == {TEACHER: "not_online"}

    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at(1.5))

    assert _offered(at(5.2)) == [TEACHER]


# ── the heartbeat: the reads a teacher's open tab makes ─────────────────────


def _client(router, prefix: str, user_id: str, role: str) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, {"sub": user_id, "role": role})
    return TestClient(app)


def _rows_of(table: FakeTable, user_id: str) -> set[str]:
    return {sk for pk, sk in table.rows if pk == f"USER#{user_id}"}


@pytest.mark.parametrize(
    ("router_name", "prefix", "method", "path", "body"),
    [
        ("notifications", "/notifications", "get", "/notifications", None),
        ("teachers", "/teachers", "get", "/teachers/me/help-requests", None),
        ("teachers", "/teachers", "patch", "/teachers/me/availability", {"status": "available"}),
    ],
    ids=["bell", "queue", "going-available"],
)
def test_a_teachers_poll_puts_them_online(table, router_name, prefix, method, path, body) -> None:
    from stoa import routers

    router = getattr(__import__(f"{routers.__name__}.{router_name}", fromlist=["router"]), "router")
    table.seed(*_account(TEACHER))
    assert teacher_dispatch_service.plan_dispatch(QUESTION)["selected"] == []

    client = _client(router, prefix, TEACHER, "teacher")
    response = client.get(path) if method == "get" else client.patch(path, json=body)

    assert response.status_code == 200, response.text
    assert [item["teacherId"] for item in teacher_dispatch_service.plan_dispatch(QUESTION)["selected"]] == [TEACHER]
    assert teacher_dispatch_service.teacher_availability_summary()["availableTeachers"] == 1


def test_a_students_bell_is_no_heartbeat(table) -> None:
    from stoa.routers import notifications

    table.seed(*_account(STUDENT, role="student"))
    before = _rows_of(table, STUDENT)

    response = _client(notifications.router, "/notifications", STUDENT, "student").get("/notifications")

    assert response.status_code == 200, response.text
    assert _rows_of(table, STUDENT) == before


# ── the teachers are listed from the heartbeat rows, not a scan (#609) ──────
#
# `list_teacher_profiles` found the teachers by scanning the whole table, on
# every request of a student's page that shows whether a teacher is there. It
# now reads the heartbeat rows through their index and each seen account's
# profile and fence by key.


def _reads(table: FakeTable) -> list[str]:
    return [
        name
        for name, _call in table.requests
        if name in {"scan", "query", "get_item", "batch_get_item"}
    ]


def test_the_heartbeat_row_carries_its_place_in_the_index(table) -> None:
    from fakes.dynamodb import DEFAULT_INDEXES, IndexSchema
    from stoa.db.repositories import user_repo
    from stoa.services.ask_question import _store

    table.seed(*_account(TEACHER))
    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at())

    row = table.rows[(f"USER#{TEACHER}", user_repo.TEACHER_SEEN_SK)]
    assert row["sweep_bucket"] == user_repo.TEACHER_SEEN_BUCKET
    assert row["sweep_due_at"] == row["seen_at"] == at()
    assert DEFAULT_INDEXES[user_repo.TEACHER_SEEN_INDEX] == IndexSchema("sweep_bucket", "sweep_due_at")
    # The generation sweep (#502) shares the index and reads its own bucket only.
    assert user_repo.TEACHER_SEEN_INDEX == _store.SWEEP_PENDING_INDEX
    assert user_repo.TEACHER_SEEN_BUCKET != _store.SWEEP_PENDING_BUCKET
    assert _store.query_generation_sweep_commands(now=NOW + timedelta(days=1), table=table) == ([], True)


def test_listing_the_teachers_scans_nothing_and_does_not_grow_with_the_table(table) -> None:
    table.seed(*_account(TEACHER), *_account("teacher-two"), *_account(STUDENT, role="student"))
    for teacher in (TEACHER, "teacher-two"):
        teacher_dispatch_service.record_teacher_seen(teacher, now=at())
    table.requests.clear()

    listed = teacher_dispatch_service.list_teacher_profiles()

    assert sorted(profile["user_id"] for profile in listed) == sorted([TEACHER, "teacher-two"])
    assert all(profile["dispatch_seen_at"] == at() for profile in listed)
    small = _reads(table)
    assert "scan" not in small
    # One query of the index, then every teacher's profile and fence in one batch.
    assert sorted(small) == ["batch_get_item", "query"]

    for index in range(300):
        table.seed({"PK": f"PRACTICE#{index:03d}", "SK": "ROW", "entity_type": "filler"})
    table.requests.clear()

    assert len(teacher_dispatch_service.list_teacher_profiles()) == 2
    assert sorted(_reads(table)) == sorted(small)


def test_a_seen_account_that_cannot_take_dispatch_is_not_listed(table) -> None:
    """A heartbeat row is where to look, not a reason to trust what is found."""
    table.seed(
        *_account(TEACHER),
        *_account("student-seen", role="student"),
        *_account("teacher-inactive"),
        *_account("teacher-leaving"),
    )
    table.rows[("USER#teacher-inactive", "PROFILE")]["account_status"] = "suspended"
    for user_id in (TEACHER, "student-seen", "teacher-inactive", "teacher-leaving"):
        teacher_dispatch_service.record_teacher_seen(user_id, now=at())
    table.rows[("USER#teacher-leaving", "ACCOUNT_FENCE")]["status"] = "deletion_pending"

    listed = teacher_dispatch_service.list_teacher_profiles()

    assert [profile["user_id"] for profile in listed] == [TEACHER]


def test_a_heartbeat_written_before_the_index_counts_from_its_next_stamp(table) -> None:
    """Rows stamped before #609 carry no index keys; the next stamp, a minute on, adds them."""
    from stoa.db.repositories import user_repo

    table.seed(*_account(TEACHER))
    table.seed(
        {
            "PK": f"USER#{TEACHER}",
            "SK": user_repo.TEACHER_SEEN_SK,
            "entity_type": "teacher_seen",
            "user_id": TEACHER,
            "seen_at": at(),
        }
    )

    assert teacher_dispatch_service.list_teacher_profiles() == []

    teacher_dispatch_service.record_teacher_seen(TEACHER, now=at(1.5))

    assert _offered(at(1.5)) == [TEACHER]


def test_the_limit_caps_the_teachers_listed(table) -> None:
    for teacher in ("teacher-a", "teacher-b", "teacher-c"):
        table.seed(*_account(teacher))
        teacher_dispatch_service.record_teacher_seen(teacher, now=at())

    assert len(teacher_dispatch_service.list_teacher_profiles(limit=2)) == 2
    assert teacher_dispatch_service.list_teacher_profiles(limit=0) == []


def test_with_nobody_seen_lately_the_reason_is_that_nobody_is_online(table) -> None:
    """Teachers exist but none has a heartbeat row: that is `not_online`, not no teachers."""
    table.seed(*_account(TEACHER), *_account("teacher-two", availability="paused"))

    plan = teacher_dispatch_service.plan_dispatch(QUESTION, now=at())

    assert plan["refused"] == []
    assert plan["summary"]["noCandidateReason"] == "not_online"
    assert teacher_dispatch_service.teacher_availability_summary(now=at())["online"] is False
