from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from stoa.config import (
    DOCUMENT_MAX_BYTES,
    FREE_STORAGE_BYTES,
    IMAGE_MAX_BYTES,
    IMAGE_MAX_EDGE,
    PAID_STORAGE_BYTES,
    UPLOAD_INTENT_TTL_SECONDS,
    Settings,
)
from stoa.models.attachment import (
    AttachmentReference,
    AttachmentStatus,
    AttachmentSummary,
    UploadIntentRequest,
    UploadIntentResponse,
)
from stoa.security.attachment_errors import (
    ATTACHMENT_ERROR_REGISTRY,
    AttachmentClientAction,
    AttachmentErrorCode,
    attachment_http_response,
    safe_attachment_error_body,
)
from stoa.services.entitlement_service import resolve_student_entitlement


SENSITIVE_CANARIES = {
    "foreign-student-canary",
    "uploads/student/raw-object-key-canary.png",
    "NoSuchKey from Amazon S3 provider-canary",
    "raw OCR extracted-content-canary",
}


def test_upload_contract_constants_are_locked() -> None:
    assert UPLOAD_INTENT_TTL_SECONDS == 1800
    assert IMAGE_MAX_BYTES == 10485760
    assert DOCUMENT_MAX_BYTES == 52428800
    assert IMAGE_MAX_EDGE == 4096
    assert FREE_STORAGE_BYTES == 5368709120
    assert PAID_STORAGE_BYTES == 16106127360


@pytest.mark.parametrize("tier,expected", [("free", FREE_STORAGE_BYTES), ("standard", PAID_STORAGE_BYTES), ("premium", PAID_STORAGE_BYTES)])
def test_effective_entitlement_contract_includes_attachment_storage(tier: str, expected: int) -> None:
    result = resolve_student_entitlement(
        "student-1",
        settings=Settings(),
        student_profile={"subscription_tier": tier},
    )
    assert result["limits"]["attachmentStorageBytes"] == expected


def test_attachment_contract_models_use_only_opaque_public_coordinates() -> None:
    forbidden = {"s3_key", "object_key", "bucket", "ocr", "extracted_content", "student_id", "owner_id"}
    for model in (UploadIntentResponse, AttachmentSummary, AttachmentReference):
        schema = str(model.model_json_schema(by_alias=True)).lower()
        assert all(field not in schema for field in forbidden)

    summary = AttachmentSummary(
        attachmentId="att-1",
        filename="notes.png",
        mediaType="image/png",
        sizeBytes=12,
        status=AttachmentStatus.ACTIVE,
        createdAt=datetime.now(timezone.utc),
    )
    assert set(summary.model_dump(by_alias=True)) == {
        "attachmentId", "filename", "mediaType", "sizeBytes", "status", "createdAt"
    }


@pytest.mark.parametrize("field", ["studentId", "ownerId", "s3Key", "objectKey", "bucket"])
def test_upload_contract_rejects_client_selected_owner_and_storage_fields(field: str) -> None:
    payload = {
        "purpose": "question_image",
        "filename": "work.png",
        "contentType": "image/png",
        "sizeBytes": 10,
        field: "foreign-student-canary",
    }
    with pytest.raises(ValidationError):
        UploadIntentRequest.model_validate(payload)


@pytest.mark.parametrize("field,value", [("purpose", "avatar"), ("purpose", "tutor_document")])
def test_upload_contract_rejects_unsupported_purpose(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        UploadIntentRequest.model_validate(
            {field: value, "filename": "x.png", "contentType": "image/png", "sizeBytes": 1}
        )


def test_attachment_error_registry_is_exhaustive_and_retry_is_bounded() -> None:
    assert set(ATTACHMENT_ERROR_REGISTRY) == set(AttachmentErrorCode)
    retryable = [code for code, contract in ATTACHMENT_ERROR_REGISTRY.items() if contract.retryable]
    assert retryable == [AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE]
    outage = ATTACHMENT_ERROR_REGISTRY[AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE]
    assert outage.idempotent_only is True
    assert outage.max_attempts == 2
    assert {contract.client_action for contract in ATTACHMENT_ERROR_REGISTRY.values()} <= set(AttachmentClientAction)


def test_missing_and_foreign_errors_are_identical_and_redacted() -> None:
    missing = safe_attachment_error_body(
        AttachmentErrorCode.UPLOAD_NOT_FOUND,
        identifier="missing-upload-canary",
        provider_error="NoSuchKey from Amazon S3 provider-canary",
    )
    foreign = safe_attachment_error_body(
        AttachmentErrorCode.UPLOAD_NOT_FOUND,
        identifier="foreign-student-canary",
        object_key="uploads/student/raw-object-key-canary.png",
        ocr_text="raw OCR extracted-content-canary",
    )
    assert missing["code"] == foreign["code"] == "upload_not_found"
    assert missing["message"] == foreign["message"]
    assert missing["correlationId"] != foreign["correlationId"]
    assert set(missing) == set(foreign) == {"code", "message", "correlationId"}
    serialized = f"{missing}{foreign}"
    assert all(canary not in serialized for canary in SENSITIVE_CANARIES)


def test_error_http_response_never_projects_provider_or_ocr_detail() -> None:
    response = attachment_http_response(
        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
        retry_after_seconds=30,
        provider_error="NoSuchKey from Amazon S3 provider-canary",
        ocr_text="raw OCR extracted-content-canary",
    )
    assert response.status_code == 503
    assert response.headers == {"Retry-After": "30"}
    assert set(response.body) == {"code", "message", "correlationId"}
    assert all(canary not in str(response) for canary in SENSITIVE_CANARIES)


def test_attachment_reference_requires_exactly_one_opaque_id() -> None:
    assert AttachmentReference(uploadId="upload-1").upload_id == "upload-1"
    assert AttachmentReference(attachmentId="attachment-1").attachment_id == "attachment-1"
    with pytest.raises(ValidationError):
        AttachmentReference()
    with pytest.raises(ValidationError):
        AttachmentReference(uploadId="upload-1", attachmentId="attachment-1")
