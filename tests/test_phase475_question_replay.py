"""Route-level proof for durable question admission and replay."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import Settings, get_settings
from stoa.db.repositories import question_submission_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import questions
from stoa.security.identity import AccountStatus, Actor, CanonicalRole


def _actor() -> Actor:
    return Actor(
        "student-1",
        "https://identity.test",
        "student-1-subject",
        CanonicalRole.STUDENT,
        AccountStatus.ACTIVE,
        CanonicalRole.STUDENT.value,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = lambda: Settings(
        free_tier_daily_question_limit=2,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
    )
    app.dependency_overrides[get_actor] = _actor
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _profile_and_entitlement(monkeypatch) -> None:
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda _student_id: {
            "user_id": "student-1",
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda *_args, **_kwargs: {
            "effectivePlan": "free",
            "source": "local",
            "limits": {"dailyAiQuestionLimit": 2},
            "blockingReason": None,
        },
    )


def _question_command(kwargs: dict[str, object]) -> dict[str, object]:
    return {
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v1",
        "status": "processing",
        "student_id": kwargs["student_id"],
        "idempotency_key": kwargs["idempotency_key"],
        "fingerprint": kwargs["fingerprint"],
        "question_id": kwargs["question"]["question_id"],  # type: ignore[index]
    }


def test_lost_response_retry_returns_original_without_repeating_effects(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    state: dict[str, object] = {"command": None, "question": None}
    effects: list[str] = []

    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: state["command"],
    )

    def admit(**kwargs):
        effects.append("admit")
        command = _question_command(kwargs)
        raw_question = kwargs["question"]
        assert isinstance(raw_question, Mapping)
        question = dict(raw_question)
        state.update(command=command, question=question)
        return question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            command=command,
            question=question,
        )

    monkeypatch.setattr(
        questions.question_submission_repo, "admit_question_submission", admit
    )
    def get_question(_question_id):
        value = state["question"]
        assert value is None or isinstance(value, Mapping)
        return dict(value) if value is not None else None

    monkeypatch.setattr(questions.question_repo, "get_question", get_question)

    def update_status(_question_id, status, **attrs):
        effects.append("question_update")
        assert isinstance(state["question"], dict)
        state["question"].update(status=status, **attrs)

    monkeypatch.setattr(questions.question_repo, "update_status", update_status)
    def answer(**_kwargs):
        effects.append("ai")
        return {
            "answer": "AI answer",
            "steps": [],
            "hints": [],
            "similar_exercises": [],
            "knowledge_points": [],
        }

    monkeypatch.setattr(questions.ai_service, "get_ai_answer", answer)

    request = {
        "content": "Please solve 2x + 4 = 10",
        "subject": "math",
        "idempotencyKey": "question-submit-replay",
    }
    first = _client().post("/questions", json=request)
    second = _client().post("/questions", json=request)

    assert first.status_code == second.status_code == 201
    assert first.json()["question_id"] == second.json()["question_id"]
    assert effects.count("admit") == 1
    assert effects.count("ai") == 1


def test_changed_payload_returns_structured_new_submission_action(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    effects: list[str] = []
    original_fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve 2x + 4 = 10",
        corrected_content=None,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: {
            "question_id": "question-original",
            "fingerprint": original_fingerprint,
            "status": "processing",
        },
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **_kwargs: effects.append("admit"),
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **_kwargs: effects.append("ai"),
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve a changed equation",
            "subject": "math",
            "idempotencyKey": "question-submit-replay",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "question_submission_payload_mismatch",
        "message": "This submission key belongs to different content. Submit the edit as a new question.",
        "action": "create_new_submission",
    }
    assert effects == []


def test_quota_and_retryable_admission_are_structured_and_effect_free(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: None,
    )
    effects: list[str] = []
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **_kwargs: effects.append("ai"),
    )

    for disposition, status_code, code in (
        (
            question_submission_repo.QuestionAdmissionDisposition.QUOTA_EXCEEDED,
            429,
            "question_quota_exceeded",
        ),
        (
            question_submission_repo.QuestionAdmissionDisposition.RETRYABLE,
            503,
            "question_submission_temporarily_unavailable",
        ),
    ):
        monkeypatch.setattr(
            questions.question_submission_repo,
            "admit_question_submission",
            lambda disposition=disposition, **_kwargs: question_submission_repo.QuestionAdmissionResult(
                disposition
            ),
        )
        response = _client().post(
            "/questions",
            json={
                "content": "Please solve 2x + 4 = 10",
                "subject": "math",
                "idempotencyKey": f"question-submit-{code}",
            },
        )
        assert response.status_code == status_code
        assert response.json()["detail"]["code"] == code
    assert effects == []


def test_command_read_failure_stops_before_attachment_reservation(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    effects: list[str] = []
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("private-store")),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *_args, **_kwargs: effects.append("reserve"),
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this image",
            "subject": "math",
            "idempotencyKey": "question-submit-store-outage",
            "attachment": {"uploadId": "upload-1"},
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "question_submission_temporarily_unavailable"
    )
    assert effects == []


def test_ai_failure_returns_queryable_durable_pending_question(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    persisted: dict[str, object] = {}
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: None,
    )

    def admit(**kwargs):
        persisted.update(kwargs["question"])
        return question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            command=_question_command(kwargs),
            question=dict(persisted),
        )

    monkeypatch.setattr(
        questions.question_submission_repo, "admit_question_submission", admit
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("private-provider-canary")),
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-pending",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert persisted["status"] == "pending"
    assert persisted["question_id"] == response.json()["question_id"]
