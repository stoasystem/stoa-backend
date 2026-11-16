"""Admin support views of one account: verification state and parent account operations."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from stoa.config import Settings
from stoa import config
from stoa.db.repositories import user_repo
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services.account_errors import AccountErrorCode, AccountViolation
from stoa.services import (
    account_operations_service,
    account_verification_service,
)


router = APIRouter()


class AccountVerificationSupportResponse(BaseModel):
    userId: str
    email: str
    role: str
    emailVerificationStatus: str
    emailVerificationRequired: bool
    accountActivationStatus: str
    emailVerificationPolicy: str
    emailVerifiedAt: str | None = None
    emailVerificationRequestedAt: str | None = None
    emailVerificationLastResendAt: str | None = None
    emailVerificationResendCount: int = 0
    resendAllowed: bool = False
    supportRecoveryState: str
    supportAction: str
    parentBindingStatus: str | None = None


class AccountOperationsParentDetailResponse(BaseModel):
    parentId: str
    parent: dict[str, Any] = Field(default_factory=dict)
    billing: dict[str, Any] = Field(default_factory=dict)
    children: list[dict[str, Any]] = Field(default_factory=list)
    usage: list[dict[str, Any]] = Field(default_factory=list)
    supportState: dict[str, Any] = Field(default_factory=dict)


@router.get("/account-verification/{user_id}", response_model=AccountVerificationSupportResponse)
async def get_account_verification_support(
    user_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Return bounded email verification state for account support."""
    profile = user_repo.get_user(user_id)
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    return AccountVerificationSupportResponse(**account_verification_service.support_summary(profile))


@router.get(
    "/account-operations/parents/{parent_id}",
    response_model=AccountOperationsParentDetailResponse,
)
async def get_parent_account_operations(
    parent_id: str,
    day: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    settings: Settings = Depends(config.settings),
    actor: Actor = Depends(admin_operation),
):
    """Return support-grade parent account operations detail."""
    try:
        return account_operations_service.build_admin_parent_operations_detail(
            parent_id,
            settings=settings,
            day=day,
        )
    except ValueError as exc:
        if str(exc) == "parent_not_found":
            raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND) from exc
        raise
