"""Admin privileged identities: administrator provisioning and capability grants."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services import privileged_identity_service


router = APIRouter()


class AdminProvisionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    target_email: str
    issuer: str
    subject: str
    reason: str = Field(min_length=1, max_length=1000)


class AdminStatusCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    operation: str
    provider_username: str
    reason: str = Field(min_length=1, max_length=1000)


class CapabilityGrantCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    grant_id: str
    capability: str
    scope: str
    reason: str = Field(min_length=1, max_length=1000)
    effective_at: str
    expected_generation: int = Field(ge=0)
    expires_at: str | None = None


class CapabilityTransitionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    grant_id: str
    capability: str
    scope: str
    expected_generation: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    changed_at: str


def get_privileged_identity_provider() -> Any:
    return aws.client(Kind.COGNITO)


@router.post("/privileged-identities/admins")
def provision_privileged_admin(
    payload: AdminProvisionCommand,
    actor: Actor = Depends(admin_operation),
    provider: Any = Depends(get_privileged_identity_provider),
    settings: Settings = Depends(config.settings),
) -> dict[str, Any]:
    return privileged_identity_service.provision_admin(
        actor=actor,
        provider=provider,
        user_pool_id=settings.cognito_user_pool_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/admins/{target_id}/status")
def change_privileged_admin_status(
    target_id: str,
    payload: AdminStatusCommand,
    actor: Actor = Depends(admin_operation),
    provider: Any = Depends(get_privileged_identity_provider),
    settings: Settings = Depends(config.settings),
) -> dict[str, Any]:
    return privileged_identity_service.change_admin_status(
        actor=actor,
        target_id=target_id,
        provider=provider,
        user_pool_id=settings.cognito_user_pool_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities")
def grant_privileged_capability(
    target_id: str,
    payload: CapabilityGrantCommand,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    return privileged_identity_service.grant_capability(
        actor=actor,
        target_id=target_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities/revoke")
def revoke_privileged_capability(
    target_id: str,
    payload: CapabilityTransitionCommand,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    return privileged_identity_service.revoke_capability(
        actor=actor,
        target_id=target_id,
        **payload.model_dump(),
    )


@router.post("/privileged-identities/{target_id}/capabilities/restore")
def restore_privileged_capability(
    target_id: str,
    payload: CapabilityTransitionCommand,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    return privileged_identity_service.restore_capability(
        actor=actor,
        target_id=target_id,
        **payload.model_dump(),
    )
