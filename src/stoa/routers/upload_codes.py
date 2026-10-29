"""Phone upload codes (#146): minted on the computer, presented by the phone.

`conversation_router` is the signed-in student's side, under the conversation the
code is for. `router` is the phone's side and takes no session: the code, then the
upload token it is exchanged for, are the credential, and both travel in the body.
Its paths sit under their own prefix rather than `/files`, whose
`/{upload_id}/...` routes would otherwise answer them.
"""

from typing import Never

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from stoa.config import Settings, get_settings
from stoa.db.repositories import upload_code_repo
from stoa.deps import (
    get_actor,
    get_image_moderation_client,
    get_s3_client,
    get_s3_presign_client,
)
from stoa.models.upload_code import (
    UploadCodeCompleteRequest,
    UploadCodeCompleteResponse,
    UploadCodePartRequest,
    UploadCodePartResponse,
    UploadCodeRedeemRequest,
    UploadCodeRedeemResponse,
    UploadCodeResponse,
    UploadCodeStatusResponse,
)
from stoa.security.attachment_errors import (
    AttachmentDecisionError,
    AttachmentErrorCode,
    log_attachment_failure,
)
from stoa.security.authorization import AuthorizationAction, AuthorizedResource
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    STUDENT_SELF,
    authorized_conversation_dependency,
)
from stoa.security.route_inventory import explicit_route_classification
from stoa.services import rate_limit, upload_code_service


conversation_router = APIRouter()
router = APIRouter()


def _live_conversation(conversation_id: str):
    item = upload_code_repo.get_conversation(conversation_id)
    if item is None or item.get("status") == "deleted":
        return None
    return item


def _raise_safe(error: AttachmentDecisionError, correlation_id: str, settings: Settings) -> Never:
    error.correlation_id = correlation_id
    log_attachment_failure(error, route="upload_codes")
    headers = {"X-Correlation-ID": correlation_id}
    if error.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE:
        headers["Retry-After"] = "30"
    if error.code is AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED:
        headers["Retry-After"] = str(settings.upload_code_window_seconds)
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers=headers,
    ) from error


def _source_digest(request: Request) -> str:
    try:
        return rate_limit.client_source_digest(request)
    except rate_limit.ProxyTopologyError:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_CODE_RATE_LIMITED) from None


@conversation_router.post("/{conv_id}/upload-codes", response_model=UploadCodeResponse)
async def issue_upload_code(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.RESPOND,
            purposes=STUDENT_SELF,
            resolver=_live_conversation,
        )
    ),
    actor: Actor = Depends(get_actor),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """A one-time code a phone can put one image into this conversation with.

    The code is in this response only. It is spent by the first redemption and
    refused from ten minutes on, or once the account enters deletion.
    """
    try:
        return upload_code_service.issue_code(
            authorized.ref.resource_id, actor, settings=settings
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)


@conversation_router.get(
    "/{conv_id}/upload-codes/{code_id}", response_model=UploadCodeStatusResponse
)
async def read_upload_code(
    code_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=STUDENT_SELF,
            resolver=_live_conversation,
        )
    ),
    actor: Actor = Depends(get_actor),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Where the phone has got to; `uploadId` to attach once the image has passed."""
    try:
        return upload_code_service.code_status(
            authorized.ref.resource_id, code_id, actor
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)


@conversation_router.get("/{conv_id}/upload-codes/{code_id}/content")
async def preview_upload_code_photo(
    code_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=STUDENT_SELF,
            resolver=_live_conversation,
        )
    ),
    actor: Actor = Depends(get_actor),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """The photo the phone put in, once it has passed, for the student to confirm.

    Whoever scans the QR first holds the code, so the computer shows this photo
    and lets the student choose to send it; it never attaches a ready upload alone.
    """
    try:
        prepared = upload_code_service.preview_upload(
            authorized.ref.resource_id, code_id, actor, s3=s3, settings=settings
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)
    return StreamingResponse(
        prepared.iter_bytes(),
        media_type=prepared.media_type,
        headers={
            **prepared.public_headers(),
            "X-Correlation-ID": correlation_id,
        },
    )


@router.post("/redeem", response_model=UploadCodeRedeemResponse)
@explicit_route_classification(
    "public",
    "phone upload: the one-time code in the body is the credential (#146)",
)
async def redeem_upload_code(
    body: UploadCodeRedeemRequest,
    request: Request,
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Spend a code on one image upload into the conversation it was made in."""
    try:
        return upload_code_service.redeem_code(
            body, source_digest=_source_digest(request), s3=s3, settings=settings
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)


@router.post("/parts/{part_number}", response_model=UploadCodePartResponse)
@explicit_route_classification(
    "public",
    "phone upload: the upload token in the body is the credential (#146)",
)
async def sign_upload_code_part(
    part_number: int,
    body: UploadCodePartRequest,
    request: Request,
    signer=Depends(get_s3_presign_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Sign the URL the phone puts one part on, straight to S3 (ADR-004)."""
    try:
        return upload_code_service.sign_part(
            part_number,
            body,
            source_digest=_source_digest(request),
            signer=signer,
            settings=settings,
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)


@router.post("/complete", response_model=UploadCodeCompleteResponse)
@explicit_route_classification(
    "public",
    "phone upload: the upload token in the body is the credential (#146)",
)
async def complete_upload_code(
    body: UploadCodeCompleteRequest,
    request: Request,
    s3=Depends(get_s3_client),
    moderation=Depends(get_image_moderation_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Finish the upload; the image is moderated before it counts (#138)."""
    try:
        return upload_code_service.complete(
            body,
            source_digest=_source_digest(request),
            s3=s3,
            settings=settings,
            moderation=moderation,
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id, settings)
