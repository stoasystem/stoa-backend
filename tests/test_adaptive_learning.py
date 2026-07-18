from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import adaptive
from stoa.security.authorization import (
    AuthorizationFacts,
    ParentAuthorizationFacts,
    TeacherAuthorizationFacts,
)
from stoa.security.identity import (
    AccountStatus,
    Actor,
    CanonicalRole,
    CapabilityGrant,
)
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import adaptive_learning_service
from audit_helpers import MemoryAuthorizationAuditSink


def _app(user: dict) -> TestClient:
    role = CanonicalRole(user["role"])
    grants = ()
    if role is CanonicalRole.ADMIN:
        capability_names = user.get("grantCapabilities") or (
            "learning_assignment_manager",
            "assignment_automation_preview",
            "assignment_automation_execute",
        )
        grants = tuple(
            CapabilityGrant(capability, "student:student-1", 1)
            for capability in capability_names
        )
    actor = Actor(
        str(user["sub"]),
        "https://identity.test",
        f"{user['sub']}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
        grants,
        tuple(
            (key, str(value))
            for key, value in user.items()
            if key in {"preferredLocale", "preferred_locale", "language"}
        ),
    )

    class _Facts:
        async def facts_for(self, current_actor, resource, action, purpose, _value):
            if user.get("factsOutage"):
                raise TimeoutError("authorization canary")
            account = {
                "user_id": resource.student_id,
                "role": "student",
                "account_status": "active",
            }
            if current_actor.role is CanonicalRole.PARENT:
                row = {
                    "parent_id": current_actor.user_id,
                    "student_id": resource.student_id,
                    "relationship": "child",
                    "status": "active",
                    "version": 1,
                }
                return AuthorizationFacts(
                    parent=ParentAuthorizationFacts(
                        row,
                        dict(row),
                        {
                            "user_id": current_actor.user_id,
                            "role": "parent",
                            "account_status": "active",
                        },
                        account,
                    )
                )
            if current_actor.role is CanonicalRole.TEACHER:
                assignment = None
                if user.get("assigned", True):
                    assignment = {
                        "teacher_id": current_actor.user_id,
                        "student_id": resource.student_id,
                        "status": "active",
                        "resource_types": [resource.resource_type.value],
                        "actions": [action.value],
                        "purposes": [purpose.value],
                    }
                return AuthorizationFacts(
                    teacher=TeacherAuthorizationFacts(
                        assignment=assignment,
                        teacher_account={
                            "user_id": current_actor.user_id,
                            "role": "teacher",
                            "account_status": "active",
                        },
                        student_account=account,
                    )
                )
            return AuthorizationFacts()

    app = FastAPI()
    app.include_router(adaptive.router, prefix="/adaptive")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = _Facts
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


@pytest.fixture(autouse=True)
def _canonical_student_profiles(monkeypatch):
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(adaptive_learning_service, "datetime", _FixedDateTime)

    def profile(user_id):
        role = "student"
        if str(user_id).startswith("parent"):
            role = "parent"
        elif str(user_id).startswith("teacher"):
            role = "teacher"
        elif str(user_id).startswith("admin"):
            role = "admin"
        return {
            "user_id": user_id,
            "role": role,
            "account_status": "active",
        }

    monkeypatch.setattr(adaptive.user_repo, "get_user", profile)
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_mistakes", lambda _id: [])
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_progress",
        lambda _id, _subject=None: [],
    )


def _install_memory_repo(monkeypatch):
    snapshots: list[dict] = []
    assignments: dict[str, dict] = {}

    def put_memory_snapshot(item):
        snapshots.append(dict(item))

    def list_memory_snapshots(student_id, subject=None):
        items = [item for item in snapshots if item["student_id"] == student_id]
        if subject:
            items = [item for item in items if item["subject"] == subject]
        return [dict(item) for item in items]

    def put_assignment(item):
        assignments[item["assignment_id"]] = dict(item)

    def put_assignment_if_absent(item):
        if item["assignment_id"] in assignments:
            return dict(assignments[item["assignment_id"]]), False
        assignments[item["assignment_id"]] = dict(item)
        return dict(item), True

    def get_assignment(assignment_id):
        item = assignments.get(assignment_id)
        return dict(item) if item else None

    def update_assignment(
        assignment_id,
        updates,
        *,
        expected_status=None,
        expected_pending_token=None,
        expected_pending_state=None,
    ):
        if assignment_id not in assignments:
            return None
        if expected_status is not None and assignments[assignment_id]["status"] != expected_status:
            return dict(assignments[assignment_id])
        current_pending = assignments[assignment_id].get("pending_sequencing_effect") or {}
        if expected_pending_token is not None and current_pending.get("transitionToken") != expected_pending_token:
            return dict(assignments[assignment_id])
        if expected_pending_state is not None and current_pending.get("state") != expected_pending_state:
            return dict(assignments[assignment_id])
        assignments[assignment_id].update(updates)
        return dict(assignments[assignment_id])

    def list_assignments(student_id, status=None, include_archived=False, limit=100):
        items = [item for item in assignments.values() if item["student_id"] == student_id]
        if status:
            items = [item for item in items if item["status"] == status]
        if not include_archived:
            items = [item for item in items if item["status"] != "archived"]
        if limit is None:
            return [dict(item) for item in items]
        return [dict(item) for item in items[:limit]]

    repo = adaptive_learning_service.adaptive_learning_repo
    monkeypatch.setattr(repo, "put_memory_snapshot", put_memory_snapshot)
    monkeypatch.setattr(repo, "list_memory_snapshots", list_memory_snapshots)
    monkeypatch.setattr(repo, "put_assignment", put_assignment)
    monkeypatch.setattr(repo, "put_assignment_if_absent", put_assignment_if_absent)
    monkeypatch.setattr(repo, "get_assignment", get_assignment)
    monkeypatch.setattr(repo, "update_assignment", update_assignment)
    monkeypatch.setattr(repo, "list_assignments", list_assignments)
    return snapshots, assignments


def _install_learning_sources(monkeypatch):
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {
            "Items": [
                {
                    "question_id": "question-1",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["Linear equations"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T10:00:00+00:00",
                }
            ]
        },
    )


def test_assignment_generation_and_transition_record_usage_ledger(monkeypatch):
    _snapshots, assignments = _install_memory_repo(monkeypatch)
    ledger_calls = []
    monkeypatch.setattr(
        adaptive_learning_service,
        "_assignment_source",
        lambda source_type, source_id, student_id, user: {
            "sourceType": source_type,
            "title": "Linear practice",
            "subject": "math",
            "topicIds": ["algebra"],
            "lessonId": "lesson-1",
            "exerciseId": source_id,
            "items": [{"prompt": "private prompt"}],
            "answerKey": [{"answer": "private answer"}],
            "rationale": "private rationale",
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
    )
    monkeypatch.setattr(
        adaptive_learning_service.curriculum_analytics_service,
        "record_assignment_started",
        lambda item: None,
    )

    created = adaptive_learning_service.create_assignment(
        student_id="student-1",
        source_type="curriculum_exercise",
        source_id="exercise-1",
        user={"sub": "teacher-1", "role": "teacher"},
        status="assigned",
    )
    assignment_id = created["assignmentId"]

    started = adaptive_learning_service.transition_assignment(
        assignment_id=assignment_id,
        action="start",
        user={"sub": "student-1", "role": "student"},
    )

    assert started["status"] == "started"
    assert ledger_calls[0]["action"] == "reviewed_assignment_generation"
    assert ledger_calls[0]["metadata"] == {"status": "assigned"}
    assert ledger_calls[1]["action"] == "assignment_started"
    assert ledger_calls[1]["metadata"]["status"] == "started"
    assert assignment_id in assignments
    assert "private prompt" not in str(ledger_calls)
    assert "private answer" not in str(ledger_calls)
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_mistakes",
        lambda student_id: [
            {
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "linear-equations",
                "lesson_id": "lesson-1",
                "created_at": "2026-06-09T11:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_progress",
        lambda student_id, subject_id=None: [
            {
                "lesson_id": "lesson-1",
                "subject_id": "math",
                "topic_id": "linear-equations",
                "status": "completed",
                "completed_at": "2026-06-09T12:00:00+00:00",
            }
        ],
    )


def test_teacher_refreshes_memory_and_parent_gets_safe_progress(monkeypatch):
    snapshots, assignments = _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    assignments["assignment-1"] = {
        "assignment_id": "assignment-1",
        "student_id": "student-1",
        "status": "assigned",
        "source_type": "ai_draft",
        "source_id": "draft-1",
        "title": "Practice linear equations",
        "subject": "math",
        "topic_ids": ["linear-equations"],
        "items": [{"prompt": "Solve x + 2 = 5"}],
        "answer_key": [{"answer": "3"}],
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }
    assignments["assignment-completed"] = {
        "assignment_id": "assignment-completed",
        "student_id": "student-1",
        "status": "completed",
        "source_type": "curriculum_exercise",
        "source_id": "challenge-1",
        "title": "Completed practice",
        "subject": "math",
        "topic_ids": ["linear-equations"],
        "items": [{"prompt": "Completed prompt"}],
        "answer_key": [{"answer": "hidden"}],
        "student_answer": "raw answer must stay private",
        "completion_result": {"correct": True, "attemptCount": 1},
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }

    teacher_response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/memory/refresh"
    )

    assert teacher_response.status_code == 200
    assert snapshots[0]["topic_id"] == "linear-equations"
    assert teacher_response.json()["memorySnapshots"][0]["recent_questions"] == ["question-1"]
    assert all(item["topicId"] != "linear-equations" for item in teacher_response.json()["recommendations"])
    assert teacher_response.json()["locale"]["effectiveLocale"] == "de"
    assert teacher_response.json()["locale"]["canonicalValuesStable"] is True

    parent_response = _app({"sub": "parent-1", "role": "parent"}).get(
        "/adaptive/parents/me/children/student-1/progress"
    )

    assert parent_response.status_code == 200
    parent_body = parent_response.json()
    assert parent_body["assignedPracticeCount"] == 1
    assert parent_body["completedPracticeCount"] == 1
    assert parent_body["freshness"]["status"] == "fresh"
    assert parent_body["locale"]["effectiveLocale"] == "de"
    assert "recent_questions" not in parent_body["weakAreas"][0]
    assert "evidenceQuestionIds" not in parent_body["weakAreas"][0]
    assert "raw answer must stay private" not in str(parent_body["completedAssignments"])
    assert "studentAnswer" not in parent_body["completedAssignments"][0]


def test_adaptive_sequencing_ranks_reviewed_drafts_and_exposes_safe_signals(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.curriculum_service,
        "list_exercises",
        lambda **kwargs: {
            "items": [
                {
                    "id": "challenge-1",
                    "prompt": "Solve a linear equation",
                    "subjectId": "math",
                    "topicId": "linear-equations",
                    "rolloutState": "active",
                }
            ],
            "count": 1,
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-1",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "teacher-1",
            }
        ],
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).get(
        "/adaptive/students/student-1/recommendations"
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["type"] == "reviewed_ai_draft"
    assert items[0]["candidateId"] == "reviewed_ai_draft:draft-1"
    assert items[0]["sourceType"] == "ai_draft"
    assert items[0]["confidence"] in {"medium", "high"}
    assert items[0]["reviewRequired"] is True
    assert items[0]["autonomousDecision"] is False
    assert items[0]["sourceSignals"]["reviewedDraftAvailable"] is True
    assert "question-1" not in str(items[0]["sourceSignals"])
    assert response.json()["sequencingSummary"]["topCandidateType"] == "reviewed_ai_draft"

    student_response = _app({"sub": "student-1", "role": "student"}).get(
        "/adaptive/students/me/memory"
    )

    assert student_response.status_code == 200
    assert all(item["type"] != "reviewed_ai_draft" for item in student_response.json()["recommendations"])


def test_adaptive_sequencing_suppresses_completed_exact_sources(monkeypatch):
    _, assignments = _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    assignments["assignment-completed"] = {
        "assignment_id": "assignment-completed",
        "student_id": "student-1",
        "status": "completed",
        "source_type": "curriculum_exercise",
        "source_id": "challenge-1",
        "title": "Completed linear equations",
        "subject": "math",
        "topic_ids": ["linear-equations"],
        "items": [],
        "answer_key": [],
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }
    monkeypatch.setattr(
        adaptive_learning_service.curriculum_service,
        "list_exercises",
        lambda **kwargs: {
            "items": [
                {
                    "id": "challenge-1",
                    "prompt": "Already completed",
                    "subjectId": "math",
                    "topicId": "linear-equations",
                    "rolloutState": "active",
                },
                {
                    "id": "challenge-2",
                    "prompt": "Fresh linear equation check",
                    "subjectId": "math",
                    "topicId": "linear-equations",
                    "rolloutState": "active",
                },
            ],
            "count": 2,
        },
    )
    monkeypatch.setattr(adaptive_learning_service.ai_teacher_tools_repo, "list_drafts", lambda **kwargs: [])

    response = _app({"sub": "teacher-1", "role": "teacher"}).get(
        "/adaptive/students/student-1/recommendations"
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item.get("sourceId") != "challenge-1" for item in items)
    assert any(item.get("sourceId") == "challenge-2" for item in items)


def test_assignment_automation_preview_selects_policy_bounded_candidates(monkeypatch):
    _, assignments = _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.curriculum_service,
        "list_exercises",
        lambda **kwargs: {
            "items": [
                {
                    "id": "challenge-1",
                    "prompt": "Solve a linear equation",
                    "subjectId": "math",
                    "topicId": "linear-equations",
                    "rolloutState": "active",
                }
            ],
            "count": 1,
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-1",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "teacher-1",
                "student_delivery_status": "not_delivered",
            }
        ],
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={
            "policy": {
                "policyId": "policy-1",
                "sourceTypes": ["ai_draft"],
                "maxAssignmentsPerStudent": 1,
                "confidenceThreshold": "medium",
                "deliveryMode": "recommended",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview"
    assert body["reviewRequired"] is True
    assert body["autonomousDecision"] is False
    assert body["summary"]["selectedCount"] == 1
    assert body["selected"][0]["sourceType"] == "ai_draft"
    assert body["selected"][0]["sourceId"] == "draft-1"
    assert body["selected"][0]["proposedStatus"] == "recommended"
    assert body["selected"][0]["reviewStatus"] == "reviewed_source"
    assert body["summary"]["refusalCounts"]["source_type_not_allowed"] >= 1
    assert all(item["refusalCode"] == "source_type_not_allowed" for item in body["refused"])
    assert assignments == {}


def test_assignment_automation_preview_refuses_paused_policy(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(adaptive_learning_service.ai_teacher_tools_repo, "list_drafts", lambda **kwargs: [])

    response = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={
            "policy": {
                "policyId": "policy-paused",
                "status": "paused",
                "pausedReason": "Teacher paused automation during exams.",
                "sourceTypes": ["memory_snapshot"],
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected"] == []
    assert body["summary"]["selectedCount"] == 0
    assert body["summary"]["refusalCounts"]["policy_paused"] >= 1
    assert body["refused"][0]["refusalReason"] == "Teacher paused automation during exams."


def test_assignment_automation_preview_refuses_out_of_scope_student(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(adaptive_learning_service.ai_teacher_tools_repo, "list_drafts", lambda **kwargs: [])

    response = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={
            "policy": {
                "policyId": "policy-student-2",
                "studentIds": ["student-2"],
                "sourceTypes": ["memory_snapshot"],
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected"] == []
    assert body["summary"]["refusalCounts"]["student_out_of_scope"] >= 1
    assert all(item["refusalCode"] == "student_out_of_scope" for item in body["refused"])


def test_assignment_automation_preview_rejects_unsupported_policy_values(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)

    bad_source = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"sourceTypes": ["typo_source"]}},
    )
    bad_blank_source = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"sourceTypes": [""]}},
    )
    bad_delivery = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"deliveryMode": "delivered"}},
    )

    assert bad_source.status_code == 400
    assert bad_source.json()["detail"] == "Unsupported automation source type: typo_source"
    assert bad_blank_source.status_code == 400
    assert bad_blank_source.json()["detail"] == "Blank policy values are not supported"
    assert bad_delivery.status_code == 400
    assert bad_delivery.json()["detail"] == "Unsupported value: delivered"


def test_assignment_automation_execute_creates_assignments_idempotently(monkeypatch):
    _, assignments = _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-1",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "teacher-1",
            }
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["linear-equations"],
            "created_by": "teacher-1",
            "items": [{"prompt": "Simplify 2/4"}],
            "answer_key": [{"answer": "1/2"}],
        },
    )
    policy = {
        "policyId": "policy-automation-1",
        "autonomyLevel": "teacher_approved_batch",
        "sourceTypes": ["ai_draft"],
        "deliveryMode": "assigned",
    }
    preview = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": policy},
    )
    assert preview.status_code == 200
    payload = {
        "batchId": preview.json()["batchId"],
        "approved": True,
        "policy": policy,
        "candidates": preview.json()["selected"],
    }

    first = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json=payload,
    )
    second = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json=payload,
    )

    assert first.status_code == 200
    body = first.json()
    assignment = body["results"][0]["assignment"]
    assert body["summary"]["assignedCount"] == 1
    assert body["results"][0]["status"] == "assigned"
    assert assignment["status"] == "assigned"
    assert assignment["automation"]["policyId"] == "policy-automation-1"
    assert assignment["automation"]["batchId"] == preview.json()["batchId"]
    assert assignment["automation"]["deliveryState"] == "assigned"
    assert assignment["automation"]["sourceSignals"]["reviewedDraftAvailable"] is True
    assert assignment["answerKey"] == [{"answer": "1/2"}]
    assert len(assignments) == 1

    assert second.status_code == 200
    assert second.json()["summary"]["duplicateCount"] == 1
    assert second.json()["results"][0]["status"] == "duplicate"
    assert second.json()["results"][0]["assignmentId"] == assignment["assignmentId"]
    assert len(assignments) == 1

    student_assignment = _app({"sub": "student-1", "role": "student"}).get(
        f"/adaptive/assignments/{assignment['assignmentId']}"
    )
    assert student_assignment.status_code == 200
    student_body = student_assignment.json()
    assert "answerKey" not in student_body
    assert "sourceSignals" not in student_body["automation"]
    assert student_body["automation"]["explanation"] == (
        "Teacher-approved practice was assigned for linear-equations based on recent learning signals."
    )


def test_assignment_automation_execute_returns_partial_batch_results(monkeypatch):
    _, assignments = _install_memory_repo(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {
            "Items": [
                {
                    "question_id": "question-linear",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["Linear equations"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T10:00:00+00:00",
                },
                {
                    "question_id": "question-fractions",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["Fractions"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T11:00:00+00:00",
                },
            ]
        },
    )
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_mistakes", lambda student_id: [])
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_progress", lambda student_id, subject_id=None: [])
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-2",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "admin-1",
            }
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["linear-equations"],
            "created_by": "admin-1",
            "items": [{"prompt": "Solve x + 2 = 5"}],
            "answer_key": [{"answer": "3"}],
        },
    )
    policy = {
        "policyId": "policy-partial-1",
        "autonomyLevel": "teacher_approved_batch",
        "sourceTypes": ["ai_draft", "memory_snapshot"],
        "deliveryMode": "recommended",
        "maxAssignmentsPerStudent": 3,
    }
    preview = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": policy},
    )
    assert preview.status_code == 200
    selected = preview.json()["selected"]
    assert {item["sourceType"] for item in selected} == {"ai_draft", "memory_snapshot"}

    response = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": preview.json()["batchId"],
            "approved": True,
            "policy": policy,
            "candidates": selected,
        },
    )
    retry = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": preview.json()["batchId"],
            "approved": True,
            "policy": policy,
            "candidates": selected,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["deliveredCount"] == 1
    assert body["summary"]["refusedCount"] == 1
    assert body["summary"]["duplicateCount"] == 0
    result_by_id = {item["candidateId"]: item for item in body["results"]}
    memory_candidate_id = next(item["candidateId"] for item in selected if item["sourceType"] == "memory_snapshot")
    assert result_by_id["reviewed_ai_draft:draft-2"]["status"] == "delivered"
    assert result_by_id[memory_candidate_id]["status"] == "refused"
    assert result_by_id[memory_candidate_id]["refusalCode"] == "unsupported_assignment_source"
    assert retry.status_code == 200
    retry_by_id = {item["candidateId"]: item for item in retry.json()["results"]}
    assert retry_by_id["reviewed_ai_draft:draft-2"]["status"] == "duplicate"
    assert retry_by_id[memory_candidate_id]["status"] == "refused"
    assert len(assignments) == 1


def test_assignment_automation_execute_rejects_stale_or_forged_candidates(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-1",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed linear equation practice",
                "created_by": "teacher-1",
            }
        ],
    )
    policy = {
        "policyId": "policy-forged-1",
        "autonomyLevel": "teacher_approved_batch",
        "sourceTypes": ["ai_draft"],
        "deliveryMode": "recommended",
    }
    preview = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": policy},
    )
    assert preview.status_code == 200
    forged = dict(preview.json()["selected"][0])
    forged["sourceId"] = "draft-forged"

    stale = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": "batch-not-current",
            "approved": True,
            "policy": policy,
            "candidates": preview.json()["selected"],
        },
    )
    forged_response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": preview.json()["batchId"],
            "approved": True,
            "policy": policy,
            "candidates": [forged],
        },
    )

    assert stale.status_code == 409
    assert stale.json()["detail"] == "Automation batch preview is stale"
    assert forged_response.status_code == 409
    assert forged_response.json()["detail"] == "Candidate does not match current preview"


def test_assignment_automation_execute_preserves_subject_scope_and_parent_visibility(monkeypatch):
    _, assignments = _install_memory_repo(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500: {
            "Items": [
                {
                    "question_id": "question-math",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["Linear equations"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T10:00:00+00:00",
                },
                {
                    "question_id": "question-german",
                    "student_id": student_id,
                    "status": "ai_answered",
                    "subject": "german",
                    "knowledge_points": ["Grammar"],
                    "student_feedback": 2,
                    "created_at": "2026-06-09T11:00:00+00:00",
                },
            ]
        },
    )
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_mistakes", lambda student_id: [])
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_progress", lambda student_id, subject_id=None: [])
    monkeypatch.setattr(adaptive_learning_service.curriculum_service, "list_exercises", lambda **kwargs: {"items": [], "count": 0})
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "list_drafts",
        lambda **kwargs: [
            {
                "draft_id": "draft-math",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "math",
                "topic_ids": ["linear-equations"],
                "title": "Reviewed math practice",
                "created_by": "teacher-1",
            },
            {
                "draft_id": "draft-german",
                "draft_type": "practice_exercise",
                "status": "accepted",
                "student_id": "student-1",
                "subject": "german",
                "topic_ids": ["grammar"],
                "title": "Reviewed German practice",
                "created_by": "teacher-1",
            },
        ],
    )
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["linear-equations"],
            "created_by": "teacher-1",
            "items": [{"prompt": "Solve x + 2 = 5"}],
            "answer_key": [{"answer": "3"}],
        },
    )
    policy = {
        "policyId": "policy-subject-1",
        "autonomyLevel": "teacher_approved_batch",
        "sourceTypes": ["ai_draft"],
        "deliveryMode": "assigned",
    }
    preview = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": policy, "subject": "math"},
    )
    assert preview.status_code == 200
    assert [item["subject"] for item in preview.json()["selected"]] == ["math"]

    execute = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": preview.json()["batchId"],
            "approved": True,
            "policy": policy,
            "subject": "math",
            "candidates": preview.json()["selected"],
        },
    )

    assert execute.status_code == 200
    assignment = execute.json()["results"][0]["assignment"]
    assert assignment["subject"] == "math"
    assert len(assignments) == 1

    parent_progress = _app({"sub": "parent-1", "role": "parent"}).get(
        "/adaptive/parents/me/children/student-1/progress"
    )
    assert parent_progress.status_code == 200
    parent_assignment = parent_progress.json()["assignments"][0]
    assert parent_assignment["automation"]["policyId"] == "policy-subject-1"
    assert "answerKey" not in parent_assignment
    assert "sourceSignals" not in parent_assignment["automation"]


def test_reviewed_ai_draft_assignment_uses_current_student_scope_not_creator_role(monkeypatch):
    _install_memory_repo(monkeypatch)
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["fractions"],
            "created_by": "other-teacher",
            "items": [{"prompt": "Simplify 2/4"}],
            "answer_key": [{"answer": "1/2"}],
        },
    )

    response = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "ai_draft",
            "sourceId": "draft-private",
            "status": "assigned",
        },
    )

    assert response.status_code == 200
    assert response.json()["studentId"] == "student-1"


def test_reviewed_ai_draft_assignment_lifecycle_is_student_owned_and_idempotent(monkeypatch):
    _install_memory_repo(monkeypatch)
    attempts: list[dict] = []
    monkeypatch.setattr(
        adaptive_learning_service.ai_teacher_tools_repo,
        "get_draft",
        lambda draft_id: {
            "draft_id": draft_id,
            "draft_type": "practice_exercise",
            "status": "accepted",
            "student_id": "student-1",
            "subject": "math",
            "topic_ids": ["fractions"],
            "created_by": "teacher-1",
            "items": [{"prompt": "Simplify 2/4"}],
            "answer_key": [{"answer": "1/2"}],
        },
    )
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "record_attempt", lambda *args, **kwargs: attempts.append(kwargs))

    created = _app({"sub": "teacher-1", "role": "teacher"}).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "ai_draft",
            "sourceId": "draft-1",
            "status": "assigned",
        },
    )

    assert created.status_code == 200
    assignment_id = created.json()["assignmentId"]
    assert created.json()["answerKey"] == [{"answer": "1/2"}]
    assert created.json()["locale"]["effectiveLocale"] == "de"

    student_client = _app({"sub": "student-1", "role": "student"})
    started = student_client.post(f"/adaptive/assignments/{assignment_id}/start")
    completed = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "2/4", "correct": False},
    )
    repeated = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "conflicting retry answer", "correct": True},
    )

    assert started.status_code == 200
    assert started.json()["sequencingFeedback"]["event"] == "started"
    assert started.json()["sequencingFeedback"]["rankingEffect"] == "active_assignment_suppresses_duplicates"
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completionResult"] == {"correct": False, "attemptCount": 1}
    assert completed.json()["sequencingFeedback"]["event"] == "completed"
    assert completed.json()["sequencingFeedback"]["remediationTopicIds"] == ["fractions"]
    assert completed.json()["sequencingFeedback"]["rankingEffect"] == "completion_adds_remediation_pressure"
    assert "answerKey" not in completed.json()
    assert repeated.status_code == 200
    assert repeated.json()["completionResult"] == {"correct": False, "attemptCount": 1}
    assert repeated.json()["studentAnswer"] == "2/4"
    assert repeated.json()["sequencingFeedback"] == completed.json()["sequencingFeedback"]
    assert attempts == []

    forbidden = _app({"sub": "student-2", "role": "student"}).post(
        f"/adaptive/assignments/{assignment_id}/skip"
    )
    assert forbidden.status_code == 404


def test_adaptive_locale_metadata_does_not_change_canonical_values(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    german = _app({"sub": "student-1", "role": "student", "preferredLocale": "de"}).get(
        "/adaptive/students/me/memory"
    )
    english = _app({"sub": "student-1", "role": "student", "preferredLocale": "en"}).get(
        "/adaptive/students/me/memory"
    )

    assert german.status_code == 200
    assert english.status_code == 200
    german_body = german.json()
    english_body = english.json()
    assert german_body["locale"]["effectiveLocale"] == "de"
    assert english_body["locale"]["effectiveLocale"] == "en"
    assert german_body["studentId"] == english_body["studentId"] == "student-1"
    assert german_body["roleView"] == english_body["roleView"] == "student"
    assert german_body["recommendations"][0]["type"] == english_body["recommendations"][0]["type"]
    assert german_body["recommendations"][0]["topicId"] == english_body["recommendations"][0]["topicId"]
    assert german_body["freshness"]["status"] == english_body["freshness"]["status"]


def test_curriculum_assignment_completion_updates_progress_once(monkeypatch):
    _install_memory_repo(monkeypatch)
    completed_lessons: list[str] = []
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_challenge",
        lambda challenge_id: {
            "challenge_id": challenge_id,
            "lesson_id": "lesson-1",
            "subject_id": "math",
            "topic_id": "algebra",
            "prompt": "Solve x + 1 = 2",
            "correct_answer": "1",
        },
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "get_lesson",
        lambda lesson_id: {"lesson_id": lesson_id, "subject_id": "math", "topic_id": "algebra"},
    )
    monkeypatch.setattr(
        adaptive_learning_service.practice_repo,
        "mark_lesson_completed",
        lambda student_id, lesson: completed_lessons.append(lesson["lesson_id"]),
    )

    created = _app({"sub": "admin-1", "role": "admin"}).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "curriculum_exercise",
            "sourceId": "challenge-1",
            "title": "Linear equation check",
        },
    )

    assert created.status_code == 200
    assignment_id = created.json()["assignmentId"]
    assert created.json()["locale"]["effectiveLocale"] == "de"
    student_client = _app({"sub": "student-1", "role": "student"})
    first = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "1", "correct": True},
    )
    second = student_client.post(
        f"/adaptive/assignments/{assignment_id}/complete",
        json={"studentAnswer": "conflicting retry", "correct": False},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["sequencingFeedback"]["sourceType"] == "curriculum_exercise"
    assert first.json()["sequencingFeedback"]["topicIds"] == ["algebra"]
    assert second.json()["studentAnswer"] == "1"
    assert second.json()["completionResult"] == {"correct": True, "attemptCount": 1}
    assert second.json()["sequencingFeedback"] == first.json()["sequencingFeedback"]
    assert completed_lessons == ["lesson-1"]


def test_adaptive_unassigned_teacher_is_hidden_before_service_reads(monkeypatch):
    service_reads = []
    monkeypatch.setattr(
        adaptive_learning_service.question_repo,
        "list_by_student",
        lambda *_args, **_kwargs: service_reads.append("read") or {"Items": []},
    )

    response = _app(
        {"sub": "teacher-1", "role": "teacher", "assigned": False}
    ).get("/adaptive/students/student-1/memory")

    assert response.status_code == 404
    assert service_reads == []


def test_adaptive_automation_preview_capability_cannot_execute(monkeypatch):
    _install_memory_repo(monkeypatch)
    _install_learning_sources(monkeypatch)
    client = _app(
        {
            "sub": "admin-1",
            "role": "admin",
            "grantCapabilities": ["assignment_automation_preview"],
        }
    )
    preview = client.post(
        "/adaptive/students/student-1/assignment-automation/batches/preview",
        json={"policy": {"policyId": "policy-scoped"}},
    )
    execute = client.post(
        "/adaptive/students/student-1/assignment-automation/batches/execute",
        json={
            "batchId": "batch-1",
            "approved": True,
            "policy": {"policyId": "policy-scoped"},
            "candidates": [],
        },
    )

    assert preview.status_code == 200
    assert execute.status_code == 403


def test_adaptive_authorization_outage_prevents_assignment_mutation(monkeypatch):
    _install_memory_repo(monkeypatch)
    writes = []
    monkeypatch.setattr(
        adaptive_learning_service.adaptive_learning_repo,
        "put_assignment",
        lambda item: writes.append(item),
    )

    response = _app(
        {"sub": "teacher-1", "role": "teacher", "factsOutage": True}
    ).post(
        "/adaptive/assignments",
        json={
            "studentId": "student-1",
            "sourceType": "curriculum_exercise",
            "sourceId": "challenge-1",
        },
    )

    assert response.status_code == 503
    assert writes == []
