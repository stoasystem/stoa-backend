"""Public upload and attachment contracts with opaque, owner-neutral identifiers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


OpaqueId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class _AttachmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class UploadPurpose(StrEnum):
    QUESTION_IMAGE = "question_image"
    CONVERSATION_ATTACHMENT = "conversation_attachment"


class UploadStatus(StrEnum):
    ISSUING = "issuing"
    PENDING_UPLOAD = "pending_upload"
    ASSEMBLING = "assembling"
    VALIDATING = "validating"
    VALIDATED = "validated"
    CONSUMING = "consuming"
    CONSUMED = "consumed"
    INVALID = "invalid"
    EXPIRED = "expired"


class AttachmentStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class SavedAttachmentDeleteStatus(StrEnum):
    DELETED = "deleted"
    RETRYABLE = "retryable"


class UploadIntentRequest(_AttachmentModel):
    purpose: UploadPurpose
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=200)
    size_bytes: int = Field(alias="sizeBytes", gt=0)


class UploadIntentResponse(_AttachmentModel):
    upload_id: OpaqueId = Field(alias="uploadId")
    expires_at: datetime = Field(alias="expiresAt")
    max_bytes: int = Field(alias="maxBytes", gt=0)
    chunk_bytes: int = Field(alias="chunkBytes", gt=0)
    accepted_types: list[str] = Field(alias="acceptedTypes", min_length=1)
    status: UploadStatus = UploadStatus.PENDING_UPLOAD


class AttachmentSummary(_AttachmentModel):
    attachment_id: OpaqueId = Field(alias="attachmentId")
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(alias="mediaType", min_length=1, max_length=200)
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    status: AttachmentStatus
    created_at: datetime = Field(alias="createdAt")


class SavedAttachmentDetail(AttachmentSummary):
    """Coordinate-free owner view of one durable saved attachment."""


class SavedAttachmentPage(_AttachmentModel):
    items: list[AttachmentSummary]
    continuation: OpaqueId | None = None


class SavedAttachmentDeleteResult(_AttachmentModel):
    attachment_id: OpaqueId = Field(alias="attachmentId")
    status: SavedAttachmentDeleteStatus


class UploadChunkResponse(_AttachmentModel):
    upload_id: OpaqueId = Field(alias="uploadId")
    part_number: int = Field(alias="partNumber", ge=1)
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    checksum_sha256: str = Field(alias="checksumSha256", pattern=r"^[0-9a-f]{64}$")
    status: str = Field(pattern=r"^accepted$")


class CompleteUploadRequest(_AttachmentModel):
    part_count: int = Field(alias="partCount", ge=1, le=10)


class CompleteUploadResponse(_AttachmentModel):
    upload_id: OpaqueId = Field(alias="uploadId")
    status: UploadStatus
    attachment: AttachmentSummary | None = None


class AttachmentReference(_AttachmentModel):
    """Reference either a validated transient upload or an active saved attachment."""

    upload_id: OpaqueId | None = Field(default=None, alias="uploadId")
    attachment_id: OpaqueId | None = Field(default=None, alias="attachmentId")

    @model_validator(mode="after")
    def exactly_one_reference(self) -> "AttachmentReference":
        if (self.upload_id is None) == (self.attachment_id is None):
            raise ValueError("exactly one opaque attachment reference is required")
        return self

    @property
    def identity(self) -> tuple[str, str]:
        if self.upload_id is not None:
            return ("upload", self.upload_id)
        return ("attachment", str(self.attachment_id))


def public_attachment_schema_fields(model: type[BaseModel]) -> set[str]:
    """Expose aliases for structural privacy checks without serializing an instance."""
    properties: dict[str, Any] = model.model_json_schema(by_alias=True).get("properties", {})
    return set(properties)
