"""Closed, redacted attachment failure and client-recovery contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AttachmentErrorCode(StrEnum):
    UPLOAD_NOT_FOUND = "upload_not_found"
    UPLOAD_EXPIRED = "upload_expired"
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_TYPE_NOT_SUPPORTED = "upload_type_not_supported"
    UPLOAD_CONTENT_MISMATCH = "upload_content_mismatch"
    UPLOAD_INVALID = "upload_invalid"
    UPLOAD_CHUNK_CONFLICT = "upload_chunk_conflict"
    STORAGE_QUOTA_EXCEEDED = "storage_quota_exceeded"
    UPLOAD_SERVICE_UNAVAILABLE = "upload_service_unavailable"


class AttachmentClientAction(StrEnum):
    SELECT_FILE = "select_file"
    REDUCE_SIZE = "reduce_size"
    DELETE_OR_UPGRADE = "delete_or_upgrade"
    RETRY_LATER = "retry_later"


@dataclass(frozen=True, slots=True)
class AttachmentErrorContract:
    http_status: int
    safe_message: str
    client_action: AttachmentClientAction
    retryable: bool = False
    idempotent_only: bool = False
    max_attempts: int = 0


ATTACHMENT_ERROR_REGISTRY: dict[AttachmentErrorCode, AttachmentErrorContract] = {
    AttachmentErrorCode.UPLOAD_NOT_FOUND: AttachmentErrorContract(
        404, "Select or upload the file again.", AttachmentClientAction.SELECT_FILE
    ),
    AttachmentErrorCode.UPLOAD_EXPIRED: AttachmentErrorContract(
        409, "This upload expired. Select the file again.", AttachmentClientAction.SELECT_FILE
    ),
    AttachmentErrorCode.UPLOAD_TOO_LARGE: AttachmentErrorContract(
        422, "This file is too large. Choose a smaller file.", AttachmentClientAction.REDUCE_SIZE
    ),
    AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED: AttachmentErrorContract(
        422, "This file type is not supported. Choose another file.", AttachmentClientAction.SELECT_FILE
    ),
    AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH: AttachmentErrorContract(
        422, "This file does not match its type. Select the file again.", AttachmentClientAction.SELECT_FILE
    ),
    AttachmentErrorCode.UPLOAD_INVALID: AttachmentErrorContract(
        422, "This file may be damaged. Select another file.", AttachmentClientAction.SELECT_FILE
    ),
    AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT: AttachmentErrorContract(
        409,
        "This upload chunk conflicts with an earlier chunk. Select the file again.",
        AttachmentClientAction.SELECT_FILE,
    ),
    AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED: AttachmentErrorContract(
        409,
        "Storage is full. Delete attachments or upgrade your plan.",
        AttachmentClientAction.DELETE_OR_UPGRADE,
    ),
    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE: AttachmentErrorContract(
        503,
        "Uploads are temporarily unavailable. Try again later.",
        AttachmentClientAction.RETRY_LATER,
        retryable=True,
        idempotent_only=True,
        max_attempts=2,
    ),
}

if set(ATTACHMENT_ERROR_REGISTRY) != set(AttachmentErrorCode):
    missing = set(AttachmentErrorCode) - set(ATTACHMENT_ERROR_REGISTRY)
    extra = set(ATTACHMENT_ERROR_REGISTRY) - set(AttachmentErrorCode)
    raise RuntimeError(f"attachment error registry is not exhaustive: missing={missing}, extra={extra}")


def safe_attachment_error_body(
    code: AttachmentErrorCode,
    *,
    correlation_id: str | None = None,
    **_ignored_sensitive_detail: Any,
) -> dict[str, str]:
    """Project only stable public fields; correlation IDs originate on the server."""
    contract = ATTACHMENT_ERROR_REGISTRY[code]
    server_correlation_id = correlation_id or str(uuid4())
    return {
        "code": code.value,
        "message": contract.safe_message,
        "correlationId": server_correlation_id,
    }


@dataclass(slots=True)
class AttachmentDecisionError(Exception):
    code: AttachmentErrorCode
    internal_detail: str | None = None
    correlation_id: str | None = None

    @property
    def status_code(self) -> int:
        return ATTACHMENT_ERROR_REGISTRY[self.code].http_status

    def public_body(self) -> dict[str, str]:
        return safe_attachment_error_body(self.code, correlation_id=self.correlation_id)


@dataclass(frozen=True, slots=True)
class AttachmentHttpResponse:
    status_code: int
    body: dict[str, str]
    headers: dict[str, str]


def attachment_http_response(
    code: AttachmentErrorCode,
    *,
    correlation_id: str | None = None,
    retry_after_seconds: int | None = None,
    **sensitive_detail: Any,
) -> AttachmentHttpResponse:
    contract = ATTACHMENT_ERROR_REGISTRY[code]
    headers: dict[str, str] = {}
    if retry_after_seconds is not None:
        if not contract.retryable or not 1 <= retry_after_seconds <= 120:
            raise ValueError("Retry-After is only valid and bounded for upload service outages")
        headers["Retry-After"] = str(retry_after_seconds)
    return AttachmentHttpResponse(
        status_code=contract.http_status,
        body=safe_attachment_error_body(
            code, correlation_id=correlation_id, **sensitive_detail
        ),
        headers=headers,
    )
