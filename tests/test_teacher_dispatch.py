from stoa.db import table as db_table
from stoa.services import help_requests, teacher_dispatch_service
from fakes.dynamodb import FakeTable, as_stored as _as_stored


QUESTION = _as_stored({
    "question_id": "question-1",
    "student_id": "student-1",
    "subject": "math",
    "status": "escalated",
    "version": 1,
})


TEACHERS = _as_stored([
    {
        "user_id": "teacher-low-load",
        "role": "teacher",
        "account_status": "active",
        "version": 7,
        "account_fence_generation": 3,
        "subjects": ["math"],
        "dispatch_availability": "available",
        "active_session_count": 0,
        "max_active_sessions": 2,
        "recent_sla_bucket": "within_target",
        "last_dispatched_at": "2026-06-15T08:00:00+00:00",
    },
    {
        "user_id": "teacher-busy",
        "role": "teacher",
        "account_status": "active",
        "version": 8,
        "account_fence_generation": 4,
        "subjects": ["math"],
        "dispatch_availability": "available",
        "active_session_count": 2,
        "max_active_sessions": 2,
    },
    {
        "user_id": "teacher-german",
        "role": "teacher",
        "account_status": "active",
        "version": 9,
        "account_fence_generation": 5,
        "subjects": ["german"],
        "dispatch_availability": "available",
        "active_session_count": 0,
        "max_active_sessions": 2,
    },
    {
        "user_id": "teacher-paused",
        "role": "teacher",
        "account_status": "active",
        "version": 10,
        "account_fence_generation": 6,
        "subjects": ["math"],
        "dispatch_availability": "paused",
    },
])


def test_dispatch_planner_ranks_eligible_and_explains_refusals():
    plan = teacher_dispatch_service.plan_dispatch(
        QUESTION,
        TEACHERS,
        now="2026-06-15T10:05:00+00:00",
    )

    assert plan["status"] == "ready"
    assert plan["selected"][0]["teacherId"] == "teacher-low-load"
    refusals = {item["teacherId"]: item["refusalCode"] for item in plan["refused"]}
    assert refusals["teacher-busy"] == "max_active_sessions"
    assert refusals["teacher-german"] == "subject_mismatch"
    assert refusals["teacher-paused"] == "not_available"


def test_dispatch_planner_rejects_inactive_deleting_and_implicit_availability():
    profiles = [
        {
            **TEACHERS[0],
            "user_id": "teacher-inactive",
            "account_status": "inactive",
        },
        {
            **TEACHERS[0],
            "user_id": "teacher-deleting",
            "account_status": "deletion_pending",
        },
        {
            key: value
            for key, value in {
                **TEACHERS[0],
                "user_id": "teacher-missing-availability",
            }.items()
            if key != "dispatch_availability"
        },
    ]

    plan = teacher_dispatch_service.plan_dispatch(QUESTION, profiles)

    assert plan["selected"] == []
    refusals = {item["teacherId"]: item["refusalCode"] for item in plan["refused"]}
    assert refusals["teacher-inactive"] == "inactive_account"
    assert refusals["teacher-deleting"] == "inactive_account"
    assert refusals["teacher-missing-availability"] == "not_available"


def _dispatch_table(*rows: dict) -> FakeTable:
    """A real table for the dispatch scans, plus the account fence they consult.

    The doubles these tests used to carry told the two scans apart by comparing
    `ExpressionAttributeValues` to a literal and answered from a script. That is the
    fifth incident in `fakes/dynamodb.py`: nothing evaluated `FilterExpression`, so a
    scan that had stopped naming `PROFILE` would have got profiles back anyway.
    """
    table = FakeTable()
    table.seed(
        {
            "PK": "USER#teacher-low-load",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": 3,
        }
    )
    for row in rows:
        table.seed(row)
    return table


def _scans_since(table: FakeTable, already_seen: int) -> list[dict]:
    """The scan requests of one walk, so two walks are not read as one."""
    return [call for name, call in table.requests if name == "scan"][already_seen:]


def _profile_row(**overrides: object) -> dict:
    teacher = dict(TEACHERS[0])
    teacher.update(overrides)
    return {"PK": f"USER#{teacher['user_id']}", "SK": "PROFILE", **teacher}


def _help_row(conversation_id: str, **overrides: object) -> dict:
    return {
        "PK": f"CONV#{conversation_id}",
        "SK": "HELP",
        "entity_type": "help_request",
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": "student-1",
        "subject": "math",
        "escalation_status": "pending",
        "escalated_at": "2026-06-15T10:00:00+00:00",
        "version": 1,
        **overrides,
    }


def _help_request_walk(*rows: dict) -> tuple[list[dict], list[dict]]:
    """Every help request on a table whose pages hold one row each, and its scans."""
    table = FakeTable(page_item_cap=1)
    table.seed(*rows)
    found = help_requests.list_all(table=table)
    return found, _scans_since(table, 0)


def test_dispatch_scans_continue_after_sparse_filtered_page(monkeypatch):
    """A page whose rows the filter all drops must not end the walk.

    `Limit` counts rows read, so the first page here is one unrelated row and no
    match at all - the shape that made `/admin/users` answer an empty list forever.
    """
    table = _dispatch_table(
        {"PK": "PRACTICE#0", "SK": "ROW"},
        _profile_row(),
    )
    db_table.install(table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    profile_scans = _scans_since(table, 0)
    # The conversation row sorts before its help request and is filtered out.
    requests, request_scans = _help_request_walk(
        {"PK": "CONV#conv-1", "SK": "CONV", "entity_type": "conversation"},
        _help_row("conv-1"),
    )

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["conversation_id"] for item in requests] == ["conv-1"]
    for walk in (profile_scans, request_scans):
        assert len(walk) > 1, "a filtered-empty page has to be followed, not accepted"
        assert all("ExclusiveStartKey" in call for call in walk[1:])


def test_dispatch_scans_continue_after_nonempty_business_rejected_page(monkeypatch):
    """A page whose rows pass the filter but fail the business rule, likewise.

    The rejected rows below match `SK = :profile` and `entity_type = help_request`
    exactly, so only the business rule can turn them down - which is the branch
    this test is about.
    """
    table = _dispatch_table(
        _profile_row(user_id="student-rejected", role="student"),
        _profile_row(),
    )
    db_table.install(table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    profile_scans = _scans_since(table, 0)
    # A deletion tombstone left in a request's place is no request.
    requests, request_scans = _help_request_walk(
        _help_row("conv-0-rejected", status="deleted", owner_deletion_generation=2),
        _help_row("conv-eligible"),
    )

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["conversation_id"] for item in requests] == ["conv-eligible"]
    for walk in (profile_scans, request_scans):
        assert len(walk) > 1
        assert all("ExclusiveStartKey" in call for call in walk[1:])

