"""Opaque, owner-bound file upload routes."""

from fastapi import APIRouter, Depends, HTTPException

from stoa.config import Settings, get_settings
from stoa.deps import get_actor, get_s3_client
from stoa.models.attachment import (
    FinalizeUploadResponse,
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
from stoa.services.attachment_service import create_upload_intent, finalize_upload


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


@router.post("/presign", response_model=UploadIntentResponse)
@explicit_route_classification("authenticated-global", "Actor-owned generated upload intent")
async def presign_upload(
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


@router.post("/{upload_id}/finalize", response_model=FinalizeUploadResponse)
async def finalize_owned_upload(
    upload_id: str,
    actor: Actor = Depends(_upload_actor_dependency),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        return finalize_upload(upload_id, actor, s3=s3, settings=settings)
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)
