"""Opaque, owner-bound file upload and saved attachment routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from stoa.config import Settings, get_settings
from stoa.db.repositories import attachment_repo
from stoa.deps import get_actor, get_authorization_audit_sink, get_s3_client
from stoa.models.attachment import (
    CompleteUploadRequest,
    CompleteUploadResponse,
    SavedAttachmentDeleteResult,
    SavedAttachmentDetail,
    SavedAttachmentPage,
    UploadChunkResponse,
    UploadIntentRequest,
    UploadIntentResponse,
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
    CurrentAuthorizationFactRepository,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_inventory import explicit_route_classification
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services.attachment_service import (
    complete_upload,
    create_upload_intent,
    delete_saved_attachment,
    list_owned_attachments,
    prepare_saved_attachment_download,
    put_upload_chunk,
    saved_attachment_detail,
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
    headers = {"X-Correlation-ID": correlation_id}
    if error.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE:
        headers["Retry-After"] = "30"
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers=headers,
    ) from error


def _raise_security(error: SecurityDecisionError) -> None:
    headers = {"X-Correlation-ID": error.correlation_id} if error.correlation_id else None
    if error.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE:
        headers = {**(headers or {}), "Retry-After": "30"}
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers=headers,
    ) from error


def _owned_attachment_dependency(action: AuthorizationAction):
    async def resolve(attachment_id: str):
        item = attachment_repo.get_attachment(attachment_id)
        if not isinstance(item, dict) or item.get("status") != "active":
            return None
        owner_id = item.get("owner_id")
        if not isinstance(owner_id, str) or not owner_id:
            return None
        return AuthorizedResource(
            ResourceRef(
                ResourceType.ATTACHMENT,
                attachment_id,
                owner_id,
                owner_id=owner_id,
            ),
            item,
        )

    async def dependency(
        attachment_id: str,
        actor: Actor = Depends(get_actor),
        facts: CurrentAuthorizationFactRepository = Depends(
            get_authorization_fact_repository
        ),
        correlation_id: str = Depends(get_request_correlation_id),
        audit_sink=Depends(get_authorization_audit_sink),
    ) -> AuthorizedResource:
        try:
            return await authorize_and_resolve(
                actor=actor,
                resource_id=attachment_id,
                spec=AuthorizationSpec(
                    ResourceType.ATTACHMENT,
                    action,
                    AuthorizationPurpose.SELF_SERVICE,
                    resolve,
                ),
                fact_repository=facts,
                correlation_id=correlation_id,
                audit_sink=audit_sink,
            )
        except SecurityDecisionError as error:
            if error.code is SecurityErrorCode.RESOURCE_NOT_FOUND:
                _raise_safe(
                    AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND),
                    correlation_id,
                )
            _raise_security(error)

    dependency.authorization_specs = (  # type: ignore[attr-defined]
        AuthorizationSpec(
            ResourceType.ATTACHMENT,
            action,
            AuthorizationPurpose.SELF_SERVICE,
            resolve,
        ),
    )
    return dependency


_attachment_read = _owned_attachment_dependency(AuthorizationAction.READ)
_attachment_delete = _owned_attachment_dependency(AuthorizationAction.DELETE)


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
    try:
        return list_owned_attachments(
            actor, limit=limit, continuation=continuation
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)


@router.get("/attachments/{attachment_id}", response_model=SavedAttachmentDetail)
async def get_saved_attachment(
    loaded: AuthorizedResource = Depends(_attachment_read),
):
    return saved_attachment_detail(dict(loaded.value))


@router.get("/attachments/{attachment_id}/content")
async def download_saved_attachment(
    loaded: AuthorizedResource = Depends(_attachment_read),
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        prepared = prepare_saved_attachment_download(
            dict(loaded.value), s3=s3, settings=settings
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)
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
    s3=Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    try:
        return delete_saved_attachment(
            dict(loaded.value), s3=s3, settings=settings
        )
    except AttachmentDecisionError as error:
        _raise_safe(error, correlation_id)


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
