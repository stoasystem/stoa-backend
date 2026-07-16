"""Opaque, owner-bound file upload routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from stoa.config import Settings, get_settings
from stoa.deps import get_actor, get_s3_client
from stoa.models.attachment import (
    CompleteUploadRequest,
    CompleteUploadResponse,
    UploadChunkResponse,
    UploadIntentRequest,
    UploadIntentResponse,
)
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_inventory import explicit_route_classification
from stoa.services.attachment_service import (
    complete_upload,
    create_upload_intent,
    put_upload_chunk,
)


router = APIRouter()


async def _upload_inventory_resolver(upload_id: str):
    return {"student_id": upload_id}


async def _upload_actor_dependency(actor: Actor = Depends(get_actor)) -> Actor:
    return actor


_upload_actor_dependency.authorization_specs = (  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.UPLOAD,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _upload_inventory_resolver,
    ),
)


def _raise_safe(error: AttachmentDecisionError, correlation_id: str) -> None:
    error.correlation_id = correlation_id
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers={"X-Correlation-ID": correlation_id},
    ) from error


@router.post("/intents", response_model=UploadIntentResponse)
@explicit_route_classification("authenticated-global", "Actor-owned generated upload intent")
async def create_owned_upload_intent(
    body: UploadIntentRequest,
    actor: Actor = Depends(get_actor),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        return create_upload_intent(body, actor, s3=s3, settings=settings)
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)


@router.put("/{upload_id}/chunks/{part_number}", response_model=UploadChunkResponse)
async def upload_owned_chunk(
    upload_id: str,
    part_number: int,
    request: Request,
    actor: Actor = Depends(_upload_actor_dependency),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        return await put_upload_chunk(
            upload_id,
            part_number,
            request.stream(),
            actor,
            s3=s3,
            settings=settings,
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_owned_upload(
    upload_id: str,
    body: CompleteUploadRequest,
    actor: Actor = Depends(_upload_actor_dependency),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        return complete_upload(
            upload_id,
            body.part_count,
            actor,
            s3=s3,
            settings=settings,
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)
