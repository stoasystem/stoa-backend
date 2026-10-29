"""Phone upload code contracts (#146).

The computer mints a code for one learning conversation and shows it as a QR code;
the phone that scans it is not signed in and presents the code instead. Both the
code and the upload token it is exchanged for are bearer secrets: they arrive in a
request body, never a path or query (API Gateway logs paths), and are typed
`SecretStr` so nothing that prints a request model prints them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, SecretStr

from stoa.models.attachment import OpaqueId, _AttachmentModel


class UploadCodeStatus(StrEnum):
    WAITING = "waiting"
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class UploadCodeResponse(_AttachmentModel):
    """A fresh code. `code` is shown once, here, and stored only as a hash."""

    code_id: OpaqueId = Field(alias="codeId")
    code: str = Field(min_length=1)
    expires_at: datetime = Field(alias="expiresAt")


class UploadCodeStatusResponse(_AttachmentModel):
    """Where the phone has got to. `uploadId` appears once the image has passed."""

    code_id: OpaqueId = Field(alias="codeId")
    status: UploadCodeStatus
    expires_at: datetime = Field(alias="expiresAt")
    upload_id: OpaqueId | None = Field(default=None, alias="uploadId")


class UploadCodeRedeemRequest(_AttachmentModel):
    code: SecretStr = Field(max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=200)
    size_bytes: int = Field(alias="sizeBytes", gt=0)


class UploadCodeRedeemResponse(_AttachmentModel):
    """The token the phone presents for the rest of this one upload."""

    upload_token: str = Field(alias="uploadToken", min_length=1)
    expires_at: datetime = Field(alias="expiresAt")
    max_bytes: int = Field(alias="maxBytes", gt=0)
    chunk_bytes: int = Field(alias="chunkBytes", gt=0)
    accepted_types: list[str] = Field(alias="acceptedTypes", min_length=1)


class UploadCodePartRequest(_AttachmentModel):
    upload_token: SecretStr = Field(alias="uploadToken", max_length=200)
    size_bytes: int = Field(alias="sizeBytes", gt=0)
    checksum_sha256: str = Field(alias="checksumSha256", pattern=r"^[0-9a-f]{64}$")


class UploadCodePartResponse(_AttachmentModel):
    """Where the phone puts one part's bytes, straight to S3 (ADR-004)."""

    part_number: int = Field(alias="partNumber", ge=1)
    url: str = Field(min_length=1)
    method: str = Field(pattern=r"^PUT$")
    headers: dict[str, str]
    expires_at: datetime = Field(alias="expiresAt")


class UploadCodeCompleteRequest(_AttachmentModel):
    upload_token: SecretStr = Field(alias="uploadToken", max_length=200)
    part_count: int = Field(alias="partCount", ge=1, le=10)


class UploadCodeCompleteResponse(_AttachmentModel):
    status: str = Field(pattern=r"^validated$")
