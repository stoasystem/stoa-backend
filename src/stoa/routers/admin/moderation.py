"""Admin moderation cases."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from starlette.responses import Response

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.deps import legacy_user
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.models.moderation import (
    ModerationCaseListResponse,
    ModerationCaseNoteRequest,
    ModerationCaseResponse,
    ModerationCaseUpdateRequest,
    ModerationReason,
    ModerationSeverity,
    ModerationStatus,
)
from stoa.services import moderation_service


router = APIRouter()


@router.get("/moderation/cases", response_model=ModerationCaseListResponse)
async def list_moderation_cases(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: Optional[str] = Query(default=None, max_length=2000),
    status: ModerationStatus | None = Query(default=None),
    severity: ModerationSeverity | None = Query(default=None),
    reason: ModerationReason | None = Query(default=None),
    reporter_role: Optional[str] = Query(default=None),
    assignee: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """One page of moderation cases, newest first, for internal operations."""
    page = moderation_service.list_cases(
        limit=limit,
        cursor=cursor,
        status=status.value if status else None,
        severity=severity.value if severity else None,
        reason=reason.value if reason else None,
        reporter_role=reporter_role,
        assignee=assignee,
        date_from=date_from,
        date_to=date_to,
    )
    return ModerationCaseListResponse(
        items=[ModerationCaseResponse.model_validate(item) for item in page.items],
        count=page.total,
        nextCursor=page.next_cursor,
    )


@router.get("/moderation/cases/{case_id}", response_model=ModerationCaseResponse)
async def get_moderation_case(
    case_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Open a moderation case with context and audit history."""
    return moderation_service.get_case(case_id)


@router.get(
    "/moderation/cases/{case_id}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        404: {"description": "The case has no image, or it was deleted"},
    },
)
async def get_moderation_case_image(
    case_id: str,
    actor: Actor = Depends(admin_operation),
    settings: Settings = Depends(config.settings),
):
    """The image moderation refused, for an `image_upload` case. Admins only."""
    data, media_type = moderation_service.read_case_image(
        case_id, s3=aws.client(Kind.S3), settings=settings
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/moderation/cases/{case_id}", response_model=ModerationCaseResponse)
async def update_moderation_case(
    case_id: str,
    body: ModerationCaseUpdateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Assign, transition, or resolve a moderation case."""
    return moderation_service.update_case(case_id, body, legacy_user(actor))


@router.post("/moderation/cases/{case_id}/notes", response_model=ModerationCaseResponse)
async def add_moderation_case_note(
    case_id: str,
    body: ModerationCaseNoteRequest,
    actor: Actor = Depends(admin_operation),
):
    """Append an internal moderation note."""
    return moderation_service.add_note(case_id, body, legacy_user(actor))
