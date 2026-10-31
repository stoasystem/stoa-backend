
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import admin, teachers
from stoa.services import teacher_dispatch_service
from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable, as_stored as _as_stored


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
    return TestClient(app)


QUESTION = _as_stored({
    "question_id": "question-1",
    "student_id": "student-1",
    "subject": "math",
    "status": "escalated",
    "teacher_requested_at": "2026-06-15T10:00:00+00:00",
    "queue_visible_at": "2026-06-15T10:00:00+00:00",
    "version": 1,
})


def _applied_mutation(question, status, attrs):
    updated = {
        **question,
        "status": status,
        "version": int(question["version"]) + 1,
        **attrs,
    }
    return teacher_dispatch_service.question_repo.QuestionMutationResult(
        teacher_dispatch_service.question_repo.QuestionMutationDisposition.APPLIED,
        str(question["question_id"]),
        updated,
    )


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


def _question_row(**overrides: object) -> dict:
    question = dict(QUESTION)
    question.update(overrides)
    return {"PK": f"QUESTION#{question['question_id']}", "SK": "META", **question}


def test_dispatch_scans_continue_after_sparse_filtered_page(monkeypatch):
    """A page whose rows the filter all drops must not end the walk.

    `Limit` counts rows read, so the first page here is one unrelated row and no
    match at all - the shape that made `/admin/users` answer an empty list forever.
    """
    table = _dispatch_table(
        {"PK": "PRACTICE#0", "SK": "ROW"},
        _profile_row(),
        _question_row(),
    )
    monkeypatch.setattr(teacher_dispatch_service, "get_table", lambda: table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    profile_scans = _scans_since(table, 0)
    questions = teacher_dispatch_service.list_teacher_dispatch_questions(limit=1)
    question_scans = _scans_since(table, len(profile_scans))

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["question_id"] for item in questions] == ["question-1"]
    for walk in (profile_scans, question_scans):
        assert len(walk) > 1, "a filtered-empty page has to be followed, not accepted"
        assert all("ExclusiveStartKey" in call for call in walk[1:])


def test_dispatch_scans_continue_after_nonempty_business_rejected_page(monkeypatch):
    """A page whose rows pass the filter but fail the business rule, likewise.

    The rejected rows below match `SK = :profile` and `SK = :meta` exactly, so only
    `accept_item` can turn them down - which is the branch this test is about.
    """
    table = _dispatch_table(
        _profile_row(user_id="student-rejected", role="student"),
        _profile_row(),
        _question_row(
            question_id="question-0-rejected",
            status="pending",
            teacher_requested_at=None,
            queue_visible_at=None,
        ),
        _question_row(question_id="question-eligible"),
    )
    monkeypatch.setattr(teacher_dispatch_service, "get_table", lambda: table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    profile_scans = _scans_since(table, 0)
    questions = teacher_dispatch_service.list_teacher_dispatch_questions(limit=1)
    question_scans = _scans_since(table, len(profile_scans))

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["question_id"] for item in questions] == ["question-eligible"]
    for walk in (profile_scans, question_scans):
        assert len(walk) > 1
        assert all("ExclusiveStartKey" in call for call in walk[1:])


def test_admin_dispatch_dashboard_is_aggregate_and_content_safe(monkeypatch):
    questions = [
        {
            **QUESTION,
            "question_id": "question-old",
            "content": "private student content",
            "dispatch_status": "dispatched",
            "dispatched_teacher_id": "teacher-low-load",
            "dispatch_deadline_at": "2026-06-15T10:10:00+00:00",
            "dispatch_attempt_count": 2,
        },
        {
            **QUESTION,
            "question_id": "question-no-candidate",
            "dispatch_status": "unassigned",
            "dispatch_no_candidate_reason": "subject_mismatch",
        },
    ]
    monkeypatch.setattr(admin.teacher_dispatch_service, "list_teacher_dispatch_questions", lambda: questions)
    monkeypatch.setattr(admin.teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(admin.teacher_dispatch_service, "_now", lambda: "2026-06-15T10:15:00+00:00")

    response = _app(admin.router, "/admin", {"sub": "admin-1", "role": "admin"}).get(
        "/admin/teacher-dispatch/dashboard"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["queue"]["count"] == 2
    assert body["queue"]["timeoutCount"] == 1
    assert body["queue"]["reassignmentCount"] == 1
    assert body["queue"]["noCandidateReasons"] == {"subject_mismatch": 1}
    serialized = str(body)
    assert "private student content" not in serialized


def _paged_scan_table(rows, page_rows: int = 50) -> FakeTable:
    """A real table whose response cap falls after `page_rows` rows read.

    `Limit` and the response cap both count evaluated rows, so a page can come back
    empty while escalated questions wait two pages further on. The double this
    replaced cut the page correctly but was still hand-written; the cap now comes
    from the shared one.
    """
    table = FakeTable(page_item_cap=page_rows)
    table.seed(*rows)
    return table


def _queue_rows(*, answered: int, escalated: int):
    rows = [
        {
            **QUESTION,
            "PK": f"QUESTION#answered-{index}",
            "SK": "META",
            "question_id": f"answered-{index}",
            "status": "answered",
        }
        for index in range(answered)
    ]
    rows += [
        {
            **QUESTION,
            "PK": f"QUESTION#waiting-{index}",
            "SK": "META",
            "question_id": f"waiting-{index}",
        }
        for index in range(escalated)
    ]
    return rows


def _queue_response(monkeypatch, table):
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-15T10:05:00+00:00")
    return _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}).get(
        "/teachers/queue"
    )


