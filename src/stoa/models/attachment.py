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
    # A teacher's image for their reply to a help request (#145); the one
    # purpose a teacher may open an upload for.
    HELP_REPLY_IMAGE = "help_reply_image"


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


class UploadPartUrlRequest(_AttachmentModel):
    """The one part a URL is signed for: its exact length and SHA-256 (hex)."""

    size_bytes: int = Field(alias="sizeBytes", gt=0)
    checksum_sha256: str = Field(alias="checksumSha256", pattern=r"^[0-9a-f]{64}$")


class UploadPartUrlResponse(_AttachmentModel):
    """Where the browser puts one part's bytes, and the headers it must send.

    S3 refuses a body whose length or SHA-256 differs from what the URL was signed
    for. The URL names the images bucket and the upload's staging object: ADR-004
    puts the bytes on S3 directly, since Lambda cannot take a part's request (#136).
    """

    upload_id: OpaqueId = Field(alias="uploadId")
    part_number: int = Field(alias="partNumber", ge=1)
    url: str = Field(min_length=1)
    method: str = Field(pattern=r"^PUT$")
    headers: dict[str, str]
    expires_at: datetime = Field(alias="expiresAt")


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


class ReplyImageReference(_AttachmentModel):
    """A validated `help_reply_image` upload of the replying teacher (#145)."""

    upload_id: OpaqueId = Field(alias="uploadId")


def public_attachment_schema_fields(model: type[BaseModel]) -> set[str]:
    """Expose aliases for structural privacy checks without serializing an instance."""
    properties: dict[str, Any] = model.model_json_schema(by_alias=True).get("properties", {})
    return set(properties)
