"""Public non-privileged teacher candidacy and guarded lifecycle endpoints."""

from functools import lru_cache
from typing import Any

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from stoa.config import Settings, get_settings
from stoa.deps import get_verified_token
from stoa.security.authorization import AuthorizationAction
from stoa.security.route_authorization import teacher_application_reviewer_dependency
from stoa.security.route_inventory import explicit_route_classification
from stoa.security.tokens import VerifiedAccessToken
from stoa.services import teacher_application_service


router = APIRouter()


class TeacherApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: str | None = None
    email: str
    email_verified: bool
    full_name: str = Field(min_length=1, max_length=120)
    subjects: list[str] = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=1, max_length=2000)


class TeacherReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    decision: str
    reason: str = Field(min_length=1, max_length=1000)


class TeacherActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=32, max_length=512)


@lru_cache(maxsize=1)
def get_teacher_identity_provider(settings: Settings = Depends(get_settings)) -> Any:
    return boto3.client("cognito-idp", region_name=settings.aws_region)


@router.post("")
@explicit_route_classification(
    "public",
    "idempotent teacher candidacy submission only",
    allowed_identifiers=("application_id",),
    identifier_scope="command-local",
)
def apply(payload: TeacherApplicationRequest) -> dict[str, Any]:
    return teacher_application_service.submit_application(payload.model_dump(exclude_none=True))


@router.get("/{application_id}/versions/{version}")
def full_application(
    application_id: str,
    version: int,
    user: dict[str, Any] = Depends(
        teacher_application_reviewer_dependency(AuthorizationAction.READ)
    ),
) -> dict[str, Any]:
    return teacher_application_service.full_application_for_reviewer(user, application_id, version)


@router.post("/{application_id}/reviews")
def review(
    application_id: str,
    payload: TeacherReviewRequest,
    user: dict[str, Any] = Depends(
        teacher_application_reviewer_dependency(AuthorizationAction.UPDATE)
    ),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return teacher_application_service.review_application(
        actor=user,
        application_id=application_id,
        version=payload.version,
        decision=payload.decision,
        reason=payload.reason,
        invitation_expiry_seconds=settings.teacher_activation_invitation_expiry_seconds,
    )


@router.post("/activation/consume")
@explicit_route_classification("public", "verified invitation activation command")
def activate(
    payload: TeacherActivationRequest,
    verified: VerifiedAccessToken = Depends(get_verified_token),
    provider: Any = Depends(get_teacher_identity_provider),
) -> dict[str, Any]:
    if not verified.verified_email:
        raise HTTPException(status_code=409, detail={"code": "verified_email_required"})
    return teacher_application_service.activate_from_invitation(
        token=payload.invitation_token,
        verified_email=verified.verified_email,
        issuer=verified.issuer,
        subject=verified.subject,
        provider=provider,
    )
