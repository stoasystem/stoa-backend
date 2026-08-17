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
from stoa.services import public_identity_service, teacher_application_service
from stoa.services.teacher_identity_provider import CognitoTeacherIdentityProvider


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


class TeacherReissueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class TeacherActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=32, max_length=512)


class TeacherActivationClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=12, max_length=256)


@lru_cache(maxsize=1)
def get_teacher_identity_provider(settings: Settings = Depends(get_settings)) -> Any:
    return boto3.client("cognito-idp", region_name=settings.aws_region)


def get_teacher_account_provider(
    settings: Settings = Depends(get_settings),
) -> Any:
    return CognitoTeacherIdentityProvider(
        boto3.client("cognito-idp", region_name=settings.aws_region),
        user_pool_id=settings.cognito_user_pool_id,
    )


@router.post("")
@explicit_route_classification(
    "public",
    "idempotent teacher candidacy submission only",
    allowed_identifiers=("application_id",),
    identifier_scope="command-local",
)
def apply(payload: TeacherApplicationRequest) -> dict[str, Any]:
    return teacher_application_service.submit_application(payload.model_dump(exclude_none=True))


@router.get("")
def pending_applications(
    review_state: str = "pending_review",
    limit: int = 50,
    user: dict[str, Any] = Depends(
        teacher_application_reviewer_dependency(AuthorizationAction.READ)
    ),
) -> dict[str, Any]:
    return teacher_application_service.applications_for_reviewer(
        user, review_state=review_state, limit=limit
    )


@router.get("/{application_id}/status")
@explicit_route_classification(
    "public",
    "decision-free progress for the holder of the opaque application id",
    allowed_identifiers=("application_id",),
    identifier_scope="command-local",
)
def application_status(application_id: str) -> dict[str, Any]:
    return teacher_application_service.application_status(application_id)


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


@router.post("/{application_id}/invitations")
def reissue(
    application_id: str,
    payload: TeacherReissueRequest,
    user: dict[str, Any] = Depends(
        teacher_application_reviewer_dependency(AuthorizationAction.UPDATE)
    ),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return teacher_application_service.reissue_invitation(
        actor=user,
        application_id=application_id,
        version=payload.version,
        invitation_expiry_seconds=settings.teacher_activation_invitation_expiry_seconds,
    )


@router.post("/activation/claim")
@explicit_route_classification(
    "public", "invitation-gated teacher account creation and activation"
)
def claim(
    payload: TeacherActivationClaimRequest,
    settings: Settings = Depends(get_settings),
    provider: Any = Depends(get_teacher_account_provider),
) -> dict[str, Any]:
    issuer = public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)
    return teacher_application_service.claim_and_activate(
        token=payload.invitation_token,
        password=payload.password,
        issuer=issuer,
        provider=provider,
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
