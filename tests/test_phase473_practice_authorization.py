"""Plan 473-26 exact teacher course/class answer authorization contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_authorization_audit_sink
from stoa.routers import practice
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizedResource,
    CurrentAuthorizationFactRepository,
    CurriculumAnswerAuthorizationFacts,
    ResourceRef,
    ResourceType,
)
from stoa.security.errors import SecurityErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository


ANSWER_CANARY = "STANDARD-ANSWER-473-26-CANARY"
EXPLANATION_CANARY = "EXPLANATION-473-26-CANARY"
ASSIGNMENT_CANARY = "ASSIGNMENT-COORDINATE-473-26-CANARY"
NOW = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


def _actor(role: CanonicalRole, user_id: str | None = None) -> Actor:
    actor_id = user_id or f"{role.value}-1"
    return Actor(
        actor_id,
        "https://identity.test",
        f"{actor_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        (),
    )


def _challenge(**overrides: Any) -> dict[str, Any]:
    challenge = {
        "challenge_id": "challenge-1",
        "challenge_version": "sha256:" + "a" * 64,
        "challenge_content_hash": "a" * 64,
        "course_id": "course-1",
        "class_id": "class-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "grade_level": "secondary",
        "prompt": "Solve x + 4 = 9.",
        "correct_answer": ANSWER_CANARY,
        "explanation": EXPLANATION_CANARY,
        "correct_feedback": "Correct.",
        "incorrect_feedback": "Use the inverse operation.",
    }
    challenge.update(overrides)
    return challenge


def _resource(**overrides: Any) -> AuthorizedResource:
    challenge = _challenge(**overrides)
    return AuthorizedResource(
        ResourceRef(
            ResourceType.CURRICULUM_ANSWER,
            challenge["challenge_id"],
            challenge["challenge_id"],
            course_id=challenge.get("course_id"),
            class_id=challenge.get("class_id"),
            lesson_id=challenge.get("lesson_id"),
            subject_id=challenge.get("subject_id"),
            grade_level=challenge.get("grade_level"),
        ),
        challenge,
    )


def _assignment(**overrides: Any) -> dict[str, Any]:
    assignment = {
        "PK": "TEACHER_ASSIGNMENT#teacher-1",
        "SK": "CURRICULUM#CURRENT",
        "entity_type": "teacher_curriculum_assignment",
        "version": 7,
        "teacher_id": "teacher-1",
        "status": "active",
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "curriculum_scope": {
            "course_id": "course-1",
            "class_id": "class-1",
            "subject_id": "math",
            "grade_level": "secondary",
        },
        "resource_types": ["curriculum_answer"],
        "actions": ["read"],
        "purposes": ["curriculum_answer_read"],
    }
    assignment.update(overrides)
    return assignment


def _policy_decision(
    assignment: dict[str, Any] | None,
    *,
    resource: AuthorizedResource | None = None,
    actor_id: str = "teacher-1",
    account_status: str = "active",
    action: AuthorizationAction = AuthorizationAction.READ,
):
    target = resource or _resource()
    return AuthorizationPolicy(clock=lambda: NOW).evaluate(
        _actor(CanonicalRole.TEACHER, actor_id),
        AuthorizedResource(
            target.ref,
            target.value,
            AuthorizationFacts(
                curriculum_answer=CurriculumAnswerAuthorizationFacts(
                    assignment=assignment,
                    teacher_account={
                        "user_id": actor_id,
                        "role": "teacher",
                        "account_status": account_status,
                    },
                )
            ),
        ),
        action,
        AuthorizationPurpose.CURRICULUM_ANSWER_READ,
    )


def test_teacher_requires_exact_course_and_class_before_optional_narrowing() -> None:
    assert _policy_decision(_assignment()).allowed is True

    subject_grade_only = _assignment(
        curriculum_scope={"subject_id": "math", "grade_level": "secondary"}
    )
    denied = _policy_decision(subject_grade_only)
    assert denied.allowed is False
    assert denied.result_code is SecurityErrorCode.RESOURCE_NOT_FOUND


@pytest.mark.parametrize(
    "scope",
    [
        {"course_id": "course-1"},
        {"class_id": "class-1"},
        {"course_id": "course-2", "class_id": "class-1"},
        {"course_id": "course-1", "class_id": "class-2"},
        {"course_id": True, "class_id": "class-1"},
        {"course_id": "course-1", "class_id": ["class-1", False]},
        {"course_id": {"course-1": True}, "class_id": "class-1"},
    ],
    ids=[
        "missing-class",
        "missing-course",
        "other-course",
        "other-class",
        "boolean-course",
        "coerced-class-member",
        "mapping-course",
    ],
)
def test_missing_cross_scope_or_malformed_course_class_denies(scope: object) -> None:
    decision = _policy_decision(_assignment(curriculum_scope=scope))
    assert decision.allowed is False
    assert decision.result_code is SecurityErrorCode.RESOURCE_NOT_FOUND


@pytest.mark.parametrize(
    "scope",
    [
        {
            "course_id": "course-1",
            "class_id": "class-1",
            "subject_id": "physics",
        },
        {
            "course_id": "course-1",
            "class_id": "class-1",
            "grade_level": "primary",
        },
        {
            "course_id": "course-1",
            "class_id": "class-1",
            "lesson_id": "lesson-2",
        },
    ],
)
def test_subject_grade_and_lesson_only_narrow_exact_course_class(scope: object) -> None:
    assert not _policy_decision(_assignment(curriculum_scope=scope)).allowed


@pytest.mark.parametrize(
    "assignment,actor_id,account_status",
    [
        (None, "teacher-1", "active"),
        (_assignment(status="pending"), "teacher-1", "active"),
        (_assignment(status="revoked"), "teacher-1", "active"),
        (_assignment(expires_at=NOW.isoformat()), "teacher-1", "active"),
        (_assignment(expires_at="not-a-timestamp"), "teacher-1", "active"),
        (_assignment(teacher_id="teacher-2"), "teacher-1", "active"),
        (_assignment(), "teacher-1", "disabled"),
        (_assignment(version=True), "teacher-1", "active"),
        (_assignment(PK=ASSIGNMENT_CANARY), "teacher-1", "active"),
        (_assignment(resource_types="curriculum_answer"), "teacher-1", "active"),
        (_assignment(actions=[True]), "teacher-1", "active"),
        (_assignment(purposes={"curriculum_answer_read": True}), "teacher-1", "active"),
    ],
)
def test_non_current_malformed_or_actor_mismatched_assignment_denies(
    assignment: dict[str, Any] | None,
    actor_id: str,
    account_status: str,
) -> None:
    decision = _policy_decision(
        assignment,
        actor_id=actor_id,
        account_status=account_status,
    )
    assert decision.allowed is False
    assert decision.result_code is SecurityErrorCode.RESOURCE_NOT_FOUND


def test_assignment_repository_reads_exact_current_key_consistently(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class Table:
        def get_item(self, **kwargs):
            calls.append(kwargs)
            return {"Item": _assignment()}

    monkeypatch.setattr(question_repo, "get_table", lambda: Table())
    assert question_repo.get_teacher_curriculum_assignment("teacher-1") == _assignment()
    assert calls == [
        {
            "Key": {
                "PK": "TEACHER_ASSIGNMENT#teacher-1",
                "SK": "CURRICULUM#CURRENT",
            },
            "ConsistentRead": True,
        }
    ]


@pytest.mark.asyncio
async def test_current_fact_repository_reloads_assignment_and_account_each_request(
    monkeypatch,
) -> None:
    assignments = [_assignment(), _assignment(status="revoked")]
    assignment_loads: list[str] = []
    account_loads: list[str] = []

    def load_assignment(teacher_id: str):
        assignment_loads.append(teacher_id)
        return assignments[len(assignment_loads) - 1]

    def load_account(teacher_id: str):
        account_loads.append(teacher_id)
        return {
            "user_id": teacher_id,
            "role": "teacher",
            "account_status": "active",
        }

    monkeypatch.setattr(question_repo, "get_teacher_curriculum_assignment", load_assignment)
    monkeypatch.setattr(user_repo, "get_user", load_account)
    repo = CurrentAuthorizationFactRepository()
    actor = _actor(CanonicalRole.TEACHER)
    target = _resource()

    first = await repo.facts_for(
        actor,
        target.ref,
        AuthorizationAction.READ,
        AuthorizationPurpose.CURRICULUM_ANSWER_READ,
        target.value,
    )
    second = await repo.facts_for(
        actor,
        target.ref,
        AuthorizationAction.READ,
        AuthorizationPurpose.CURRICULUM_ANSWER_READ,
        target.value,
    )

    assert first.curriculum_answer is not None
    assert first.curriculum_answer.assignment["status"] == "active"
    assert second.curriculum_answer is not None
    assert second.curriculum_answer.assignment["status"] == "revoked"
    assert assignment_loads == ["teacher-1", "teacher-1"]
    assert account_loads == ["teacher-1", "teacher-1"]


def test_admin_is_global_read_only_and_teacher_read_never_grants_mutation() -> None:
    policy = AuthorizationPolicy(clock=lambda: NOW)
    resource = _resource()
    admin = _actor(CanonicalRole.ADMIN)
    assert policy.evaluate(
        admin,
        resource,
        AuthorizationAction.READ,
        AuthorizationPurpose.CURRICULUM_ANSWER_READ,
    ).allowed

    for action in (
        AuthorizationAction.CREATE,
        AuthorizationAction.UPDATE,
        AuthorizationAction.DELETE,
        AuthorizationAction.CURRICULUM_MUTATION,
    ):
        assert not policy.evaluate(
            admin,
            resource,
            action,
            AuthorizationPurpose.CURRICULUM_ANSWER_READ,
        ).allowed
        assert not _policy_decision(_assignment(), action=action).allowed


class _MutableFacts:
    def __init__(self, assignment: dict[str, Any] | None) -> None:
        self.assignment = assignment
        self.loads = 0

    async def facts_for(self, actor, *_args):
        self.loads += 1
        if actor.role is not CanonicalRole.TEACHER:
            return AuthorizationFacts()
        return AuthorizationFacts(
            curriculum_answer=CurriculumAnswerAuthorizationFacts(
                assignment=self.assignment,
                teacher_account={
                    "user_id": actor.user_id,
                    "role": "teacher",
                    "account_status": actor.account_status.value,
                },
            )
        )


def _client(
    monkeypatch,
    *,
    role: str,
    assignment: dict[str, Any] | None = None,
    challenge: dict[str, Any] | None = None,
):
    canonical = challenge or _challenge()
    challenge_loads: list[str] = []

    def load(challenge_id: str):
        challenge_loads.append(challenge_id)
        return dict(canonical) if challenge_id == canonical["challenge_id"] else None

    monkeypatch.setattr(practice.practice_repo, "get_challenge", load)
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    actor = install_actor_overrides(app, {"sub": f"{role}-1", "role": role})
    facts = _MutableFacts(assignment)
    audit = MemoryAuthorizationAuditSink()
    app.dependency_overrides[get_authorization_fact_repository] = lambda: facts
    app.dependency_overrides[get_authorization_audit_sink] = lambda: audit
    return TestClient(app), actor, facts, challenge_loads, audit


def _answer_path(challenge_id: str = "challenge-1") -> str:
    return f"/practice/curriculum/challenges/{challenge_id}/answer"


def test_route_allows_only_exact_current_teacher_assignment_and_reloads_facts(
    monkeypatch,
) -> None:
    client, _, facts, loads, _ = _client(
        monkeypatch,
        role="teacher",
        assignment=_assignment(),
    )
    allowed = client.get(_answer_path())
    assert allowed.status_code == 200
    assert allowed.json()["standardAnswer"] == ANSWER_CANARY
    assert loads == ["challenge-1"]
    assert facts.loads == 1

    facts.assignment = _assignment(status="revoked")
    denied = client.get(_answer_path())
    assert denied.status_code == 404
    assert ANSWER_CANARY not in denied.text
    assert loads == ["challenge-1", "challenge-1"]
    assert facts.loads == 2


def test_route_subject_grade_overlap_and_request_spoofing_cannot_authorize(
    monkeypatch,
) -> None:
    client, _, _, _, _ = _client(
        monkeypatch,
        role="teacher",
        assignment=_assignment(
            curriculum_scope={"subject_id": "math", "grade_level": "secondary"}
        ),
    )
    response = client.request(
        "GET",
        _answer_path(),
        params={"courseId": "course-1", "classId": "class-1"},
        json={"courseId": "course-1", "classId": "class-1"},
        headers={"X-Course-ID": "course-1", "X-Class-ID": "class-1"},
    )
    assert response.status_code == 404
    assert ANSWER_CANARY not in response.text
    assert EXPLANATION_CANARY not in response.text


@pytest.mark.parametrize(
    "role,assignment",
    [
        ("student", None),
        ("parent", None),
        ("teacher", None),
        ("teacher", _assignment(status="revoked")),
        (
            "teacher",
            _assignment(
                curriculum_scope={"course_id": "course-2", "class_id": "class-1"}
            ),
        ),
    ],
)
def test_denied_roles_and_scopes_match_missing_resource_contract(
    monkeypatch,
    role: str,
    assignment: dict[str, Any] | None,
) -> None:
    client, _, _, _, _ = _client(
        monkeypatch,
        role=role,
        assignment=assignment,
    )
    denied = client.get(_answer_path())
    missing = client.get(_answer_path("random-challenge"))
    assert denied.status_code == missing.status_code == 404
    assert set(denied.json()) == set(missing.json()) == {"detail"}
    assert set(denied.json()["detail"]) == set(missing.json()["detail"])
    assert denied.json()["detail"]["code"] == "resource_not_found"
    assert missing.json()["detail"]["code"] == "resource_not_found"
    assert len(denied.content) == len(missing.content)
    for canary in (ANSWER_CANARY, EXPLANATION_CANARY, ASSIGNMENT_CANARY):
        assert canary not in denied.text
        assert canary not in missing.text


def test_missing_or_malformed_loaded_challenge_is_hidden_before_fact_load(monkeypatch) -> None:
    malformed = _challenge(challenge_id="challenge-1", course_id=None)
    client, _, facts, loads, _ = _client(
        monkeypatch,
        role="teacher",
        assignment=_assignment(),
        challenge=malformed,
    )
    response = client.get(_answer_path())
    assert response.status_code == 404
    assert ANSWER_CANARY not in response.text
    assert loads == ["challenge-1"]
    assert facts.loads == 0


def test_anonymous_request_never_loads_or_serializes_answer(monkeypatch) -> None:
    loads: list[str] = []
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenge",
        lambda challenge_id: loads.append(challenge_id) or _challenge(),
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    response = TestClient(app).get(_answer_path())
    assert response.status_code == 401
    assert loads == []
    assert ANSWER_CANARY not in response.text


def test_route_inventory_declares_only_narrow_answer_read_and_no_mutation() -> None:
    from stoa.main import app
    from stoa.security.route_inventory import inventory_application

    answer_operations = [
        item
        for item in inventory_application(app)
        if item.path == "/practice/curriculum/challenges/{challenge_id}/answer"
    ]
    assert len(answer_operations) == 1
    operation = answer_operations[0]
    assert operation.method == "GET"
    assert operation.authorization_spec is not None
    assert operation.authorization_spec.resource_type == "curriculum_answer"
    assert operation.authorization_spec.action == "read"
    assert operation.authorization_spec.purpose == "curriculum_answer_read"


def test_route_audit_is_redacted_and_uses_one_opaque_fingerprint(monkeypatch) -> None:
    client, _, _, _, audit = _client(
        monkeypatch,
        role="teacher",
        assignment=_assignment(),
    )
    response = client.get(_answer_path())
    assert response.status_code == 200
    assert len(audit.events) == 1
    event = next(iter(audit.events.values()))
    assert event["resource_type"] == "curriculum_answer"
    assert event["action"] == "read"
    assert event["purpose"] == "curriculum_answer_read"
    serialized = repr(event)
    for canary in (
        ANSWER_CANARY,
        EXPLANATION_CANARY,
        ASSIGNMENT_CANARY,
        "challenge-1",
        "course-1",
        "class-1",
    ):
        assert canary not in serialized
