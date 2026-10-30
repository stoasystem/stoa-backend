"""Closed, redacted attachment failure and client-recovery contract."""

from __future__ import annotations

import logging
import sys
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class AttachmentErrorCode(StrEnum):
    ATTACHMENT_IN_USE = "attachment_in_use"
    UPLOAD_NOT_FOUND = "upload_not_found"
    UPLOAD_EXPIRED = "upload_expired"
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_TYPE_NOT_SUPPORTED = "upload_type_not_supported"
    UPLOAD_CONTENT_MISMATCH = "upload_content_mismatch"
    UPLOAD_INVALID = "upload_invalid"
    UPLOAD_CONTENT_BLOCKED = "upload_content_blocked"
    UPLOAD_CHUNK_CONFLICT = "upload_chunk_conflict"
    STORAGE_QUOTA_EXCEEDED = "storage_quota_exceeded"
    UPLOAD_SERVICE_UNAVAILABLE = "upload_service_unavailable"
    UPLOAD_CODE_INVALID = "upload_code_invalid"
    UPLOAD_CODE_RATE_LIMITED = "upload_code_rate_limited"
    MESSAGE_IDEMPOTENCY_CONFLICT = "message_idempotency_conflict"
    MESSAGE_IN_PROGRESS = "message_in_progress"
    MESSAGE_DAILY_LIMIT = "message_daily_limit"
    MESSAGE_FAILED = "message_failed"
    MESSAGE_COMMAND_EXPIRED = "message_command_expired"
    MESSAGE_COMMAND_NOT_FOUND = "message_command_not_found"


class AttachmentClientAction(StrEnum):
    REMOVE_FROM_RESOURCE = "remove_from_resource"
    SELECT_FILE = "select_file"
    REDUCE_SIZE = "reduce_size"
    DELETE_OR_UPGRADE = "delete_or_upgrade"
    RETRY_LATER = "retry_later"
    NEW_UPLOAD_CODE = "new_upload_code"


@dataclass(frozen=True, slots=True)
class AttachmentErrorContract:
    http_status: int
    safe_message: str
    client_action: AttachmentClientAction
    retryable: bool = False
    idempotent_only: bool = False
    max_attempts: int = 0


ATTACHMENT_ERROR_REGISTRY: dict[AttachmentErrorCode, AttachmentErrorContract] = {
    AttachmentErrorCode.ATTACHMENT_IN_USE: AttachmentErrorContract(
        409,
        "Remove this attachment from its conversation or question first.",
        AttachmentClientAction.REMOVE_FROM_RESOURCE,
    ),
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
    # Image moderation refused it (#138). There is no appeal; the client shows
    # its own copy for this code and offers another image or plain text.
    AttachmentErrorCode.UPLOAD_CONTENT_BLOCKED: AttachmentErrorContract(
        422,
        "This image cannot be sent. Choose another image or describe the problem in words.",
        AttachmentClientAction.SELECT_FILE,
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
    # A phone upload code that is wrong, used, expired, or whose account is in
    # deletion (#146). One answer for all of them, so a refusal tells a guesser
    # nothing; the phone page asks for a fresh code from the computer.
    AttachmentErrorCode.UPLOAD_CODE_INVALID: AttachmentErrorContract(
        404,
        "This code is no longer valid. Show a new code on your computer.",
        AttachmentClientAction.NEW_UPLOAD_CODE,
    ),
    AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED: AttachmentErrorContract(
        429,
        "Too many attempts. Try again later.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT: AttachmentErrorContract(
        409,
        "This message key was already used for a different request.",
        AttachmentClientAction.SELECT_FILE,
    ),
    AttachmentErrorCode.MESSAGE_IN_PROGRESS: AttachmentErrorContract(
        409,
        "This message is still being processed. Try again shortly.",
        AttachmentClientAction.RETRY_LATER,
        retryable=True,
        idempotent_only=True,
        max_attempts=20,
    ),
    AttachmentErrorCode.MESSAGE_DAILY_LIMIT: AttachmentErrorContract(
        429,
        "Your daily message limit is reached. Try again tomorrow.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AttachmentErrorCode.MESSAGE_FAILED: AttachmentErrorContract(
        409,
        "This message could not be completed. Send it again.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AttachmentErrorCode.MESSAGE_COMMAND_EXPIRED: AttachmentErrorContract(
        409,
        "This message request expired. Send it again.",
        AttachmentClientAction.RETRY_LATER,
    ),
    AttachmentErrorCode.MESSAGE_COMMAND_NOT_FOUND: AttachmentErrorContract(
        409,
        "This message request is unavailable. Send it again.",
        AttachmentClientAction.RETRY_LATER,
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


def in_flight_cause() -> str | None:
    """Name the exception being handled, without repeating what it says.

    A provider error's message carries account coordinates, so only its own
    `Error.Code` is taken; anything else is named by class alone. Returns None
    outside an `except` block, where there is nothing to name.
    """
    cause = sys.exception()
    if cause is None:
        return None
    response = getattr(cause, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping) and error.get("Code"):
            return f"{type(cause).__name__}:{error['Code']}"
    return type(cause).__name__


@dataclass(slots=True)
class AttachmentDecisionError(Exception):
    code: AttachmentErrorCode
    internal_detail: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        # Most of the subsystem's blanket handlers raise this `from None`, which
        # leaves an operator the decision but not the cause. The cause is still
        # in flight here, and card 127's second fault needed two deploys to
        # reach because each handler had to be taught to say so by itself.
        if self.internal_detail is None:
            self.internal_detail = in_flight_cause()

    @property
    def status_code(self) -> int:
        return ATTACHMENT_ERROR_REGISTRY[self.code].http_status

    def public_body(self) -> dict[str, str]:
        return safe_attachment_error_body(self.code, correlation_id=self.correlation_id)


def log_attachment_failure(error: AttachmentDecisionError, route: str) -> None:
    """Record where a redacted failure came from, at the one boundary it leaves by.

    The student is told only "temporarily unavailable", and the subsystem drops
    its tracebacks with `from None` on the way here, but this exception's own
    traceback still names the line that decided. Without it a 503 from a
    provider outage, a contract violation and a scan running out of pages are
    the same event to an operator - which is how card 127 came to be diagnosed
    by probing the live API from outside instead of by reading a log.

    Only frames are recorded: file, line and function, never a value.
    """
    frames = traceback.extract_tb(error.__traceback__)
    where = " < ".join(
        f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
        for frame in reversed(frames[-4:])
    )
    contract = ATTACHMENT_ERROR_REGISTRY[error.code]
    log = logger.error if contract.http_status >= 500 else logger.info
    log(
        "attachment_failure code=%s status=%s route=%s correlation_id=%s detail=%s raised_at=%s",
        error.code.value,
        contract.http_status,
        route,
        error.correlation_id or "-",
        error.internal_detail or "-",
        where or "unknown",
    )


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
