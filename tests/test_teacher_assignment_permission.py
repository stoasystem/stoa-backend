"""#495: a teacher who took a student's help request may assign them practice.

The only relationship that counts (布置练习的权限, CONTEXT.md): the teacher
holds one of the student's help requests in progress, or resolved it, and then
for 14 days after it was resolved. It opens the student's learning profile and
assignments - memory, recommendations, the assignment list, the automation
preview and execute, one assignment, archiving the teacher's own - and nothing
else of the student's. Without it the student is hidden (404).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import actor_from_user
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
    TeacherAuthorizationFacts,
)
from stoa.security.errors import SecurityErrorCode
from stoa.security.identity import Actor, AccountStatus, CanonicalRole
from stoa.services import help_requests
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
TEACHER = "teacher-495"
OTHER_TEACHER = "teacher-495-other"
STUDENT = "student-495"


def _request(**fields: Any) -> dict[str, Any]:
    record = {
        "entity_type": "help_request",
        "conversation_id": "conv-495",
        "escalation_request_id": "conv-495",
        "student_id": STUDENT,
        "teacher_id": TEACHER,
        "escalation_status": "in_progress",
        "dispatch_status": "accepted",
    }
    record.update(fields)
    return {key: value for key, value in record.items() if value is not None}


def _resolved(days_ago: float) -> dict[str, Any]:
    return _request(
        escalation_status="resolved",
        escalation_resolved_at=(NOW - timedelta(days=days_ago)).isoformat(),
    )


# --- The rule, in one place ---


@pytest.mark.parametrize(
    "record",
    [
        _request(),
        _resolved(0),
        _resolved(13.9),
        _resolved(14),
    ],
    ids=["in-progress", "resolved-now", "resolved-13.9-days", "resolved-14-days"],
)
def test_a_teacher_who_took_the_students_request_helped_them(record) -> None:
    assert help_requests.teacher_helped_student([record], TEACHER, STUDENT, now=NOW)


@pytest.mark.parametrize(
    "record",
    [
        _resolved(14.01),
        _request(escalation_status="resolved"),
        _request(escalation_status="resolved", escalation_resolved_at="not a time"),
        # Offered, never taken.
        _request(
            teacher_id=None,
            escalation_status="pending",
            dispatch_status="dispatched",
            dispatched_teacher_id=TEACHER,
        ),
        # Held by somebody else (reassigned away).
        _request(teacher_id=OTHER_TEACHER),
        # Pending with this teacher's name left on it.
        _request(escalation_status="pending"),
        _request(escalation_status="withdrawn"),
        _request(escalation_status="expired"),
        # Closed to this teacher when their account was scrubbed.
        _request(dispatch_status="revoked"),
        # Another student's request.
        _request(student_id="student-other"),
    ],
    ids=[
        "resolved-past-14-days",
        "resolved-without-a-time",
        "resolved-unreadable-time",
        "only-offered",
        "another-teacher-holds-it",
        "pending",
        "withdrawn",
        "expired",
        "revoked",
        "another-student",
    ],
)
def test_nothing_else_is_having_helped_the_student(record) -> None:
    assert not help_requests.teacher_helped_student([record], TEACHER, STUDENT, now=NOW)


def test_any_one_qualifying_request_is_enough() -> None:
    records = [_request(escalation_status="withdrawn"), _resolved(3)]

    assert help_requests.teacher_helped_student(records, TEACHER, STUDENT, now=NOW)


def test_no_requests_no_relationship() -> None:
    assert not help_requests.teacher_helped_student([], TEACHER, STUDENT, now=NOW)


# --- The policy ---


def _teacher_actor(teacher_id: str = TEACHER) -> Actor:
    return Actor(
        teacher_id,
        "https://identity.test",
        f"{teacher_id}-subject",
        CanonicalRole.TEACHER,
        AccountStatus.ACTIVE,
        "teacher",
    )


def _account(user_id: str, role: str, status: str = "active") -> dict[str, Any]:
    return {"user_id": user_id, "role": role, "account_status": status}


def _facts(
    requests: list[dict[str, Any]],
    *,
    learning_assignment: dict[str, Any] | None = None,
    teacher_status: str = "active",
    student_status: str = "active",
) -> AuthorizationFacts:
    return AuthorizationFacts(
        teacher=TeacherAuthorizationFacts(
            student_requests=tuple(requests),
            learning_assignment=learning_assignment,
            teacher_account=_account(TEACHER, "teacher", teacher_status),
            student_account=_account(STUDENT, "student", student_status),
        )
    )


def _decide(
    facts: AuthorizationFacts,
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    *,
    resource_type: ResourceType = ResourceType.ADAPTIVE_PROFILE,
    resource_id: str = STUDENT,
    value: dict[str, Any] | None = None,
):
    resource = AuthorizedResource(
        ResourceRef(resource_type, resource_id, STUDENT), value or {}, facts
    )
    return AuthorizationPolicy(clock=lambda: NOW).evaluate(
        _teacher_actor(), resource, action, purpose
    )


#: What the adaptive routes ask of a teacher (`routers/adaptive.py`).
LEARNING_ROUTES = [
    (AuthorizationAction.READ, AuthorizationPurpose.LEARNING_ASSIGNMENT),  # memory, lists
    (AuthorizationAction.UPDATE, AuthorizationPurpose.LEARNING_ASSIGNMENT),  # refresh
    (AuthorizationAction.ASSIGN, AuthorizationPurpose.LEARNING_ASSIGNMENT),  # one assignment
    (AuthorizationAction.READ, AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW),
    (AuthorizationAction.CREATE, AuthorizationPurpose.ASSIGNMENT_AUTOMATION_EXECUTE),
]


@pytest.mark.parametrize(("action", "purpose"), LEARNING_ROUTES)
def test_the_helping_teacher_may_use_the_students_learning_profile(action, purpose) -> None:
    decision = _decide(_facts([_request()]), action, purpose)

    assert decision.allowed


@pytest.mark.parametrize(("action", "purpose"), LEARNING_ROUTES)
def test_an_unrelated_teacher_is_told_the_student_is_not_there(action, purpose) -> None:
    decision = _decide(_facts([_request(teacher_id=OTHER_TEACHER)]), action, purpose)

    assert not decision.allowed
    assert decision.result_code is SecurityErrorCode.RESOURCE_NOT_FOUND


def test_a_relationship_past_its_14_days_hides_the_student() -> None:
    decision = _decide(
        _facts([_resolved(15)]),
        AuthorizationAction.READ,
        AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW,
    )

    assert not decision.allowed
    assert decision.result_code is SecurityErrorCode.RESOURCE_NOT_FOUND


@pytest.mark.parametrize(
    ("teacher_status", "student_status"), [("suspended", "active"), ("active", "suspended")]
)
def test_an_account_that_is_not_active_ends_it(teacher_status, student_status) -> None:
    decision = _decide(
        _facts([_request()], teacher_status=teacher_status, student_status=student_status),
        AuthorizationAction.READ,
        AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW,
    )

    assert not decision.allowed


@pytest.mark.parametrize(
    "resource_type",
    [
        ResourceType.STUDENT,
        ResourceType.QUESTION,
        ResourceType.CONVERSATION,
        ResourceType.PRACTICE,
        ResourceType.REPORT,
    ],
)
def test_it_opens_nothing_else_of_the_students(resource_type) -> None:
    # The student's other content is read under the same purpose
    # (`STUDENT_CONTENT_READ`); the help relationship is not a key to it.
    decision = _decide(
        _facts([_request()]),
        AuthorizationAction.READ,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_type=resource_type,
    )

    assert not decision.allowed


def test_it_is_not_a_teacher_help_permission_on_the_profile() -> None:
    decision = _decide(
        _facts([_request()]), AuthorizationAction.READ, AuthorizationPurpose.TEACHER_HELP
    )

    assert not decision.allowed


def test_the_teacher_archives_an_assignment_they_made() -> None:
    assignment = {"assignment_id": "assignment-1", "student_id": STUDENT, "created_by": TEACHER}

    decision = _decide(
        _facts([_request()], learning_assignment=assignment),
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_id="assignment-1",
        value=assignment,
    )

    assert decision.allowed


def test_the_teacher_may_not_archive_somebody_elses_assignment() -> None:
    assignment = {"assignment_id": "assignment-1", "student_id": STUDENT, "created_by": "admin-1"}

    decision = _decide(
        _facts([_request()], learning_assignment=assignment),
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_id="assignment-1",
        value=assignment,
    )

    assert not decision.allowed
    # They can see it in the student's list, so it is refused, not hidden.
    assert decision.result_code is SecurityErrorCode.ACTION_NOT_ALLOWED


def test_the_teacher_reads_any_assignment_of_the_student() -> None:
    assignment = {"assignment_id": "assignment-1", "student_id": STUDENT, "created_by": "admin-1"}

    decision = _decide(
        _facts([_request()], learning_assignment=assignment),
        AuthorizationAction.READ,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_id="assignment-1",
        value=assignment,
    )

    assert decision.allowed


def test_an_admin_assignment_row_still_counts() -> None:
    facts = AuthorizationFacts(
        teacher=TeacherAuthorizationFacts(
            assignment={
                "teacher_id": TEACHER,
                "student_id": STUDENT,
                "status": "active",
                "resource_types": [ResourceType.ADAPTIVE_PROFILE.value],
                "actions": [AuthorizationAction.READ.value],
                "purposes": [AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW.value],
            },
            teacher_account=_account(TEACHER, "teacher"),
            student_account=_account(STUDENT, "student"),
        )
    )

    decision = _decide(
        facts, AuthorizationAction.READ, AuthorizationPurpose.ASSIGNMENT_AUTOMATION_PREVIEW
    )

    assert decision.allowed


# --- The facts, as production loads them ---


@pytest.fixture
def stored(monkeypatch):
    from stoa.db.repositories import question_repo, user_repo

    requests: dict[str, list[dict[str, Any]]] = {STUDENT: [_request()]}
    asked: list[str] = []

    def for_student(student_id, *, table=None):
        asked.append(student_id)
        return {str(i): record for i, record in enumerate(requests.get(student_id, []))}

    monkeypatch.setattr(help_requests, "for_student", for_student)
    monkeypatch.setattr(question_repo, "get_teacher_assignment", lambda *_args: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id: _account(
            user_id, "teacher" if user_id.startswith("teacher") else "student"
        ),
    )
    return requests, asked


def _load(
    action: AuthorizationAction,
    purpose: AuthorizationPurpose,
    *,
    resource_type: ResourceType = ResourceType.ADAPTIVE_PROFILE,
    resource_id: str = STUDENT,
    value: dict[str, Any] | None = None,
) -> AuthorizationFacts:
    import asyncio

    return asyncio.run(
        CurrentAuthorizationFactRepository().facts_for(
            _teacher_actor(),
            ResourceRef(resource_type, resource_id, STUDENT),
            action,
            purpose,
            value or _account(STUDENT, "student"),
        )
    )


@pytest.mark.parametrize(("action", "purpose"), LEARNING_ROUTES)
def test_the_students_requests_are_read_for_the_learning_profile(stored, action, purpose) -> None:
    _requests, asked = stored

    facts = _load(action, purpose)

    assert asked == [STUDENT]
    assert facts.teacher is not None
    assert facts.teacher.student_requests == (_request(),)
    assert facts.teacher.learning_assignment is None


def test_they_are_not_read_for_anything_else(stored) -> None:
    _requests, asked = stored

    facts = _load(
        AuthorizationAction.READ,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_type=ResourceType.STUDENT,
    )

    assert asked == []
    assert facts.teacher is not None
    assert facts.teacher.student_requests == ()


def test_an_assignment_is_carried_with_its_maker(stored) -> None:
    assignment = {"assignment_id": "assignment-1", "student_id": STUDENT, "created_by": TEACHER}

    facts = _load(
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.LEARNING_ASSIGNMENT,
        resource_id="assignment-1",
        value=assignment,
    )

    assert facts.teacher is not None
    assert facts.teacher.learning_assignment == assignment


# --- The routes, end to end through the real fact loader ---


def _adaptive(user: dict[str, Any]) -> TestClient:
    from stoa.routers import adaptive

    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_actor] = lambda: actor_from_user(user)
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


@pytest.fixture
def automation(stored, monkeypatch):
    from stoa.services import adaptive_learning_service

    calls: list[str] = []

    def preview(**kwargs):
        calls.append(f"preview:{kwargs['student_id']}")
        return {"batchId": "batch-1", "selected": [], "refused": []}

    def listed(**kwargs):
        calls.append(f"list:{kwargs['student_id']}")
        return {"items": [], "count": 0}

    monkeypatch.setattr(adaptive_learning_service, "preview_assignment_automation_batch", preview)
    monkeypatch.setattr(adaptive_learning_service, "list_assignments", listed)
    return stored[0], calls


def test_the_helping_teacher_previews_and_lists_through_the_routes(automation) -> None:
    _requests, calls = automation
    client = _adaptive({"sub": TEACHER, "role": "teacher"})

    preview = client.post(f"/adaptive/students/{STUDENT}/assignment-automation/batches/preview")
    listed = client.get(f"/adaptive/students/{STUDENT}/assignments")

    assert preview.status_code == 200, preview.text
    assert listed.status_code == 200, listed.text
    assert calls == [f"preview:{STUDENT}", f"list:{STUDENT}"]


def test_another_teacher_gets_404_before_the_service_runs(automation) -> None:
    _requests, calls = automation
    client = _adaptive({"sub": OTHER_TEACHER, "role": "teacher"})

    preview = client.post(f"/adaptive/students/{STUDENT}/assignment-automation/batches/preview")
    listed = client.get(f"/adaptive/students/{STUDENT}/assignments")

    assert preview.status_code == 404, preview.text
    assert listed.status_code == 404, listed.text
    assert calls == []


def test_the_relationship_ends_14_days_after_resolving(automation) -> None:
    requests, calls = automation
    requests[STUDENT] = [
        _request(
            escalation_status="resolved",
            escalation_resolved_at=(datetime.now(UTC) - timedelta(days=15)).isoformat(),
        )
    ]
    client = _adaptive({"sub": TEACHER, "role": "teacher"})

    response = client.post(
        f"/adaptive/students/{STUDENT}/assignment-automation/batches/preview"
    )

    assert response.status_code == 404, response.text
    assert calls == []


def test_an_admin_with_the_capability_is_unchanged(automation) -> None:
    _requests, calls = automation
    requests = automation[0]
    requests[STUDENT] = []
    client = _adaptive(
        {"sub": "admin-1", "role": "admin", "grantScope": f"student:{STUDENT}"}
    )

    response = client.post(
        f"/adaptive/students/{STUDENT}/assignment-automation/batches/preview"
    )

    assert response.status_code == 200, response.text
    assert calls == [f"preview:{STUDENT}"]


def test_an_admin_without_the_capability_is_still_refused(automation) -> None:
    _requests, calls = automation
    client = _adaptive(
        {
            "sub": "admin-1",
            "role": "admin",
            "grantScope": f"student:{STUDENT}",
            "grantCapabilities": ("assignment_automation_preview",),
        }
    )

    response = client.post(
        f"/adaptive/students/{STUDENT}/assignment-automation/batches/execute",
        json={
            "batchId": "batch-1",
            "approved": True,
            "candidates": [{"candidateId": "c", "sourceType": "ai_draft", "sourceId": "d"}],
        },
    )

    assert response.status_code in {403, 404}, response.text
    assert calls == []


# --- The teacher reaches the student from the help request ---


def test_the_help_request_list_names_the_student(table) -> None:
    from test_chat_help_request_lifecycle import STUDENT as LISTED_STUDENT
    from test_chat_help_request_lifecycle import TEACHER as LISTED_TEACHER
    from test_chat_help_request_lifecycle import _client, _dispatch_to

    _dispatch_to(table, LISTED_TEACHER)

    [listed] = _client().get("/teachers/me/help-requests").json()["items"]

    assert listed["studentId"] == LISTED_STUDENT
