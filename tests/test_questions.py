from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import questions


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=2,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
        s3_images_bucket="images-bucket",
    )


def _client(*, raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_current_user] = lambda: {"sub": "student-1", "role": "student"}
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "UpdateItem")


def test_submit_question_uses_corrected_ocr_text_and_hides_image_key(monkeypatch):
    stored = {}
    usage_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Sek1", "language": "de"},
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
        questions.question_repo,
        "record_daily_question_usage",
        lambda student_id, day, limit, expires_at: usage_calls.append((student_id, limit)) or 1,
    )
    monkeypatch.setattr(
        questions.ocr_service,
        "extract_text_from_s3",
        lambda bucket, key: "raw OCR text from image",
    )
    monkeypatch.setattr(questions.question_repo, "put_question", lambda item: stored.update(item))
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(questions.usage_ledger_service, "record_question_usage_event", lambda **kwargs: {})
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
            "image_s3_key": "private/student-1/image.png",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Solve 2x + 4 = 10"
    assert body["image_s3_key"] is None
    assert body["has_image"] is True
    assert body["ocr_metadata"]["status"] == "succeeded"
    assert body["ocr_metadata"]["correction_applied"] is True
    assert body["ocr_metadata"]["text_length"] == len("raw OCR text from image")
    assert "private/student-1/image.png" not in str(body)
    assert stored["image_s3_key"] == "private/student-1/image.png"
    assert stored["ocr_text"] == "raw OCR text from image"
    assert stored["original_content"] == "Please solve the image"
    assert stored["corrected_text"] == "Solve 2x + 4 = 10"
    assert stored["entitlement"]["effectivePlan"] == "free"
    assert usage_calls == [("student-1", 2)]


def test_submit_question_appends_ocr_text_when_no_correction(monkeypatch):
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Sek1", "language": "de"},
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
    monkeypatch.setattr(questions.ocr_service, "extract_text_from_s3", lambda bucket, key: "Equation from image")
    monkeypatch.setattr(questions.question_repo, "put_question", lambda item: None)
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(questions.usage_ledger_service, "record_question_usage_event", lambda **kwargs: {})
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
            "image_s3_key": "private/student-1/image.png",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "Please solve\n\n[Image text: Equation from image]"
    assert body["image_s3_key"] is None
    assert body["ocr_metadata"]["correction_applied"] is False


def test_get_question_hides_private_image_key(monkeypatch):
    monkeypatch.setattr(
        questions.question_repo,
        "get_question",
        lambda question_id: {
            "question_id": question_id,
            "student_id": "student-1",
            "subject": "math",
            "content": "Question content",
            "image_s3_key": "private/student-1/image.png",
            "has_image": True,
            "ocr_metadata": {"status": "succeeded", "source": "rekognition_s3", "text_length": 12, "correction_applied": False},
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

    response = _client().get("/questions/question-1")

    assert response.status_code == 200
    assert response.json()["image_s3_key"] is None
    assert "private/student-1/image.png" not in str(response.json())


def test_check_daily_limit_uses_atomic_counter(monkeypatch):
    calls = []
    settings = _settings()
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda student_id, day, limit, expires_at: calls.append((student_id, day, limit, expires_at)) or 2,
    )

    questions._check_daily_limit("student-1", "free", settings)

    assert calls[0][0] == "student-1"
    assert calls[0][2] == 2


def test_check_daily_limit_uses_effective_entitlement(monkeypatch):
    calls = []
    settings = _settings()
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda student_id, day, limit, expires_at: calls.append((student_id, day, limit, expires_at)) or 1,
    )

    questions._check_daily_limit(
        "student-1",
        "free",
        settings,
        entitlement={
            "effectivePlan": "premium",
            "limits": {"dailyAiQuestionLimit": 100},
            "blockingReason": None,
        },
    )

    assert calls[0][2] == 100


def test_check_daily_limit_rejects_when_counter_condition_fails(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(questions.question_repo, "record_daily_question_usage", lambda *args: None)

    try:
        questions._check_daily_limit("student-1", "free", settings)
    except questions.HTTPException as exc:
        assert exc.status_code == 429
        assert "Daily question limit (2)" in exc.detail
    else:
        raise AssertionError("quota exhaustion should raise")


def test_record_daily_question_usage_returns_none_on_condition_failure(monkeypatch):
    class FakeTable:
        def update_item(self, **kwargs):
            raise _client_error("ConditionalCheckFailedException")

    monkeypatch.setattr(questions.question_repo, "get_table", lambda: FakeTable())

    assert questions.question_repo.record_daily_question_usage("student-1", "2026-06-07", 2, 1) is None


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
    monkeypatch.setattr(
        questions.question_repo,
        "record_daily_question_usage",
        lambda student_id, day, limit, expires_at: 7,
    )
    monkeypatch.setattr(questions.question_repo, "put_question", lambda item: stored.update(item))
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        questions.ai_service,
        "get_ai_answer",
        lambda **kwargs: {"answer": "AI answer", "steps": [], "hints": [], "similar_exercises": []},
    )
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "get_question_usage_event",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "record_question_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
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
    assert ledger_calls[0]["counter_value"] == 7
    assert ledger_calls[0]["idempotency_key"] == "question-submit-1"
    assert ledger_calls[0]["entitlement"]["effectivePlan"] == "premium"


def test_submit_question_idempotent_retry_without_question_does_not_increment_counter(monkeypatch):
    usage_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Sek1", "language": "de"},
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
        questions.usage_ledger_service,
        "get_question_usage_event",
        lambda **kwargs: {"question_id": "question-existing"},
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

    assert response.status_code == 409
    assert usage_calls == []


def test_submit_question_rejects_mismatched_idempotent_retry_without_counter(monkeypatch):
    usage_calls = []

    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Sek1", "language": "de"},
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
        questions.usage_ledger_service,
        "get_question_usage_event",
        lambda **kwargs: {"question_id": "question-existing"},
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
    assert "different question submission" in response.json()["detail"]
    assert usage_calls == []


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
        },
    )
    monkeypatch.setattr(questions.question_repo, "update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(questions.notify_service, "enqueue_teacher_request", lambda **kwargs: None)
    monkeypatch.setattr(questions.notification_service, "emit_teacher_requested", lambda **kwargs: None)
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


def test_submit_question_persistence_failure_leaves_counter_and_ledger_for_reconciliation(monkeypatch):
    ledger_calls = []
    counter_calls = []
    monkeypatch.setattr(
        questions.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "subscription_tier": "free", "grade": "Sek1", "language": "de"},
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
        questions.usage_ledger_service,
        "get_question_usage_event",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        questions.usage_ledger_service,
        "record_question_usage_event",
        lambda **kwargs: ledger_calls.append(kwargs) or {"idempotency_status": "created"},
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

    assert response.status_code == 500
    assert len(counter_calls) == 1
    assert len(ledger_calls) == 1
    assert ledger_calls[0]["idempotency_key"] == "question-submit-1"
