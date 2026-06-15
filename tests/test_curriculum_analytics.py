from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import admin, practice
from stoa.services import adaptive_learning_service, curriculum_analytics_service


def _app_for_user(user: dict, *, include_admin: bool = False) -> FastAPI:
    app = FastAPI()
    router = admin.router if include_admin else practice.router
    prefix = "/admin" if include_admin else "/practice"
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _install_analytics_repo(monkeypatch, metrics=None):
    signals: list[dict] = []
    increments: list[dict] = []
    repo = curriculum_analytics_service.curriculum_analytics_repo
    monkeypatch.setattr(repo, "put_signal", lambda item: signals.append(dict(item)))
    monkeypatch.setattr(repo, "increment_metric", lambda item: increments.append(dict(item)))
    monkeypatch.setattr(repo, "list_metrics", lambda **kwargs: list(metrics or []))
    return {"signals": signals, "increments": increments}


def test_practice_answer_records_attempt_and_wrong_answer_signals(monkeypatch):
    state = _install_analytics_repo(monkeypatch)
    challenge = {
        "challenge_id": "exercise-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
        "prompt": "Solve x + 1 = 2",
        "correct_answer": "x = 1",
        "version_id": "version-1",
    }
    attempts = []
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda challenge_id: dict(challenge))
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda lesson_id: [dict(challenge)])
    monkeypatch.setattr(practice.practice_repo, "record_attempt", lambda *args, **kwargs: attempts.append((args, kwargs)))
    client = TestClient(_app_for_user({"sub": "student-1", "role": "student"}))

    response = client.post("/practice/challenges/exercise-1/answer", json={"answer": "x = 3"})

    assert response.status_code == 200
    assert [item["signal_type"] for item in state["signals"]] == ["practice_attempt", "wrong_answer"]
    assert state["signals"][0]["source_type"] == "catalog_self_practice"
    assert state["signals"][0]["metadata"] == {
        "correct": False,
        "studentHash": "student:600bf3b15689",
    }
    assert "x = 3" not in str(state["signals"])
    assert len(attempts) == 1


def test_lesson_completion_records_aggregate_signal(monkeypatch):
    state = _install_analytics_repo(monkeypatch)
    lesson = {
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
        "version_id": "version-1",
        "order": 1,
    }
    monkeypatch.setattr(practice.practice_repo, "get_lesson", lambda lesson_id: dict(lesson))
    monkeypatch.setattr(practice.practice_repo, "mark_lesson_completed", lambda *args, **kwargs: None)
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda topic_id=None: [dict(lesson)])
    monkeypatch.setattr(
        practice.practice_repo,
        "get_progress",
        lambda user_id: [{"lesson_id": "lesson-1", "status": "completed"}],
    )
    client = TestClient(_app_for_user({"sub": "student-1", "role": "student"}))

    response = client.post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 200
    assert state["signals"][0]["signal_type"] == "lesson_completed"
    assert state["signals"][0]["public_id"] == "lesson-1"
    assert state["signals"][0]["content_type"] == "lesson"


def test_adaptive_assignment_transitions_record_content_quality_signals(monkeypatch):
    state = _install_analytics_repo(monkeypatch)
    assignments = {
        "assignment-1": {
            "assignment_id": "assignment-1",
            "student_id": "student-1",
            "status": "assigned",
            "source_type": "curriculum_exercise",
            "source_id": "exercise-1",
            "subject": "math",
            "topic_ids": ["algebra"],
            "lesson_id": "lesson-1",
            "exercise_id": "exercise-1",
            "items": [],
            "version_id": "version-1",
        }
    }
    repo = adaptive_learning_service.adaptive_learning_repo
    monkeypatch.setattr(repo, "get_assignment", lambda assignment_id: dict(assignments[assignment_id]))

    def update_assignment(
        assignment_id,
        updates,
        *,
        expected_status=None,
        expected_pending_token=None,
        expected_pending_state=None,
    ):
        if expected_status is not None and assignments[assignment_id]["status"] != expected_status:
            return dict(assignments[assignment_id])
        current_pending = assignments[assignment_id].get("pending_sequencing_effect") or {}
        if expected_pending_token is not None and current_pending.get("transitionToken") != expected_pending_token:
            return dict(assignments[assignment_id])
        if expected_pending_state is not None and current_pending.get("state") != expected_pending_state:
            return dict(assignments[assignment_id])
        assignments[assignment_id].update(updates)
        return dict(assignments[assignment_id])

    monkeypatch.setattr(repo, "update_assignment", update_assignment)
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "record_attempt", lambda *args, **kwargs: None)
    monkeypatch.setattr(adaptive_learning_service.practice_repo, "get_lesson", lambda lesson_id: None)

    skipped = adaptive_learning_service.transition_assignment(
        assignment_id="assignment-1",
        action="skip",
        user={"sub": "student-1", "role": "student"},
    )
    assignments["assignment-1"]["status"] = "assigned"
    completed = adaptive_learning_service.transition_assignment(
        assignment_id="assignment-1",
        action="complete",
        user={"sub": "student-1", "role": "student"},
        correct=False,
        student_answer="raw answer must not be stored",
    )

    assert skipped["status"] == "skipped"
    assert completed["status"] == "completed"
    assert [item["signal_type"] for item in state["signals"]] == [
        "assignment_skipped",
        "assignment_skipped",
        "assignment_completed",
        "assignment_completed",
    ]
    assert "raw answer must not be stored" not in str(state["signals"])


def test_adaptive_assignment_start_and_archive_record_feedback_signals(monkeypatch):
    state = _install_analytics_repo(monkeypatch)
    assignments = {
        "assignment-1": {
            "assignment_id": "assignment-1",
            "student_id": "student-1",
            "status": "assigned",
            "source_type": "curriculum_exercise",
            "source_id": "exercise-1",
            "subject": "math",
            "topic_ids": ["algebra"],
            "lesson_id": "lesson-1",
            "exercise_id": "exercise-1",
            "items": [],
            "version_id": "version-1",
        }
    }
    repo = adaptive_learning_service.adaptive_learning_repo
    monkeypatch.setattr(repo, "get_assignment", lambda assignment_id: dict(assignments[assignment_id]))

    def update_assignment(
        assignment_id,
        updates,
        *,
        expected_status=None,
        expected_pending_token=None,
        expected_pending_state=None,
    ):
        if expected_status is not None and assignments[assignment_id]["status"] != expected_status:
            return dict(assignments[assignment_id])
        current_pending = assignments[assignment_id].get("pending_sequencing_effect") or {}
        if expected_pending_token is not None and current_pending.get("transitionToken") != expected_pending_token:
            return dict(assignments[assignment_id])
        if expected_pending_state is not None and current_pending.get("state") != expected_pending_state:
            return dict(assignments[assignment_id])
        assignments[assignment_id].update(updates)
        return dict(assignments[assignment_id])

    monkeypatch.setattr(repo, "update_assignment", update_assignment)

    started = adaptive_learning_service.transition_assignment(
        assignment_id="assignment-1",
        action="start",
        user={"sub": "student-1", "role": "student"},
    )
    archived = adaptive_learning_service.transition_assignment(
        assignment_id="assignment-1",
        action="archive",
        user={"sub": "tutor-1", "role": "tutor"},
    )

    assert started["status"] == "started"
    assert started["sequencingFeedback"]["event"] == "started"
    assert archived["status"] == "archived"
    assert archived["sequencingFeedback"]["rankingEffect"] == "archive_suppresses_exact_source"
    assert [item["signal_type"] for item in state["signals"]] == [
        "assignment_started",
        "assignment_started",
        "assignment_archived",
        "assignment_archived",
    ]
    assert state["signals"][0]["metadata"]["event"] == "started"
    assert state["signals"][0]["metadata"]["topicIds"] == ["algebra"]


def test_losing_conditional_transition_does_not_emit_side_effects(monkeypatch):
    state = _install_analytics_repo(monkeypatch)
    assignment = {
        "assignment_id": "assignment-1",
        "student_id": "student-1",
        "status": "assigned",
        "source_type": "curriculum_exercise",
        "source_id": "exercise-1",
        "subject": "math",
        "topic_ids": ["algebra"],
        "lesson_id": "lesson-1",
        "exercise_id": "exercise-1",
        "items": [],
        "version_id": "version-1",
    }
    repo = adaptive_learning_service.adaptive_learning_repo
    monkeypatch.setattr(repo, "get_assignment", lambda assignment_id: dict(assignment))
    monkeypatch.setattr(
        repo,
        "update_assignment",
        lambda assignment_id, updates, *, expected_status=None, expected_pending_token=None, expected_pending_state=None: {
            **assignment,
            "status": "started",
            "updated_at": updates["updated_at"],
            "transition_token": "transition-owned-by-other-request",
        },
    )

    response = adaptive_learning_service.transition_assignment(
        assignment_id="assignment-1",
        action="start",
        user={"sub": "student-1", "role": "student"},
    )

    assert response["status"] == "started"
    assert state["signals"] == []


def test_curriculum_quality_endpoint_returns_aggregate_privacy_boundary(monkeypatch):
    _install_analytics_repo(
        monkeypatch,
        metrics=[
            {
                "public_id": "exercise-1",
                "content_type": "exercise",
                "version_id": "version-1",
                "subject_id": "math",
                "topic_id": "algebra",
                "total_count": 5,
                "signal_wrong_answer_count": 2,
                "signal_assignment_started_count": 1,
                "signal_assignment_skipped_count": 1,
                "signal_assignment_archived_count": 1,
                "signal_assignment_completed_count": 1,
                "source_reviewed_assignment_count": 3,
                "updated_at": "2026-06-12T09:00:00+00:00",
            }
        ],
    )
    client = TestClient(_app_for_user({"sub": "tutor-1", "role": "tutor"}, include_admin=True))

    response = client.get("/admin/curriculum/analytics/content-quality?contentType=exercise")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["publicId"] == "exercise-1"
    assert body["items"][0]["assignmentStarts"] == 1
    assert body["items"][0]["assignmentArchives"] == 1
    assert body["items"][0]["priorityScore"] == 7
    assert body["privacy"] == {
        "aggregateOnly": True,
        "rawStudentAnswers": False,
        "answerKeys": False,
        "studentIdentifiers": False,
    }
    assert "correct_answer" not in str(body)
    assert "student-1" not in str(body)


def test_curriculum_warehouse_readiness_and_export_are_aggregate_only(monkeypatch):
    _install_analytics_repo(
        monkeypatch,
        metrics=[
            {
                "public_id": "exercise-1",
                "content_type": "exercise",
                "version_id": "version-1",
                "subject_id": "math",
                "topic_id": "algebra",
                "total_count": 6,
                "signal_wrong_answer_count": 2,
                "signal_assignment_started_count": 1,
                "signal_assignment_skipped_count": 1,
                "signal_assignment_archived_count": 0,
                "signal_assignment_completed_count": 2,
                "updated_at": "2026-06-12T09:00:00+00:00",
            }
        ],
    )
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, include_admin=True))

    readiness = client.get("/admin/curriculum/analytics/warehouse-readiness")
    export = client.get("/admin/curriculum/analytics/warehouse-export?contentType=exercise")

    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["state"] == "api-ready"
    assert readiness_body["liveWarehouseConfigured"] is False
    assert readiness_body["blockers"] == ["live_warehouse_not_configured"]
    assert readiness_body["privacy"]["rawStudentAnswers"] is False
    source_names = {source["name"] for source in readiness_body["sources"] if source["name"] != "warehouse"}
    assert source_names == set(readiness_body["sourceSchemas"])
    assert readiness_body["sourceSchemas"]["content_quality_metrics"]["rowState"] == "exported"
    assert readiness_body["sourceSchemas"]["learning_memory"]["rowState"] == "schema-only"

    assert export.status_code == 200
    export_body = export.json()
    assert export_body["schemaVersion"] == "stoa.curriculum_analytics.v1"
    assert export_body["sourceSchemas"]["assignment_outcomes"]["rowState"] == "schema-only"
    assert export_body["items"][0]["metricId"] == "exercise:exercise-1:version-1"
    assert export_body["items"][0]["metrics"]["assignmentStarts"] == 1
    assert export_body["items"][0]["metrics"]["assignmentCompletions"] == 2
    assert export_body["window"]["liveWarehouseRequired"] is False
    assert export_body["window"]["sampled"] is True
    assert "student-1" not in str(export_body)
    assert "correct_answer" not in str(export_body)


def test_curriculum_analytics_dashboard_summarizes_operator_actions(monkeypatch):
    _install_analytics_repo(
        monkeypatch,
        metrics=[
            {
                "public_id": "exercise-1",
                "content_type": "exercise",
                "version_id": "version-1",
                "subject_id": "math",
                "topic_id": "algebra",
                "total_count": 8,
                "signal_wrong_answer_count": 2,
                "signal_assignment_started_count": 2,
                "signal_assignment_skipped_count": 1,
                "signal_assignment_archived_count": 1,
                "signal_assignment_completed_count": 1,
                "signal_lesson_completed_count": 3,
                "updated_at": "2026-06-12T09:00:00+00:00",
            },
            {
                "public_id": "lesson-2",
                "content_type": "lesson",
                "version_id": "version-2",
                "subject_id": "math",
                "topic_id": "geometry",
                "total_count": 3,
                "signal_lesson_completed_count": 3,
                "updated_at": "2026-06-12T10:00:00+00:00",
            },
        ],
    )
    client = TestClient(_app_for_user({"sub": "tutor-1", "role": "tutor"}, include_admin=True))

    response = client.get("/admin/curriculum/analytics/dashboard?subjectId=math")

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 2
    assert body["sampled"] is True
    assert body["summary"]["assignmentStarts"] == 2
    assert body["summary"]["lessonCompletions"] == 6
    assert body["sequencingCoverage"]["assignmentCompletions"] == 1
    assert body["qualityHotspots"][0]["publicId"] == "exercise-1"
    assert body["interventions"][0]["reasons"] == ["wrong_answers", "assignment_skips", "assignment_archives"]
    assert body["emptyState"] is None


def test_curriculum_analytics_dashboard_empty_state(monkeypatch):
    _install_analytics_repo(monkeypatch, metrics=[])
    client = TestClient(_app_for_user({"sub": "teacher-1", "role": "teacher"}, include_admin=True))

    response = client.get("/admin/curriculum/analytics/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["sampleSize"] == 0
    assert body["emptyState"] == "No aggregate learning analytics have been recorded yet."
    assert body["summary"]["totalSignals"] == 0
