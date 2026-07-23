from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.routers import admin, teachers
from stoa.services import teacher_dispatch_service
from actor_helpers import install_actor_overrides


def _app(router, prefix: str, user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    install_actor_overrides(app, user)
    return TestClient(app)


QUESTION = {
    "question_id": "question-1",
    "student_id": "student-1",
    "subject": "math",
    "status": "escalated",
    "teacher_requested_at": "2026-06-15T10:00:00+00:00",
    "queue_visible_at": "2026-06-15T10:00:00+00:00",
    "version": 1,
}


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


TEACHERS = [
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
]


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


def test_dispatch_question_conditionally_claims_best_teacher(monkeypatch):
    updates = []
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", lambda question_id: dict(QUESTION))
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "mutate_question",
        lambda question, *, status, extra_attrs, **_kwargs: updates.append(
            (question["question_id"], status, extra_attrs)
        )
        or _applied_mutation(question, status, extra_attrs),
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "dispatched"
    assert result["teacherId"] == "teacher-low-load"
    assert updates[0][2]["dispatch_status"] == "dispatched"
    assert updates[0][2]["dispatched_teacher_id"] == "teacher-low-load"
    assert updates[0][2]["dispatch_attempt_count"] == 1


def test_dispatch_assignment_atomically_observes_teacher_profile_and_fence(monkeypatch):
    mutations = []
    monkeypatch.setattr(
        teacher_dispatch_service,
        "list_teacher_profiles",
        lambda: [TEACHERS[0]],
    )
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "get_question",
        lambda question_id: dict(QUESTION),
    )

    def mutate_question(question, *, status, extra_attrs, **kwargs):
        mutations.append(kwargs)
        return _applied_mutation(question, status, extra_attrs)

    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "mutate_question",
        mutate_question,
    )

    result = teacher_dispatch_service.dispatch_question("question-1")

    assert result["status"] == "dispatched"
    conditions = mutations[0]["additional_conditions"]
    assert conditions[0]["ConditionCheck"]["Key"] == {
        "PK": "USER#teacher-low-load",
        "SK": "ACCOUNT_FENCE",
    }
    profile = conditions[1]["ConditionCheck"]
    assert profile["Key"] == {
        "PK": "USER#teacher-low-load",
        "SK": "PROFILE",
    }
    assert profile["ExpressionAttributeValues"] == {
        ":teacher_id": "teacher-low-load",
        ":teacher_role": "teacher",
        ":active": "active",
        ":teacher_profile_version": 7,
    }


class _SparseDispatchScanTable:
    def __init__(self):
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(dict(kwargs))
        if "ExclusiveStartKey" not in kwargs:
            return {
                "Items": [],
                "LastEvaluatedKey": {"PK": "UNRELATED#last", "SK": "ROW"},
            }
        if kwargs["ExpressionAttributeValues"] == {":profile": "PROFILE"}:
            return {"Items": [dict(TEACHERS[0])]}
        return {"Items": [dict(QUESTION)]}

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        assert Key == {
            "PK": "USER#teacher-low-load",
            "SK": "ACCOUNT_FENCE",
        }
        return {
            "Item": {
                **Key,
                "status": "active",
                "generation": 3,
            }
        }


def test_dispatch_scans_continue_after_sparse_filtered_page(monkeypatch):
    table = _SparseDispatchScanTable()
    monkeypatch.setattr(teacher_dispatch_service, "get_table", lambda: table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    questions = teacher_dispatch_service.list_teacher_dispatch_questions(limit=1)

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["question_id"] for item in questions] == ["question-1"]
    assert len(table.calls) == 4
    assert all(
        "ExclusiveStartKey" in call
        for call in (table.calls[1], table.calls[3])
    )


class _BusinessFilteredDispatchScanTable:
    def __init__(self):
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(dict(kwargs))
        is_profile = kwargs["ExpressionAttributeValues"] == {":profile": "PROFILE"}
        if "ExclusiveStartKey" not in kwargs:
            item = (
                {
                    **TEACHERS[0],
                    "user_id": "student-rejected",
                    "role": "student",
                }
                if is_profile
                else {
                    **QUESTION,
                    "status": "pending",
                    "teacher_requested_at": None,
                    "queue_visible_at": None,
                }
            )
            return {
                "Items": [item],
                "LastEvaluatedKey": {
                    "PK": "REJECTED#last",
                    "SK": "PROFILE" if is_profile else "META",
                },
            }
        return {
            "Items": [
                dict(TEACHERS[0])
                if is_profile
                else {**QUESTION, "question_id": "question-eligible"}
            ]
        }

    def get_item(self, *, Key, ConsistentRead=True):  # noqa: N803
        assert ConsistentRead is True
        assert Key == {
            "PK": "USER#teacher-low-load",
            "SK": "ACCOUNT_FENCE",
        }
        return {
            "Item": {
                **Key,
                "status": "active",
                "generation": 3,
            }
        }


def test_dispatch_scans_continue_after_nonempty_business_rejected_page(monkeypatch):
    table = _BusinessFilteredDispatchScanTable()
    monkeypatch.setattr(teacher_dispatch_service, "get_table", lambda: table)

    teachers = teacher_dispatch_service.list_teacher_profiles(limit=1)
    questions = teacher_dispatch_service.list_teacher_dispatch_questions(limit=1)

    assert [item["user_id"] for item in teachers] == ["teacher-low-load"]
    assert [item["question_id"] for item in questions] == ["question-eligible"]
    assert len(table.calls) == 4
    assert all(
        "ExclusiveStartKey" in call
        for call in (table.calls[1], table.calls[3])
    )


def test_dispatch_question_uses_fresh_escalation_snapshot(monkeypatch):
    updates = []
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "get_question",
        lambda question_id: {**QUESTION, "status": "ai_answered"},
    )
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "mutate_question",
        lambda question, *, status, extra_attrs, **_kwargs: updates.append(
            (question["question_id"], status, extra_attrs)
        )
        or _applied_mutation(question, status, extra_attrs),
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        question=dict(QUESTION),
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "dispatched"
    assert updates[0][2]["dispatched_teacher_id"] == "teacher-low-load"


def test_dispatch_question_reports_claim_conflict(monkeypatch):
    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: [TEACHERS[0]])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", lambda question_id: dict(QUESTION))
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "mutate_question",
        lambda question, **_kwargs: teacher_dispatch_service.question_repo.QuestionMutationResult(
            teacher_dispatch_service.question_repo.QuestionMutationDisposition.STALE,
            str(question["question_id"]),
        ),
    )

    result = teacher_dispatch_service.dispatch_question(
        "question-1",
        now="2026-06-15T10:05:00+00:00",
    )

    assert result["status"] == "claim_conflict"


def test_reassign_timed_out_dispatch_excludes_previous_teacher(monkeypatch):
    stale_question = {
        **QUESTION,
        "dispatch_status": "dispatched",
        "dispatched_teacher_id": "teacher-low-load",
        "dispatch_deadline_at": "2026-06-15T10:10:00+00:00",
        "dispatch_attempt_count": 1,
    }
    updates = []
    questions = {
        "question-1": dict(stale_question),
    }

    def get_question(question_id):
        return questions[question_id]

    def mutate_question(question, *, status, extra_attrs, **_kwargs):
        question_id = str(question["question_id"])
        attrs = dict(extra_attrs)
        updates.append((question_id, status, attrs))
        result = _applied_mutation(question, status, attrs)
        questions[question_id] = dict(result.question or {})
        return result

    monkeypatch.setattr(teacher_dispatch_service, "list_teacher_profiles", lambda: TEACHERS[:2])
    monkeypatch.setattr(teacher_dispatch_service.question_repo, "get_question", get_question)
    monkeypatch.setattr(
        teacher_dispatch_service.question_repo,
        "mutate_question",
        mutate_question,
    )

    result = teacher_dispatch_service.reassign_timed_out_dispatches(
        [stale_question],
        now="2026-06-15T10:15:00+00:00",
    )

    assert result["processed"] == 1
    assert updates[0][2]["dispatch_status"] == "timed_out"
    assert updates[0][2]["previous_dispatch_teacher_ids"] == ["teacher-low-load"]
    assert result["results"][0]["status"] == "no_candidate"
    assert result["results"][0]["plan"]["summary"]["noCandidateReason"] == "max_active_sessions"


def test_teacher_queue_filters_dispatches_owned_by_other_teachers(monkeypatch):
    items = [
        {**QUESTION, "question_id": "mine", "dispatch_status": "dispatched", "dispatched_teacher_id": "teacher-1"},
        {**QUESTION, "question_id": "other", "dispatch_status": "dispatched", "dispatched_teacher_id": "teacher-2"},
        {**QUESTION, "question_id": "manual", "dispatch_status": "unassigned"},
    ]
    monkeypatch.setattr(teachers, "_list_escalated_questions", lambda: items)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-15T10:05:00+00:00")

    response = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}).get("/teachers/queue")

    assert response.status_code == 200
    ids = {item["question_id"] for item in response.json()["items"]}
    assert ids == {"mine", "manual"}
    mine = next(item for item in response.json()["items"] if item["question_id"] == "mine")
    assert mine["dispatch"]["assignedToMe"] is True


def test_takeover_accepts_current_dispatch_and_rejects_other_teacher(monkeypatch):
    claims = []
    item = {
        **QUESTION,
        "dispatch_status": "dispatched",
        "dispatched_teacher_id": "teacher-1",
        "dispatch_deadline_at": "2099-06-15T10:15:00+00:00",
    }

    table = object()
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: "2026-06-15T10:05:00+00:00")
    monkeypatch.setattr(teachers.question_repo, "get_question", lambda question_id: item)
    monkeypatch.setattr(
        teachers.question_repo,
        "claim_teacher_takeover",
        lambda question_id, teacher_id, **attrs: claims.append(
            (question_id, teacher_id, attrs)
        )
        or teachers.question_repo.TeacherTakeoverResult(
            teachers.question_repo.TeacherTakeoverDisposition.CLAIMED,
            question_id,
            session_id="session-1",
        ),
    )

    other = _app(teachers.router, "/teachers", {"sub": "teacher-2", "role": "teacher"}).post(
        "/teachers/questions/question-1/takeover"
    )
    assert other.status_code == 404

    mine = _app(teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}).post(
        "/teachers/questions/question-1/takeover"
    )
    assert mine.status_code == 200
    assert claims[0][1] == "teacher-1"
    assert claims[0][2]["claimed_at"] == "2026-06-15T10:05:00+00:00"
    assert claims[0][2]["table"] is table


def test_teacher_queue_projects_metadata_without_student_content(monkeypatch):
    monkeypatch.setattr(
        teachers,
        "_list_escalated_questions",
        lambda: [{**QUESTION, "content": "private answer", "student_profile": {"name": "Hidden"}}],
    )
    response = _app(
        teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}
    ).get("/teachers/queue")

    assert response.status_code == 200
    serialized = str(response.json())
    assert "private answer" not in serialized
    assert "Hidden" not in serialized
    assert "student_id" not in serialized


def test_dispatch_controls_require_exact_local_capability(monkeypatch):
    monkeypatch.setattr(teachers.question_repo, "get_question", lambda _id: dict(QUESTION))
    monkeypatch.setattr(
        teachers.teacher_dispatch_service,
        "plan_dispatch",
        lambda item, now: {"questionId": item["question_id"], "status": "ready"},
    )
    plain = _app(
        teachers.router, "/teachers", {"sub": "teacher-1", "role": "teacher"}
    ).post("/teachers/dispatch/preview", json={"question_id": "question-1"})
    operator = _app(
        teachers.router,
        "/teachers",
        {
            "sub": "teacher-1",
            "role": "teacher",
            "grantCapabilities": ["teacher_dispatch_operator"],
            "grantScope": "global",
        },
    ).post("/teachers/dispatch/preview", json={"question_id": "question-1"})

    assert plain.status_code == 403
    assert operator.status_code == 200


def test_suspended_teacher_cannot_take_over_and_mutation_does_not_run(monkeypatch):
    claims = []
    monkeypatch.setattr(teachers.question_repo, "get_question", lambda _id: dict(QUESTION))
    monkeypatch.setattr(
        teachers.question_repo,
        "claim_teacher_takeover",
        lambda *args, **kwargs: claims.append((args, kwargs)),
    )
    response = _app(
        teachers.router,
        "/teachers",
        {"sub": "teacher-1", "role": "teacher", "accountStatus": "suspended"},
    ).post("/teachers/questions/question-1/takeover")

    assert response.status_code == 404
    assert claims == []


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
