"""File routes — S3 presigned PUT URL for direct client uploads."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user, get_s3_client

router = APIRouter()

_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "heic"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class PresignRequest(BaseModel):
    filename: str
    content_type: str

    @field_validator("filename")
    @classmethod
    def validate_extension(cls, v: str) -> str:
        ext = v.rsplit(".", 1)[-1].lower() if "." in v else ""
        if ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"Extension '.{ext}' is not allowed; use: {_ALLOWED_EXTENSIONS}")
        return v

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        if not v.startswith("image/"):
            raise ValueError("Only image/* content types are permitted")
        return v


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


@router.post("/presign", response_model=PresignResponse)
async def get_presigned_url(
    body: PresignRequest,
    user: dict = Depends(get_current_user),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
):
    """Return an S3 presigned PUT URL so the client can upload directly."""
    user_id = user.get("sub", "unknown")
    ext = body.filename.rsplit(".", 1)[-1].lower()
    key = f"uploads/{user_id}/{uuid.uuid4()}.{ext}"

    try:
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_images_bucket,
                "Key": key,
                "ContentType": body.content_type,
            },
            ExpiresIn=settings.s3_presign_expiry_seconds,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate presigned URL: {exc}")

    return PresignResponse(
        upload_url=url,
        s3_key=key,
        expires_in=settings.s3_presign_expiry_seconds,
    )
