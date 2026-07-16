from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

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
    AttachmentDecisionError,
    AttachmentErrorCode,
    attachment_http_response,
    safe_attachment_error_body,
)
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services.attachment_service import (
    bind_message_attachments,
    create_upload_intent,
    finalize_upload,
    prepare_message_attachments,
    storage_limit_for_entitlement,
)
from stoa.db.repositories import attachment_repo
from stoa.services.entitlement_service import resolve_student_entitlement
from stoa.services.file_validation_service import ValidationFailure, validate_uploaded_file


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


@pytest.mark.parametrize(
    "tier,expected",
    [
        ("free", FREE_STORAGE_BYTES),
        ("standard", PAID_STORAGE_BYTES),
        ("premium", PAID_STORAGE_BYTES),
    ],
)
def test_effective_entitlement_contract_includes_attachment_storage(
    tier: str, expected: int
) -> None:
    result = resolve_student_entitlement(
        "student-1",
        settings=Settings(),
        student_profile={"subscription_tier": tier},
    )
    assert result["limits"]["attachmentStorageBytes"] == expected


def test_attachment_contract_models_use_only_opaque_public_coordinates() -> None:
    forbidden = {
        "s3_key",
        "object_key",
        "bucket",
        "ocr",
        "extracted_content",
        "student_id",
        "owner_id",
    }
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
        "attachmentId",
        "filename",
        "mediaType",
        "sizeBytes",
        "status",
        "createdAt",
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
    assert {contract.client_action for contract in ATTACHMENT_ERROR_REGISTRY.values()} <= set(
        AttachmentClientAction
    )


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


def _image(fmt: str, size: tuple[int, int] = (8, 8)) -> bytes:
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=fmt)
    return output.getvalue()


def _pdf() -> bytes:
    from pypdf import PdfWriter

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=10, height=10)
    writer.write(output)
    return output.getvalue()


def _ooxml(root: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(f"{root}/document.xml", "<root/>")
    return output.getvalue()


@pytest.mark.parametrize(
    "filename,mime,data,canonical",
    [
        ("x.jpg", "image/jpeg", _image("JPEG"), "image/jpeg"),
        ("x.png", "image/png", _image("PNG"), "image/png"),
        ("x.pdf", "application/pdf", _pdf(), "application/pdf"),
        (
            "x.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _ooxml("word"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "x.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            _ooxml("ppt"),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "x.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _ooxml("xl"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("x.txt", "text/plain", b"safe text", "text/plain"),
        ("x.md", "text/markdown", b"# safe", "text/markdown"),
    ],
)
def test_validate_supported_bytes(filename: str, mime: str, data: bytes, canonical: str) -> None:
    detected = validate_uploaded_file(data, filename, mime)
    assert detected.media_type == canonical
    assert detected.size_bytes == len(data)


@pytest.mark.parametrize("filename", ["x.gif", "x.webp", "x.heic", "x.doc", "x.ppt", "x.xls"])
def test_validate_rejects_unsupported_before_parsing(filename: str) -> None:
    with pytest.raises(ValidationFailure) as error:
        validate_uploaded_file(b"provider-content-canary", filename, "application/octet-stream")
    assert error.value.code.value == "upload_type_not_supported"
    assert "provider-content-canary" not in str(error.value)


def test_validate_rejects_mime_magic_dimension_archive_and_utf8_failures() -> None:
    cases = [
        (b"not png", "x.png", "image/png", "upload_invalid"),
        (_image("PNG"), "x.png", "image/jpeg", "upload_content_mismatch"),
        (_image("PNG", (4097, 1)), "x.png", "image/png", "upload_invalid"),
        (b"\xff", "x.txt", "text/plain", "upload_invalid"),
        (b"a\x00b", "x.md", "text/plain", "upload_invalid"),
    ]
    for data, filename, mime, code in cases:
        with pytest.raises(ValidationFailure) as error:
            validate_uploaded_file(data, filename, mime)
        assert error.value.code.value == code


def test_validate_rejects_ooxml_traversal_and_compression_ratio() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "x")
        archive.writestr("../secret", "x")
    with pytest.raises(ValidationFailure) as error:
        validate_uploaded_file(output.getvalue(), "x.docx", MIME_BY_EXTENSION_DOCX)
    assert error.value.code.value == "upload_invalid"


MIME_BY_EXTENSION_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _IntentRepository:
    def __init__(self) -> None:
        self.item: dict | None = None

    def create_upload_intent(self, item: dict) -> None:
        assert self.item is None
        self.item = item


class _PostS3:
    def __init__(self) -> None:
        self.call: dict | None = None

    def generate_presigned_post(self, **kwargs):
        self.call = kwargs
        return {"url": "https://upload.invalid", "fields": {"key": kwargs["Key"]}}


def _student_actor(user_id: str = "student-1") -> Actor:
    return Actor(
        user_id, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student"
    )


def test_intent_is_owner_bound_opaque_and_post_policy_is_exact() -> None:
    repository, s3 = _IntentRepository(), _PostS3()
    result = create_upload_intent(
        UploadIntentRequest(
            purpose="question_image", filename="work.png", contentType="image/png", sizeBytes=10
        ),
        _student_actor(),
        s3=s3,
        settings=Settings(s3_images_bucket="bucket"),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        repository=repository,
    )
    assert set(result) == {
        "uploadId",
        "url",
        "fields",
        "expiresAt",
        "maxBytes",
        "acceptedTypes",
        "status",
    }
    assert repository.item and repository.item["owner_id"] == "student-1"
    assert repository.item["expires_at"] == 1767227400
    assert "object_key" in repository.item and "object_key" not in str(result)
    assert s3.call["ExpiresIn"] == 1800
    assert ["content-length-range", 1, IMAGE_MAX_BYTES] in s3.call["Conditions"]


def test_storage_quota_uses_authoritative_entitlement_tiers() -> None:
    assert storage_limit_for_entitlement("free") == FREE_STORAGE_BYTES
    assert storage_limit_for_entitlement("standard") == PAID_STORAGE_BYTES
    assert storage_limit_for_entitlement("premium") == PAID_STORAGE_BYTES


class _FinalizeRepository:
    def __init__(self, item: dict | None) -> None:
        self.item = item
        self.events: list[str] = []

    def get_upload_intent(self, upload_id: str):
        return self.item

    def begin_validation(self, *args) -> bool:
        self.events.append("begin")
        return True

    def mark_validated(self, *args) -> bool:
        self.events.append("validated")
        return True

    def mark_invalid(self, *args) -> bool:
        self.events.append("invalid")
        return True

    def release_validation(self, *args) -> bool:
        self.events.append("released")
        return True


class _Body:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, limit: int) -> bytes:
        return self.data[:limit]


class _FinalizeS3:
    def __init__(self, data: bytes):
        self.data = data
        self.calls: list[str] = []

    def head_object(self, **kwargs):
        self.calls.append("head")
        return {"ContentLength": len(self.data), "ContentType": "image/png", "ETag": "etag"}

    def get_object(self, **kwargs):
        self.calls.append("get")
        return {"Body": _Body(self.data), "ETag": "etag"}


def _pending_upload(owner: str = "student-1") -> dict:
    return {
        "upload_id": "upload-1",
        "owner_id": owner,
        "object_key": "uploads/private/object-canary.png",
        "original_filename": "work.png",
        "declared_type": "image/png",
        "max_bytes": IMAGE_MAX_BYTES,
        "status": "pending_upload",
        "version": 1,
        "expires_at": 2_000_000_000,
    }


def test_finalize_heads_reads_validates_then_transitions() -> None:
    repository = _FinalizeRepository(_pending_upload())
    s3 = _FinalizeS3(_image("PNG"))
    result = finalize_upload(
        "upload-1",
        _student_actor(),
        s3=s3,
        settings=Settings(s3_images_bucket="bucket"),
        repository=repository,
    )
    assert result["status"] == "validated"
    assert s3.calls == ["head", "get"]
    assert repository.events == ["begin", "validated"]


def test_foreign_finalize_is_hidden_before_s3_read() -> None:
    repository = _FinalizeRepository(_pending_upload("foreign-student-canary"))
    s3 = _FinalizeS3(_image("PNG"))
    with pytest.raises(AttachmentDecisionError) as error:
        finalize_upload(
            "upload-1",
            _student_actor(),
            s3=s3,
            settings=Settings(s3_images_bucket="bucket"),
            repository=repository,
        )
    assert error.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert s3.calls == []


class _MessageAttachmentRepository:
    association_key = staticmethod(attachment_repo.association_key)
    build_message_attachment_transaction = staticmethod(
        attachment_repo.build_message_attachment_transaction
    )

    def __init__(self, uploads=None, attachments=None, used_bytes=0) -> None:
        self.uploads = uploads or {}
        self.attachments = attachments or {}
        self.used_bytes = used_bytes
        self.transactions = []

    def get_upload_intent(self, upload_id):
        return self.uploads.get(upload_id)

    def get_attachment(self, attachment_id):
        return self.attachments.get(attachment_id)

    def get_storage_usage(self, owner_id):
        return self.used_bytes

    def transact(self, operations):
        self.transactions.append(operations)


def _validated_upload(owner="student-1") -> dict:
    return {
        "upload_id": "upload-1",
        "owner_id": owner,
        "object_key": "uploads/private/provider-coordinate-canary.pdf",
        "original_filename": "notes.pdf",
        "detected_type": "application/pdf",
        "content_length": 321,
        "status": "validated",
        "expected_kind": "conversation_attachment",
        "version": 3,
        "expires_at": 2_000_000_000,
        "etag": "private-version-canary",
    }


def _saved_attachment(owner="student-1") -> dict:
    return {
        "attachment_id": "attachment-saved",
        "owner_id": owner,
        "object_key": "uploads/private/saved-provider-coordinate.pdf",
        "original_filename": "saved.pdf",
        "detected_type": "application/pdf",
        "content_length": 777,
        "status": "active",
        "created_at": "2026-07-16T00:00:00+00:00",
    }


def test_prepare_message_attachments_conceals_missing_foreign_and_invalid_as_no_effect() -> None:
    for repository in (
        _MessageAttachmentRepository(),
        _MessageAttachmentRepository(uploads={"upload-1": _validated_upload("foreign")}),
        _MessageAttachmentRepository(
            uploads={"upload-1": {**_validated_upload(), "status": "invalid"}}
        ),
    ):
        with pytest.raises(AttachmentDecisionError) as error:
            prepare_message_attachments(
                [AttachmentReference(uploadId="upload-1")],
                _student_actor(),
                repository=repository,
            )
        assert error.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
        assert repository.transactions == []


def test_fresh_and_reused_message_attachments_share_one_atomic_transaction() -> None:
    repository = _MessageAttachmentRepository(
        uploads={"upload-1": _validated_upload()},
        attachments={"attachment-saved": _saved_attachment()},
    )
    references = [
        AttachmentReference(uploadId="upload-1"),
        AttachmentReference(attachmentId="attachment-saved"),
    ]
    prepared = prepare_message_attachments(
        references, _student_actor(), repository=repository
    )
    summaries = bind_message_attachments(
        message={
            "PK": "CONV#conv-1",
            "SK": "MSG#message-1",
            "message_id": "message-1",
            "content": "use both",
        },
        conversation_id="conv-1",
        actor=_student_actor(),
        prepared=prepared,
        effective_plan="free",
        now=datetime(2026, 7, 16, tzinfo=timezone.utc),
        repository=repository,
    )
    assert len(repository.transactions) == 1
    operations = repository.transactions[0]
    assert sum("Update" in operation for operation in operations) == 2
    storage_updates = [
        operation["Update"]
        for operation in operations
        if "Update" in operation and operation["Update"]["Key"]["PK"].startswith("STORAGE#")
    ]
    assert storage_updates[0]["ExpressionAttributeValues"][":size"] == 321
    assert sum("ConditionCheck" in operation for operation in operations) == 1
    message = operations[0]["Put"]["Item"]
    assert message["attachment_ids"][1] == "attachment-saved"
    public = str([summary.model_dump(by_alias=True) for summary in summaries])
    assert "provider-coordinate" not in public
    assert "private-version" not in public


def test_saved_attachment_reuse_does_not_mutate_storage_usage() -> None:
    repository = _MessageAttachmentRepository(
        attachments={"attachment-saved": _saved_attachment()}, used_bytes=FREE_STORAGE_BYTES
    )
    prepared = prepare_message_attachments(
        [AttachmentReference(attachmentId="attachment-saved")],
        _student_actor(),
        repository=repository,
    )
    bind_message_attachments(
        message={"PK": "CONV#other", "SK": "MSG#new", "message_id": "new"},
        conversation_id="other",
        actor=_student_actor(),
        prepared=prepared,
        effective_plan="free",
        repository=repository,
    )
    assert all(
        not (
            "Update" in operation
            and operation["Update"]["Key"]["PK"].startswith("STORAGE#")
        )
        for operation in repository.transactions[0]
    )
