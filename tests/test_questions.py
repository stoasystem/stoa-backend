from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.config import Settings, get_settings
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import questions
from stoa.db.repositories import question_submission_repo
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services.ocr_service import OcrAttachmentFailure


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=2,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
        s3_images_bucket="images-bucket",
    )


def _actor(role=CanonicalRole.STUDENT, user_id="student-1"):
    return Actor(
        user_id,
        "https://identity.test",
        f"{user_id}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )


def _client(*, raise_server_exceptions: bool = True, actor=None) -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "UpdateItem")


def _question_command(
    *, caller_key: str, fingerprint: str, question_id: str = "question-existing"
) -> dict[str, object]:
    digest = question_submission_repo.question_submission_command_digest(
        "student-1", caller_key
    )
    return {
        "PK": "USER#student-1",
        "SK": f"QUESTION_SUBMISSION#{digest}",
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "command_id": digest,
        "student_id": "student-1",
        "idempotency_digest": digest,
        "question_id": question_id,
        "fingerprint": fingerprint,
        "status": "processing",
        "account_fence_generation": 1,
        "version": 1,
    }


def _admitted_command(kwargs: dict[str, object]) -> dict[str, object]:
    question = kwargs["question"]
    assert isinstance(question, dict)
    return {
        "entity_type": "question_submission_command",
        "schema_version": "question-submission-command.v2",
        "command_id": kwargs["idempotency_digest"],
        "student_id": kwargs["student_id"],
        "idempotency_digest": kwargs["idempotency_digest"],
        "question_id": question["question_id"],
        "fingerprint": kwargs["fingerprint"],
        "account_fence_generation": 1,
        "status": "processing",
        "version": 1,
    }


def _begin_effect(command, question, kind, **_kwargs):
    return question_submission_repo.QuestionEffectResult(
        question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER,
        effect={
            "effect_kind": str(kind),
            "command": dict(command),
            "question": dict(question),
        },
    )


def _record_effect(effect, result, **_kwargs):
    return question_submission_repo.QuestionEffectResult(
        question_submission_repo.QuestionEffectDisposition.RESULT_READY,
        effect={**effect, "result": dict(result)},
    )


def _complete_effect(effect, **_kwargs):
    command = dict(effect["command"])
    question = dict(effect["question"])
    result = effect["result"]
    if effect["effect_kind"] == "ocr":
        question.update(
            ocr_text=result["ocr_text"],
            ocr_metadata=result["ocr_metadata"],
        )
        command["status"] = "processing"
    else:
        question.update(
            status="ai_answered",
            ai_response=result["ai_response"],
            knowledge_points=result["knowledge_points"],
            topic_seeds=result["topic_seeds"],
        )
        command["status"] = "completed"
    question["version"] = int(question["version"]) + 1
    command["version"] = int(command["version"]) + 1
    return question_submission_repo.QuestionEffectResult(
        question_submission_repo.QuestionEffectDisposition.COMPLETED,
        effect=dict(effect),
        question=question,
        command=command,
    )


def _prepared_question_attachment() -> dict:
    return {
        "kind": "upload",
        "identity": ("upload", "upload-1"),
        "record": {
            "upload_id": "upload-1",
            "owner_id": "student-1",
            "status": "consuming",
            "version": 2,
            "expires_at": 2_000_000_000,
            "consume_epoch": 1_900_000_000,
        },
        "attachment": {
            "attachment_id": "attachment-1",
            "owner_id": "student-1",
            "immutable_object_key": "objects/private/student-1/image.png",
            "immutable_version_id": "image-version-1",
            "immutable_etag": "image-etag-1",
            "content_sha256": "0" * 64,
            "original_filename": "work.png",
            "detected_type": "image/png",
            "content_length": 123,
            "status": "active",
            "created_at": "2026-07-16T00:00:00+00:00",
        },
    }


@pytest.fixture(autouse=True)
def _atomic_question_admission(monkeypatch):
    monkeypatch.setattr(
        questions.question_submission_repo.account_deletion_repo,
        "require_active_account_fence",
        lambda *_args, **_kwargs: {"status": "active", "generation": 1},
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **kwargs: question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            command=_admitted_command(kwargs),
            question=dict(kwargs["question"]),
        ),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "begin_question_effect",
        _begin_effect,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "record_question_effect_result",
        _record_effect,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "complete_question_effect",
        _complete_effect,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "mark_question_effect_outcome_unknown",
        lambda effect, **_kwargs: question_submission_repo.QuestionEffectResult(
            question_submission_repo.QuestionEffectDisposition.PROVIDER_OUTCOME_UNKNOWN,
            effect=dict(effect),
        ),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "mark_question_effect_terminal",
        lambda effect, **_kwargs: question_submission_repo.QuestionEffectResult(
            question_submission_repo.QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION,
            effect=dict(effect),
        ),
    )
    monkeypatch.setattr(
        questions,
        "_question_attachment_operations",
        lambda **kwargs: ("prepared-attachment",)
        if kwargs["prepared"] is not None
        else (),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "list_attachment_summaries",
        lambda attachment_ids: {
            attachment_id: _attachment_summary() for attachment_id in attachment_ids
        },
    )


def _attachment_summary() -> dict:
    return {
        "attachmentId": "attachment-1",
        "filename": "work.png",
        "mediaType": "image/png",
        "sizeBytes": 123,
        "status": "active",
        "createdAt": "2026-07-16T00:00:00Z",
    }


def _patch_question_submit_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": 2},
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(questions.question_repo, "record_daily_question_usage", lambda *args: 1)
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "record_question_usage_event",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {
            "answer": "AI answer",
            "steps": [],
            "hints": [],
            "similar_exercises": [],
        },
    )


def test_submit_question_uses_corrected_ocr_text_and_hides_image_key(monkeypatch):
    stored = {}

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": settings.free_tier_daily_question_limit},
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda attachment, settings_obj: "raw OCR text from image",
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: _prepared_question_attachment(),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **kwargs: stored.update(kwargs["question"])
        or question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            command=_admitted_command(kwargs),
            question=dict(kwargs["question"]),
        ),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "release_question_attachment_reservation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {"answer": "AI answer", "steps": [], "hints": [], "similar_exercises": []},
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve the image",
            "corrected_text": "Solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-corrected-ocr",
            "attachment": {"uploadId": "upload-1"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Solve 2x + 4 = 10"
    assert body["has_image"] is True
    assert body["attachment"] == _attachment_summary()
    assert body["ocr_metadata"]["status"] == "succeeded"
    assert body["ocr_metadata"]["correction_applied"] is True
    assert body["ocr_metadata"]["text_length"] == len("raw OCR text from image")
    assert "private/student-1/image.png" not in str(body)
    assert "raw OCR text from image" not in str(body)
    assert stored["attachment_id"] == "attachment-1"
    assert stored["attachment_source_identity"] == "upload:upload-1"
    assert stored["ocr_text"] is None
    assert stored["original_content"] == "Please solve the image"
    assert stored["corrected_text"] == "Solve 2x + 4 = 10"
    assert stored["entitlement"]["effectivePlan"] == "free"
    assert stored["status"] == "pending"


def test_submit_question_appends_ocr_text_when_no_correction(monkeypatch):
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": settings.free_tier_daily_question_limit},
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(questions.question_repo, "record_daily_question_usage", lambda *args: 1)
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda attachment, settings_obj: "Equation from image",
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: _prepared_question_attachment(),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "commit_question_with_attachment",
        lambda **kwargs: _attachment_summary(),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "release_question_attachment_reservation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        questions.usage_ledger_service, "record_question_usage_event", lambda **kwargs: {}
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {"answer": "AI answer", "steps": [], "hints": [], "similar_exercises": []},
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve",
            "subject": "math",
            "idempotencyKey": "question-submit-appended-ocr",
            "attachment": {"uploadId": "upload-1"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Please solve"
    assert "Equation from image" not in str(body)
    assert body["ocr_metadata"]["correction_applied"] is False


def test_question_quota_race_stable_error_has_no_question_or_ai_effect(monkeypatch):
    _patch_question_submit_dependencies(monkeypatch)
    effects = []
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: _prepared_question_attachment(),
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda *args, **kwargs: "private-ocr-canary",
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **_kwargs: question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.QUOTA_EXCEEDED
        ),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "release_question_attachment_reservation",
        lambda *args, **kwargs: effects.append("released"),
    )
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: effects.append("ai"),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "private-question-canary",
            "subject": "math",
            "idempotencyKey": "question-submit-quota-race",
            "attachment": {"uploadId": "upload-1"},
        },
    )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "question_quota_exceeded"
    assert effects == ["released"]
    assert "private-question-canary" not in response.text
    assert "private-ocr-canary" not in response.text


def test_get_question_hides_private_image_key(monkeypatch):
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "content": "Question content",
            "attachment_id": "attachment-1",
            "has_image": True,
            "ocr_metadata": {
                "status": "succeeded",
                "source": "rekognition_s3",
                "text_length": 12,
                "correction_applied": False,
            },
            "status": "pending",
            "ai_response": None,
            "teacher_id": None,
            "teacher_response": None,
            "knowledge_points": [],
            "student_feedback": None,
            "created_at": "2026-06-07T12:00:00+00:00",
            "resolved_at": None,
        },
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "list_attachment_summaries",
        lambda attachment_ids: {"attachment-1": _attachment_summary()},
    )

    response = _client().get("/questions/question-1")

    assert response.status_code == 200
    assert "image_s3_key" not in response.json()
    assert response.json()["attachment"] == _attachment_summary()
    assert "private/student-1/image.png" not in str(response.json())


def test_question_limit_uses_subscription_tier_default():
    settings = _settings()
    assert questions._question_limit("free", settings) == 2


def test_question_limit_uses_effective_entitlement():
    settings = _settings()
    assert questions._question_limit(
        "free",
        settings,
        entitlement={
            "effectivePlan": "premium",
            "limits": {"dailyAiQuestionLimit": 100},
            "blockingReason": None,
        },
    ) == 100


def test_question_limit_uses_configured_tier_when_entitlement_limit_absent():
    settings = _settings()
    assert questions._question_limit("standard", settings, entitlement={}) == 30


def test_record_daily_question_usage_returns_none_on_condition_failure(monkeypatch):
    class FakeTable:
        def update_item(self, **kwargs):
            raise _client_error("ConditionalCheckFailedException")

    monkeypatch.setattr(questions.question_repo, "get_table", lambda: FakeTable())

    assert (
        questions.question_repo.record_daily_question_usage("student-1", "2026-06-07", 2, 1) is None
    )


def test_submit_question_records_privacy_safe_usage_ledger_event(monkeypatch):
    stored = {}
    ledger_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "premium",
            "source": "provider_billing",
            "limits": {"dailyAiQuestionLimit": settings.premium_tier_daily_question_limit},
            "parentId": "parent-1",
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {"answer": "AI answer", "steps": [], "hints": [], "similar_exercises": []},
    )
    def admit(**kwargs):
        stored.update(kwargs["question"])
        ledger_calls.append(kwargs["usage_event"])
        return question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.ADMITTED,
            question=dict(kwargs["question"]),
        )

    monkeypatch.setattr(
        questions.question_submission_repo, "admit_question_submission", admit
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-1",
        },
    )

    assert response.status_code == 201
    assert ledger_calls[0]["student_id"] == "student-1"
    assert ledger_calls[0]["question_id"] == stored["question_id"]
    assert ledger_calls[0]["counter_value_after"] == 1
    assert ledger_calls[0]["idempotency_digest"] == (
        question_submission_repo.question_submission_command_digest(
            "student-1", "question-submit-1"
        )
    )
    assert "idempotency_key" not in ledger_calls[0]
    assert ledger_calls[0]["effective_plan"] == "premium"
    assert ledger_calls[0]["entitlement_snapshot"]["effectivePlan"] == "premium"


def test_submit_question_idempotent_retry_without_question_does_not_increment_counter(monkeypatch):
    usage_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": settings.free_tier_daily_question_limit},
            "blockingReason": None,
        },
    )
    fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve 2x + 4 = 10",
        corrected_content=None,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: _question_command(
            caller_key="question-submit-1", fingerprint=fingerprint
        ),
    )
    monkeypatch.setattr(questions.question_repo, "get_question", lambda question_id: None)
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *args: usage_calls.append(args) or 1,
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-1",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "question_submission_temporarily_unavailable"
    )
    assert usage_calls == []


def test_submit_question_rejects_mismatched_idempotent_retry_without_counter(monkeypatch):
    usage_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": settings.free_tier_daily_question_limit},
            "blockingReason": None,
        },
    )
    original_fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve 2x + 4 = 10",
        corrected_content=None,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: _question_command(
            caller_key="question-submit-1", fingerprint=original_fingerprint
        ),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "content": "Please solve 2x + 4 = 10",
            "original_content": "Please solve 2x + 4 = 10",
            "corrected_text": None,
            "image_s3_key": None,
            "has_image": False,
            "status": "pending",
            "ai_response": None,
            "teacher_id": None,
            "teacher_response": None,
            "knowledge_points": [],
            "student_feedback": None,
            "created_at": "2026-06-07T12:00:00+00:00",
            "resolved_at": None,
        },
    )
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *args: usage_calls.append(args) or 1,
    )

    response = _client().post(
        "/questions",
        json={
            "content": "Please solve a different problem",
            "subject": "math",
            "idempotencyKey": "question-submit-1",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "question_submission_payload_mismatch"
    assert usage_calls == []


def test_question_contract_has_no_client_storage_coordinates() -> None:
    schema = _client().app.openapi()
    request_schema = str(schema["components"]["schemas"]["SubmitQuestionRequest"]).lower()
    response_schema = str(schema["components"]["schemas"]["QuestionResponse"]).lower()
    for forbidden in ("image_s3_key", "s3key", "objectkey", "bucket"):
        assert forbidden not in request_schema
        assert forbidden not in response_schema
    assert "attachment" in request_schema
    assert "attachment" in response_schema


def test_ocr_receives_only_server_resolved_attachment(monkeypatch) -> None:
    _patch_question_submit_dependencies(monkeypatch)
    observed = []
    prepared = _prepared_question_attachment()
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: prepared,
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda attachment, settings_obj: observed.append(dict(attachment)) or "2x = 4",
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "commit_question_with_attachment",
        lambda **kwargs: _attachment_summary(),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this image",
            "subject": "math",
            "idempotencyKey": "question-submit-resolved-attachment",
            "attachment": {"uploadId": "upload-1"},
        },
    )
    assert response.status_code == 201
    assert observed == [prepared["attachment"]]
    assert observed[0]["immutable_version_id"] == "image-version-1"
    assert "object_key" not in str(response.json()).lower()


def test_transient_ocr_failure_returns_durable_processing_question(
    monkeypatch, caplog
) -> None:
    _patch_question_submit_dependencies(monkeypatch)
    effects = []
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: _prepared_question_attachment(),
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OcrAttachmentFailure("provider-payload-canary", terminal=False)
        ),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "release_question_attachment_reservation",
        lambda *args, **kwargs: effects.append("released"),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "invalidate_question_attachment",
        lambda *args, **kwargs: effects.append("invalidated"),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "commit_question_with_attachment",
        lambda **kwargs: effects.append("committed"),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this image",
            "subject": "math",
            "idempotencyKey": "question-submit-transient-ocr",
            "attachment": {"uploadId": "upload-1"},
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["ocr_metadata"]["status"] == "processing"
    assert "provider-payload-canary" not in str(response.json())
    assert "provider-payload-canary" not in caplog.text
    assert "event_category=question_ocr_failed" in caplog.text
    assert "exception_class=OcrAttachmentFailure" in caplog.text
    assert effects == []


def test_terminal_ocr_failure_preserves_durable_attachment_and_processing_question(
    monkeypatch,
) -> None:
    _patch_question_submit_dependencies(monkeypatch)
    effects = []
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: _prepared_question_attachment(),
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OcrAttachmentFailure("invalid-object-provider-canary", terminal=True)
        ),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "invalidate_question_attachment",
        lambda *args, **kwargs: effects.append("invalidated"),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "commit_question_with_attachment",
        lambda **kwargs: effects.append("committed"),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this image",
            "subject": "math",
            "idempotencyKey": "question-submit-terminal-ocr",
            "attachment": {"uploadId": "upload-1"},
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["attachment"]["attachmentId"] == "attachment-1"
    assert "provider-canary" not in str(response.json())
    assert effects == []


def test_unresolved_attachment_fails_before_counter_ocr_or_question(monkeypatch) -> None:
    _patch_question_submit_dependencies(monkeypatch)
    effects = []
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        ),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *args: effects.append("counter"),
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_attachment",
        lambda *args, **kwargs: effects.append("ocr"),
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "commit_question_with_attachment",
        lambda **kwargs: effects.append("commit"),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this image",
            "subject": "math",
            "idempotencyKey": "question-submit-missing-attachment",
            "attachment": {"attachmentId": "foreign-or-missing"},
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "upload_not_found"
    assert effects == []


def test_idempotency_key_cannot_be_rebound_to_another_attachment(monkeypatch):
    effects = []
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "limits": {"dailyAiQuestionLimit": 2},
        },
    )
    original_fingerprint = question_submission_repo.question_submission_fingerprint(
        subject="math",
        original_content="Please solve this equation",
        corrected_content=None,
        attachment_identities=("upload:upload-original",),
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "get_question_submission_command",
        lambda *_args, **_kwargs: _question_command(
            caller_key="question-submit-attachment",
            fingerprint=original_fingerprint,
        ),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "content": "Please solve this equation",
            "original_content": "Please solve this equation",
            "corrected_text": None,
            "attachment_source_identity": "upload:upload-original",
            "attachment_id": "attachment-original",
            "has_image": True,
            "status": "pending",
            "ai_response": None,
            "teacher_id": None,
            "teacher_response": None,
            "knowledge_points": [],
            "student_feedback": None,
            "created_at": "2026-07-16T00:00:00Z",
            "resolved_at": None,
        },
    )
    monkeypatch.setattr(
        questions.attachment_service,
        "reserve_question_attachment",
        lambda *args, **kwargs: effects.append("reserve"),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *args: effects.append("counter"),
    )
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this equation",
            "subject": "math",
            "idempotencyKey": "question-submit-attachment",
            "attachment": {"uploadId": "upload-different"},
        },
    )
    assert response.status_code == 409
    assert effects == []


def test_request_teacher_records_support_visible_usage_event(monkeypatch):
    ledger_calls = []
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "status": "ai_answered",
            "version": 1,
        },
    )
    monkeypatch.setattr(
        questions.question_repo,
        "mutate_question",
        lambda question, *, status, extra_attrs, **_kwargs: (
            questions.question_repo.QuestionMutationResult(
                questions.question_repo.QuestionMutationDisposition.APPLIED,
                str(question["question_id"]),
                {
                    **question,
                    "status": status,
                    "version": int(question["version"]) + 1,
                    **extra_attrs,
                },
            )
        ),
    )
    monkeypatch.setattr(questions.notify_service, "enqueue_teacher_request", lambda **kwargs: None)
    monkeypatch.setattr(
        questions.notification_service, "emit_teacher_requested", lambda **kwargs: None
    )
    monkeypatch.setattr(
        questions.teacher_dispatch_service,
        "dispatch_question",
        lambda *args, **kwargs: {"status": "deferred"},
    )
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "record_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
    )

    response = _client().post("/questions/question-1/request-teacher")

    assert response.status_code == 202
    assert ledger_calls[0]["action"] == "question_teacher_help_request"
    assert ledger_calls[0]["student_id"] == "student-1"
    assert ledger_calls[0]["request_correlation_id"] == "question-1"
    assert ledger_calls[0]["metadata"] == {
        "question_id": "question-1",
        "subject": "math",
        "status": "escalated",
    }


def test_submit_question_precommit_failure_has_no_legacy_partial_writes(
    monkeypatch,
):
    ledger_calls = []
    counter_calls = []
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "subscription_tier": "free",
            "grade": "Sek1",
            "language": "de",
        },
    )
    monkeypatch.setattr(
        questions.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "effectivePlan": "free",
            "source": "local",
            "limits": {"dailyAiQuestionLimit": settings.free_tier_daily_question_limit},
            "blockingReason": None,
        },
    )
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *args: counter_calls.append(args) or 1,
    )
    monkeypatch.setattr(
        questions.question_submission_repo,
        "admit_question_submission",
        lambda **_kwargs: question_submission_repo.QuestionAdmissionResult(
            question_submission_repo.QuestionAdmissionDisposition.RETRYABLE
        ),
    )

    def fail_put_question(item):
        raise RuntimeError("dynamodb write failed")

    monkeypatch.setattr(questions.question_repo, "put_question", fail_put_question)
    client = _client(raise_server_exceptions=False)

    response = client.post(
        "/questions",
        json={
            "content": "Please solve 2x + 4 = 10",
            "subject": "math",
            "idempotencyKey": "question-submit-1",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "question_submission_temporarily_unavailable"
    )
    assert counter_calls == []
    assert ledger_calls == []


def test_submit_question_rejects_body_owner_substitution_before_any_write(monkeypatch):
    calls = []
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda *_args: calls.append("counter"),
    )
    monkeypatch.setattr(questions.question_repo, "put_question", lambda *_args: calls.append("put"))
    response = _client().post(
        "/questions",
        json={
            "content": "Please solve this equation",
            "subject": "math",
            "student_id": "student-2",
        },
    )
    assert response.status_code == 422
    assert calls == []


def test_sec_002_real_other_owner_and_random_question_are_indistinguishable(monkeypatch):
    real = {
        "question_id": "question-real",
        "student_id": "student-1",
        "subject": "math",
        "content": "private",
        "status": "pending",
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "student_feedback": None,
        "created_at": "2026-07-15T00:00:00Z",
        "resolved_at": None,
    }
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: real if question_id == "question-real" else None,
    )
    client = _client(actor=_actor(user_id="student-2"))
    hidden = client.get("/questions/question-real")
    missing = client.get("/questions/question-random")
    assert hidden.status_code == missing.status_code == 404
    for response in (hidden, missing):
        assert response.json()["detail"]["code"] == "resource_not_found"
        assert response.json()["detail"]["message"] == "The requested resource was not found."


def test_bound_parent_and_current_task_teacher_question_positive_controls(monkeypatch):
    item = {
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "content": "private",
        "status": "teacher_active",
        "dispatch_status": "accepted",
        "teacher_id": "teacher-1",
        "teacher_response": None,
        "ai_response": None,
        "knowledge_points": [],
        "student_feedback": None,
        "created_at": "2026-07-15T00:00:00Z",
        "resolved_at": None,
    }
    accounts = {
        "student-1": {"user_id": "student-1", "role": "student", "account_status": "active"},
        "parent-1": {"user_id": "parent-1", "role": "parent", "account_status": "active"},
        "teacher-1": {"user_id": "teacher-1", "role": "teacher", "account_status": "active"},
    }
    row = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "version": 1,
        "status": "active",
    }
    monkeypatch.setattr(questions.question_repo, "get_question", lambda *_: item)
    monkeypatch.setattr(questions.question_repo, "get_teacher_session", lambda *_: None)
    monkeypatch.setattr(questions.question_repo, "get_teacher_assignment", lambda *_: None)
    monkeypatch.setattr(questions.user_repo, "get_user", lambda user_id: accounts.get(user_id))
    monkeypatch.setattr(questions.user_repo, "get_parent_student_binding", lambda *_: row)
    monkeypatch.setattr(questions.user_repo, "get_student_parent_binding", lambda *_: dict(row))
    parent = _client(actor=_actor(CanonicalRole.PARENT, "parent-1")).get("/questions/question-1")
    teacher = _client(actor=_actor(CanonicalRole.TEACHER, "teacher-1")).get("/questions/question-1")
    assert parent.status_code == teacher.status_code == 200


def test_question_repository_outage_returns_503_before_feedback_mutation(monkeypatch):
    writes = []
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda *_: (_ for _ in ()).throw(TimeoutError("store canary")),
    )
    monkeypatch.setattr(
        questions.question_repo,
        "update_status",
        lambda *_args, **_kwargs: writes.append("update"),
    )
    response = _client().post("/questions/question-1/feedback", json={"rating": 5})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert writes == []
