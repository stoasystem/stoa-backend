"""Opaque, owner-bound file upload and saved attachment routes."""


from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.deps import get_actor
from stoa.models.attachment import (
    CompleteUploadRequest,
    CompleteUploadResponse,
    SavedAttachmentDeleteResult,
    SavedAttachmentDetail,
    SavedAttachmentPage,
    UploadIntentRequest,
    UploadIntentResponse,
    UploadPartUrlRequest,
    UploadPartUrlResponse,
)
from stoa.security.attachment_errors import (
    AttachmentDecisionError,
    AttachmentErrorCode,
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.declared_authorization import (
    DELETABLE,
    authorized,
    path,
    service_enforced,
)
from stoa.security.identity import Actor, CanonicalRole
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_inventory import explicit_route_classification
from stoa.services import uploads
from stoa.services.attachment_service import (
    delete_saved_attachment,
    list_owned_attachments,
    prepare_saved_attachment_download,
    saved_attachment_detail,
)


router = APIRouter()


# Whose an upload is, and whether an intent may name its learning session
# (#139), is checked by the upload service itself, against the Actor it is
# handed: these routes say so instead of claiming a check here.
_OWN = {role: AuthorizationPurpose.SELF_SERVICE for role in CanonicalRole}
_upload_intent_actor = service_enforced(
    "uploads.start", ResourceType.CONVERSATION, AuthorizationAction.UPDATE, _OWN
)
_upload_part_actor = service_enforced(
    "uploads.sign_part", ResourceType.UPLOAD, AuthorizationAction.UPDATE, _OWN
)
_upload_complete_actor = service_enforced(
    "uploads.complete", ResourceType.UPLOAD, AuthorizationAction.UPDATE, _OWN
)


def _upload_not_found() -> AttachmentDecisionError:
    return AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)


def _owned_attachment(action: AuthorizationAction, kind: str | None = None):
    """The Actor's own live attachment; one that is not there is `upload_not_found`."""
    return authorized(
        ResourceType.ATTACHMENT,
        action,
        path("attachment_id"),
        _OWN,
        kind=kind,
        not_found=_upload_not_found,
    )


_attachment_read = _owned_attachment(AuthorizationAction.READ)
_attachment_delete = _owned_attachment(AuthorizationAction.DELETE, DELETABLE)


@router.get("/attachments", response_model=SavedAttachmentPage)
@explicit_route_classification(
    "authenticated-global", "Actor-owned saved attachment collection"
)
async def list_saved_attachments(
    continuation: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
):
    return list_owned_attachments(
        actor, limit=limit, continuation=continuation
    )


@router.get("/attachments/{attachment_id}", response_model=SavedAttachmentDetail)
async def get_saved_attachment(
    loaded: AuthorizedResource = Depends(_attachment_read),
):
    return saved_attachment_detail(dict(loaded.value))


@router.get("/attachments/{attachment_id}/content")
async def download_saved_attachment(
    loaded: AuthorizedResource = Depends(_attachment_read),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    prepared = prepare_saved_attachment_download(
        dict(loaded.value), s3=aws.client(Kind.S3), settings=settings
    )
    return StreamingResponse(
        prepared.iter_bytes(),
        media_type=prepared.media_type,
        headers={
            **prepared.public_headers(),
            "X-Correlation-ID": correlation_id,
        },
    )


@router.delete(
    "/attachments/{attachment_id}", response_model=SavedAttachmentDeleteResult
)
async def remove_saved_attachment(
    loaded: AuthorizedResource = Depends(_attachment_delete),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    return delete_saved_attachment(
        dict(loaded.value), s3=aws.client(Kind.S3), settings=settings
    )


@router.post("/intents", response_model=UploadIntentResponse)
async def create_owned_upload_intent(
    body: UploadIntentRequest,
    actor: Actor = Depends(_upload_intent_actor),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    return uploads.start(body, actor, s3=aws.client(Kind.S3), settings=settings)


@router.post("/{upload_id}/parts/{part_number}", response_model=UploadPartUrlResponse)
async def sign_owned_upload_part(
    upload_id: str,
    part_number: int,
    body: UploadPartUrlRequest,
    actor: Actor = Depends(_upload_part_actor),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Sign a URL the browser puts one part on, straight to S3 (ADR-004, #136)."""
    return uploads.sign_part(
        upload_id,
        part_number,
        body,
        actor,
        signer=aws.client(Kind.S3_PRESIGN),
        settings=settings,
    )


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_owned_upload(
    upload_id: str,
    body: CompleteUploadRequest,
    actor: Actor = Depends(_upload_complete_actor),
    settings: Settings = Depends(config.settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    return uploads.complete(
        upload_id,
        body.part_count,
        actor,
        s3=aws.client(Kind.S3),
        settings=settings,
        moderation=aws.client(Kind.REKOGNITION_MODERATION),
    )
