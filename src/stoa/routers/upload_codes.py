"""Phone upload codes (#146): minted on the computer, presented by the phone.

`conversation_router` is the signed-in student's side, under the conversation the
code is for. `student_router` makes a code for no conversation yet (#191), for a
question not asked yet, and `files_router` follows it by the upload it reserved,
under that upload's own authorization. `router` is the phone's side and takes no
session: the code, then the
upload token it is exchanged for, are the credential, and both travel in the body.
Its paths sit under their own prefix rather than `/files`, whose
`/{upload_id}/...` routes would otherwise answer them.
"""


from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from stoa.config import Settings, get_settings
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
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    STUDENT_SELF,
    authorized_conversation_dependency,
)
from stoa.security.route_inventory import explicit_route_classification
from stoa.services import learning_session, rate_limit, upload_code_service


conversation_router = APIRouter()
student_router = APIRouter()
files_router = APIRouter()
router = APIRouter()


def _live_conversation(conversation_id: str):
    item = learning_session.read(conversation_id)
    if item is None or item.get("status") == "deleted":
        return None
    return item


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
    return upload_code_service.issue_code(
        authorized.ref.resource_id, actor, settings=settings
    )


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
    return upload_code_service.code_status(
        authorized.ref.resource_id, code_id, actor
    )


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
    prepared = upload_code_service.preview_upload(
        authorized.ref.resource_id, code_id, actor, s3=s3, settings=settings
    )
    return StreamingResponse(
        prepared.iter_bytes(),
        media_type=prepared.media_type,
        headers={
            **prepared.public_headers(),
            "X-Correlation-ID": correlation_id,
        },
    )


@student_router.post("", response_model=UploadCodeResponse)
@explicit_route_classification(
    "authenticated-global",
    "a student's own phone upload code for a question not asked yet (#191)",
)
async def issue_unbound_upload_code(
    actor: Actor = Depends(get_actor),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """A one-time code a phone can put one image in with, before there is a conversation.

    The upload it will open is reserved here (`uploadId`); the photo goes with
    whichever question the student sends it with, like a file chosen on the computer.
    """
    return upload_code_service.issue_code(None, actor, settings=settings)


async def _reserved_upload_resolver(upload_id: str):
    return {"student_id": upload_id}


async def _reserved_upload_actor(actor: Actor = Depends(get_actor)) -> Actor:
    return actor


# The upload is the student's own: `upload_code_service` reads the code it was
# reserved for and refuses one that is not theirs, as `/files` does for uploads.
_reserved_upload_actor.authorization_specs = (  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.UPLOAD,
        AuthorizationAction.READ,
        AuthorizationPurpose.SELF_SERVICE,
        _reserved_upload_resolver,
    ),
)


@files_router.get("/{upload_id}/phone-code", response_model=UploadCodeStatusResponse)
async def read_unbound_upload_code(
    upload_id: str,
    actor: Actor = Depends(_reserved_upload_actor),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Where the phone has got with a code made for no conversation, by its upload."""
    return upload_code_service.unbound_code_status(upload_id, actor)


@files_router.get("/{upload_id}/phone-code/content")
async def preview_unbound_upload_code_photo(
    upload_id: str,
    actor: Actor = Depends(_reserved_upload_actor),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """The photo the phone put in, once it has passed, for the student to confirm."""
    prepared = upload_code_service.preview_unbound_upload(
        upload_id, actor, s3=s3, settings=settings
    )
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
    return upload_code_service.redeem_code(
        body, source_digest=_source_digest(request), s3=s3, settings=settings
    )


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
    return upload_code_service.sign_part(
        part_number,
        body,
        source_digest=_source_digest(request),
        signer=signer,
        settings=settings,
    )


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
    return upload_code_service.complete(
        body,
        source_digest=_source_digest(request),
        s3=s3,
        settings=settings,
        moderation=moderation,
    )
