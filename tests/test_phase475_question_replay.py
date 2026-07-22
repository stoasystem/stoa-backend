"""Route-level proof for durable question admission and replay."""

from __future__ import annotations

import inspect
import json
import re

import pytest

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
    digest = str(kwargs["idempotency_digest"])
    return {
        "PK": f"USER#{kwargs['student_id']}",
        "SK": f"QUESTION_SUBMISSION#{digest}",
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "status": "processing",
        "student_id": kwargs["student_id"],
        "idempotency_digest": digest,
        "command_id": digest,
        "fingerprint": kwargs["fingerprint"],
        "question_id": kwargs["question"]["question_id"],  # type: ignore[index]
        "account_fence_generation": 1,
        "version": 1,
    }


class _ReplayTable:
    def __init__(self, *items: dict[str, object]) -> None:
        self.items = {(str(item["PK"]), str(item["SK"])): dict(item) for item in items}
        self.reads: list[tuple[str, str, bool]] = []

    def get_item(self, *, Key: dict[str, object], ConsistentRead: bool) -> dict[str, object]:
        key = (str(Key["PK"]), str(Key["SK"]))
        self.reads.append((*key, ConsistentRead))
        item = self.items.get(key)
        return {} if item is None else {"Item": dict(item)}


def _strict_replay_rows(
    *,
    command_status: str = "processing",
    question_status: str = "pending",
) -> tuple[str, str, str, dict[str, object], dict[str, object], dict[str, object]]:
    student_id = "student-1"
    caller_key = "question-submit-strict-replay"
    digest = question_submission_repo.question_submission_command_digest(
        student_id, caller_key
    )
    fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve 2x + 4 = 10",
        corrected_content=None,
    )
    command = {
        "PK": f"USER#{student_id}",
        "SK": f"QUESTION_SUBMISSION#{digest}",
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "student_id": student_id,
        "idempotency_digest": digest,
        "command_id": digest,
        "fingerprint": fingerprint,
        "question_id": "question-original",
        "account_fence_generation": 7,
        "status": command_status,
        "version": 3,
    }
    fence = {
        "PK": f"USER#{student_id}",
        "SK": "ACCOUNT_FENCE",
        "entity_type": "account_fence",
        "schema_version": "account-fence.v1",
        "user_id": student_id,
        "status": "active",
        "generation": 7,
        "version": 2,
    }
    question = {
        "PK": "QUESTION#question-original",
        "SK": "META",
        "entity_type": "question",
        "schema_version": "question.v1",
        "question_id": "question-original",
        "student_id": student_id,
        "account_fence_generation": 7,
        "version": 4,
        "subject": "math",
        "content": "private-original-question",
        "status": question_status,
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "topic_seeds": [],
        "student_feedback": None,
        "created_at": "2026-07-22T00:00:00+00:00",
        "resolved_at": None,
    }
    return student_id, digest, fingerprint, command, fence, question


@pytest.mark.parametrize(
    ("request_patch", "private_canary"),
    (
        pytest.param({}, "private-content-canary", id="missing"),
        pytest.param({"idempotencyKey": None}, "private-content-canary", id="null"),
        pytest.param({"idempotencyKey": "        "}, "        ", id="blank"),
        pytest.param({"idempotencyKey": "short"}, "short", id="too-short"),
        pytest.param({"idempotencyKey": "k" * 201}, "k" * 201, id="too-long"),
        pytest.param(
            {"idempotencyKey": "question-submit-valid", "unexpected": "private-extra-canary"},
            "private-extra-canary",
            id="unexpected-field",
        ),
    ),
)
def test_invalid_idempotency_input_is_redacted_and_effect_free(
    monkeypatch,
    request_patch: dict[str, object],
    private_canary: str,
) -> None:
    effects: list[str] = []

    def observed(name: str, value):
        effects.append(name)
        return value

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda *_args, **_kwargs: observed("profile", {}),
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda *_args, **_kwargs: observed(
            "entitlement",
            {"effectivePlan": "free", "limits": {"dailyAiQuestionLimit": 2}},
        ),
    )
    monkeypatch.setattr(
        questions.uuid,
        "uuid4",
        lambda: observed("uuid", "generated-question-id"),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: observed("command_read", None),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **_kwargs: observed(
            "admission",
            question_submission_repo.QuestionAdmissionResult(
                question_submission_repo.QuestionAdmissionDisposition.RETRYABLE
            ),
        ),
    )
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "build_question_usage_event",
        lambda **_kwargs: observed("ledger", {}),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "update_status",
        lambda *_args, **_kwargs: observed("question", None),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *_args, **_kwargs: observed("attachment", {"attachment": {}}),
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda *_args, **_kwargs: observed("ocr", ""),
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **_kwargs: observed("ai", {}),
    )

    request = {
        "content": "private-content-canary",
        "subject": "math",
        **request_patch,
    }
    response = _client().post("/questions", json=request)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "question_submission_identity_invalid",
        "message": "Provide a valid question submission key and try again.",
        "correlationId": response.json()["detail"]["correlationId"],
    }
    assert re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        response.json()["detail"]["correlationId"],
    )
    assert private_canary not in json.dumps(response.json())
    assert effects == []


def test_valid_idempotency_key_reaches_replay_boundary_as_opaque_digest(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    caller_key = "  student.private@example.test / solve this exactly  "
    expected_digest = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    observed_keys: list[str] = []

    def command_read(_student_id: str, idempotency_key: str):
        observed_keys.append(idempotency_key)
        return {
            "entity_type": "question_submission_command",
            "schema_version": "question-submission-command.v2",
            "student_id": "student-1",
            "idempotency_digest": expected_digest,
            "command_id": expected_digest,
            "question_id": "question-original",
            "fingerprint": question_submission_repo.question_submission_fingerprint(
                subject="math",
                original_content="Please solve 2x + 4 = 10",
                corrected_content=None,
            ),
            "status": "processing",
        }

    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        command_read,
    )
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda _question_id: {
            "question_id": "question-original",
            "student_id": "student-1",
            "subject": "math",
            "content": "Please solve 2x + 4 = 10",
            "status": "pending",
            "ai_response": None,
            "teacher_id": None,
            "teacher_response": None,
            "knowledge_points": [],
            "student_feedback": None,
            "created_at": "2026-07-22T00:00:00+00:00",
            "resolved_at": None,
        },
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": caller_key,
        },
    )

    assert response.status_code == 201
    assert observed_keys == [expected_digest]
    assert caller_key not in json.dumps(response.json(), sort_keys=True)


def test_raw_caller_key_is_absent_from_route_body_and_diagnostics(
    monkeypatch, caplog
) -> None:
    _profile_and_entitlement(monkeypatch)
    caller_key = "student.private@example.test / this is not a storage coordinate"
    expected_digest = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    captured: dict[str, object] = {}
    diagnostics: list[object] = []

    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: None,
    )

    def admit(**kwargs):
        captured.update(kwargs)
        command = _question_command(kwargs)
        question = dict(kwargs["question"])
        return question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            command=command,
            question=question,
        )

    monkeypatch.setattr(
        questions.question_submission_repo, "admit_question_submission", admit
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **_kwargs: (_ for _ in ()).throw(TimeoutError("provider unavailable")),
    )
    monkeypatch.setattr(
        questions,
        "emit_private_event",
        lambda *args, **kwargs: diagnostics.append((args, kwargs)),
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": caller_key,
        },
    )

    encoded = json.dumps(
        {
            "captured": captured,
            "response": response.json(),
            "diagnostics": diagnostics,
            "logs": caplog.text,
        },
        sort_keys=True,
        default=str,
    )
    assert response.status_code == 201
    assert captured["idempotency_digest"] == expected_digest
    assert caller_key not in encoded
    source = inspect.getsource(questions.submit_question)
    assert source.count("body.idempotency_key") == 1


def test_changed_payload_returns_structured_new_submission_action(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    effects: list[str] = []
    original_fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve 2x + 4 = 10",
        corrected_content=None,
    )
    digest = question_submission_repo.question_submission_command_digest(
        "student-1", "question-submit-replay"
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: {
            "entity_type": "question_submission_command",
            "schema_version": "question-submission-command.v2",
            "student_id": "student-1",
            "idempotency_digest": digest,
            "command_id": digest,
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


@pytest.mark.parametrize(
    ("target", "field", "value"),
    (
        pytest.param("command", "PK", "USER#student-2", id="wrong-command-owner-key"),
        pytest.param("command", "schema_version", "question-submission-command.v1", id="legacy-command-schema"),
        pytest.param("command", "status", "unknown", id="invalid-command-status"),
        pytest.param("command", "version", 0, id="invalid-command-version"),
        pytest.param("command", "account_fence_generation", 8, id="stale-command-generation"),
        pytest.param("question", "student_id", "student-2", id="foreign-question-owner"),
        pytest.param("question", "question_id", "question-foreign", id="wrong-question-identity"),
        pytest.param("question", "account_fence_generation", 8, id="wrong-question-generation"),
        pytest.param("question", "schema_version", "question.v0", id="legacy-question-schema"),
        pytest.param("question", "status", "resolved", id="processing-question-status-mismatch"),
    ),
)
def test_strict_replay_rejects_corrupt_foreign_or_stale_rows(
    target: str, field: str, value: object
) -> None:
    student_id, digest, fingerprint, command, fence, question = _strict_replay_rows()
    row = command if target == "command" else question
    row[field] = value
    table = _ReplayTable(command, fence, question)

    result = question_submission_repo.classify_question_submission_replay(
        student_id=student_id,
        idempotency_digest=digest,
        fingerprint=fingerprint,
        table=table,
    )

    assert result is not None
    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.RETRYABLE
    assert result.command is None
    assert result.question is None
    assert "private-original-question" not in repr(result)
    assert all(consistent for *_key, consistent in table.reads)


@pytest.mark.parametrize(
    ("command_status", "question_status"),
    (
        pytest.param("processing", "pending", id="processing-replay"),
        pytest.param("completed", "ai_answered", id="completed-replay"),
        pytest.param("completed", "resolved", id="completed-later-resolution-replay"),
    ),
)
def test_strict_replay_returns_only_exact_owner_bound_question(
    command_status: str, question_status: str
) -> None:
    student_id, digest, fingerprint, command, fence, question = _strict_replay_rows(
        command_status=command_status,
        question_status=question_status,
    )
    table = _ReplayTable(command, fence, question)

    result = question_submission_repo.classify_question_submission_replay(
        student_id=student_id,
        idempotency_digest=digest,
        fingerprint=fingerprint,
        table=table,
    )

    assert result is not None
    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.RESUME
    assert result.command == command
    assert result.question == question
    assert table.reads == [
        (command["PK"], command["SK"], True),
        (fence["PK"], fence["SK"], True),
        (question["PK"], question["SK"], True),
    ]


def test_strict_replay_keeps_mismatch_only_for_authoritative_command() -> None:
    student_id, digest, _fingerprint, command, fence, question = _strict_replay_rows()
    table = _ReplayTable(command, fence, question)

    result = question_submission_repo.classify_question_submission_replay(
        student_id=student_id,
        idempotency_digest=digest,
        fingerprint="f" * 64,
        table=table,
    )

    assert result is not None
    assert result.disposition is question_submission_repo.QuestionAdmissionDisposition.PAYLOAD_MISMATCH
    assert result.command == command
    assert result.question is None
    assert table.reads == [
        (command["PK"], command["SK"], True),
        (fence["PK"], fence["SK"], True),
    ]


def test_route_foreign_question_replay_is_redacted_and_effect_free(monkeypatch) -> None:
    _profile_and_entitlement(monkeypatch)
    student_id, digest, fingerprint, command, _fence, question = _strict_replay_rows()
    effects: list[str] = []
    private_content = "private-foreign-student-question"
    question.update(student_id="student-2", content=private_content)
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: command,
    )
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda _question_id, **_kwargs: question,
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
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-strict-replay",
        },
    )

    assert student_id == "student-1"
    assert digest == command["command_id"]
    assert fingerprint == command["fingerprint"]
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "question_submission_temporarily_unavailable"
    assert private_content not in json.dumps(response.json(), sort_keys=True)
    assert effects == []
