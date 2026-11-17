"""Admin account console: listing, invitations, password reset, status and parent links."""

from collections.abc import Mapping
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa import config
from stoa.deps import legacy_user
from stoa.db.repositories import (
    parent_link_repo,
    security_audit_repo,
    user_repo,
)
from stoa.security.admin_authorization import (
    AdminTargetProvider,
    admin_operation,
    admin_target_provider,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor
from stoa.models.user import SubscriptionTier
from stoa.services.account_errors import AccountErrorCode, AccountViolation
from stoa.services import (
    account_lifecycle,
    account_listing,
    account_provisioning_service,
    current_relationship,
    notify_service,
    parent_link_service,
    public_identity_service,
)
from stoa.services.teacher_identity_provider import CognitoTeacherIdentityProvider
from stoa.routers.admin._common import _now_iso


router = APIRouter()


PARENT_LINK_TARGET = AdminTargetProvider(
    "scalar", "body", ("parent_id", "student_id"), ("parent_id", "student_id"),
    reference_only=("reason",),
)


class UserUpdateRequest(BaseModel):
    subscription_tier: Optional[SubscriptionTier] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    grade: Optional[str] = Field(default=None, min_length=1, max_length=40)
    school: Optional[str] = Field(default=None, min_length=1, max_length=160)


class AccountInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=20)
    email: str = Field(min_length=3, max_length=320)
    fullName: str = Field(default="", max_length=120)
    # Shape-checked here only; the calendar check belongs to the service, which
    # refuses by code so the rejected date never travels back out.
    dateOfBirth: Optional[str] = Field(default=None, max_length=32)
    expirySeconds: Optional[int] = Field(default=None, ge=60, le=1209600)
    locale: Optional[str] = Field(default=None, min_length=2, max_length=8)


class AccountAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=20)
    email: str = Field(min_length=3, max_length=320)
    fullName: str = Field(default="", max_length=120)
    dateOfBirth: Optional[str] = Field(default=None, max_length=32)


class AccountInvitationReissueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expirySeconds: Optional[int] = Field(default=None, ge=60, le=1209600)
    locale: Optional[str] = Field(default=None, min_length=2, max_length=8)


class AccountPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class AccountStatusChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended", "archived"]
    reason: str = Field(min_length=1, max_length=500)


class AdminParentLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str = Field(min_length=1, max_length=120)
    student_id: str = Field(min_length=1, max_length=120)
    relationship: str = Field(default="child", min_length=1, max_length=40)


class AdminParentLinkRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str = Field(min_length=1, max_length=120)
    student_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class AdminParentLinkRevokeResponse(BaseModel):
    """The link as it now stands: closed on both sides at `link_updated_at`."""

    parent_id: str
    student_id: str
    relationship: str
    status: str
    link_updated_at: str


@router.get("/users")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    role: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=120),
    created_from: Optional[str] = Query(default=None, max_length=40),
    created_to: Optional[str] = Query(default=None, max_length=40),
    cursor: Optional[str] = Query(default=None, max_length=2000),
    actor: Actor = Depends(admin_operation),
):
    """One page of accounts, grouped by role, with their confirmed parent links.

    Card 002 #7: the links are resolved one account at a time, so the cost of a
    page is the page size times the links behind it, not the page size. Measured
    on a full page of parents with three children each: 3201 DynamoDB round trips,
    against a 29 second API Gateway ceiling. The number is pinned by
    tests/test_admin_user_list_read_amplification.py so it cannot grow unnoticed;
    batching it down needs `current_relationship.judge`, not this file.
    """
    del actor
    return account_listing.account_page(
        limit=limit,
        role=role,
        status=status,
        keyword=q,
        created_from=created_from,
        created_to=created_to,
        cursor=cursor,
    )


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Update a user's subscription tier or active status."""
    profile = user_repo.get_user(user_id)
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)

    update_parts = []
    attr_values: dict = {}

    attr_names: dict[str, str] = {}

    if body.subscription_tier is not None:
        update_parts.append("subscription_tier = :tier")
        attr_values[":tier"] = body.subscription_tier.value
    if body.name is not None:
        update_parts.append("#name = :name")
        attr_names["#name"] = "name"
        attr_values[":name"] = body.name
    if body.grade is not None:
        update_parts.append("grade = :grade")
        attr_values[":grade"] = body.grade
    if body.school is not None:
        update_parts.append("school = :school")
        attr_values[":school"] = body.school

    if not update_parts:
        return {"user_id": user_id, "message": "Nothing to update"}

    changed = {
        field: present
        for field, present in (
            ("subscription_tier", body.subscription_tier is not None),
            ("name", body.name is not None),
            ("grade", body.grade is not None),
            ("school", body.school is not None),
        )
        if present
    }
    user_repo.update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(update_parts),
        expression_attribute_values=attr_values,
        expression_attribute_names=attr_names or None,
        owned_fields=frozenset(changed),
    )
    _record_account_admin_event(
        actor=actor,
        target_id=user_id,
        event_type="account_profile_edited",
        action="update_account_profile",
        reason_code=",".join(sorted(changed)),
        evidence_reference=_account_change_evidence(profile, attr_values, attr_names),
    )
    return {"user_id": user_id, "updated": {k.lstrip(":"): v for k, v in attr_values.items()}}


# ---------------------------------------------------------------------------
# Account provisioning, password reset, status machine and parent links
# ---------------------------------------------------------------------------


def get_account_identity_provider(settings: Settings = Depends(config.settings)) -> Any:
    """Role-neutral account creator; the teacher adapter already speaks this shape."""
    return CognitoTeacherIdentityProvider(
        aws.client(Kind.COGNITO),
        user_pool_id=settings.cognito_user_pool_id,
    )


def get_account_password_administrator() -> Any:
    return aws.client(Kind.COGNITO)


def _account_issuer(settings: Settings) -> str:
    return public_identity_service.canonical_public_issuer(settings.allowed_cognito_issuers)


def _invitation_delivery(locale: str | None):
    """Mail the invitee in the language the request names, else in all four (#374, #415).

    Never in the administrator's own screen language: that is who sent the
    invitation, not who reads it. The operator calls (#384) mail the same way.
    """
    return notify_service.account_invitation_delivery(locale)


def _record_account_admin_event(
    *,
    actor: Actor,
    target_id: str,
    event_type: str,
    action: str,
    reason_code: str = "",
    evidence_reference: str = "",
) -> None:
    """One durable row per administrator write against an account."""
    event: dict[str, object] = {
        "event_id": f"event_{uuid4().hex}",
        "event_type": event_type,
        "actor_id": actor.user_id,
        "actor_role": actor.role.value,
        "target_id": target_id,
        "target_type": "account",
        "action": action,
        "created_at": _now_iso(),
    }
    if reason_code:
        event["reason_code"] = reason_code[:200]
    if evidence_reference:
        event["evidence_reference"] = evidence_reference[:400]
    security_audit_repo.append_event(target_id, event)


def _account_change_evidence(
    profile: Mapping[str, object],
    attr_values: Mapping[str, object],
    attr_names: Mapping[str, str],
) -> str:
    """Before and after for every field this command actually writes."""
    parts: list[str] = []
    for alias, value in attr_values.items():
        field = attr_names.get(f"#{alias.lstrip(':')}", alias.lstrip(":"))
        parts.append(f"{field}:{profile.get(field)!s}->{value!s}")
    return ";".join(sorted(parts))


def _account_profile_or_404(user_id: str) -> dict[str, Any]:
    profile = user_repo.get_user(user_id)
    if not profile:
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    return dict(profile)


def _account_email_or_409(profile: Mapping[str, object]) -> str:
    email = str(profile.get("email") or "").strip()
    if not email:
        raise AccountViolation(AccountErrorCode.ACCOUNT_EMAIL_MISSING)
    return email


def _refuse_password_reset(
    *, actor: Actor, target_id: str, reason_code: AccountErrorCode
) -> None:
    """A refused reset is still a command somebody issued, so it is recorded."""
    _record_account_admin_event(
        actor=actor,
        target_id=target_id,
        event_type="account_password_reset_denied",
        action="reset_account_password",
        reason_code=reason_code,
        evidence_reference=f"account_password_reset_denied:{reason_code}",
    )
    raise AccountViolation(reason_code)


def _guard_peer_admin_credentials(
    *, actor: Actor, target_id: str, profile: Mapping[str, object]
) -> None:
    """Card 006: an administrator may not take another administrator's credential.

    This is a different judgement from the lifecycle's last-administrator guard
    (`account_lifecycle.transition`), because the
    harm is different. Resetting someone else's password does not close the console
    down; it hands the caller a working credential for another privileged principal,
    in plaintext, in the response body, with no consent from the target and no
    notice to it - the target's own change-at-next-sign-in obligation only fires
    when the target signs in, and the caller signs in first. Administrators are not
    interchangeable either: privileged capabilities such as `admin_identity_manager`
    are granted per account, so taking over a peer can be an escalation.

    Resetting one's own password is the legitimate case and is left alone; so is
    every non-admin target, which is what this console exists to service.

    The lockout this could cause - every administrator forgetting its password with
    no peer allowed to help - is answered outside the product, not inside it. The
    user pool is reachable with AWS credentials (`admin-set-user-password`), a
    separate trust domain with its own audit trail. Keeping the break-glass there
    is the point: an attacker holding one administrator session cannot reach it.
    """
    if actor.user_id == target_id:
        return
    if str(profile.get("role") or "") != "admin":
        return
    _refuse_password_reset(
        actor=actor,
        target_id=target_id,
        reason_code=AccountErrorCode.ACCOUNT_PEER_ADMIN_PASSWORD_RESET_FORBIDDEN,
    )


@router.post("/users/invitations")
def invite_account(
    payload: AccountInvitationRequest,
    actor: Actor = Depends(admin_operation),
    settings: Settings = Depends(config.settings),
) -> dict[str, Any]:
    """Open one account in `invited` state and mail its single-use activation link."""
    expiry = (
        payload.expirySeconds
        if payload.expirySeconds is not None
        else account_provisioning_service.DEFAULT_INVITATION_SECONDS
    )
    return account_provisioning_service.invite_account(
        actor=legacy_user(actor),
        role=payload.role,
        email=payload.email,
        full_name=payload.fullName,
        date_of_birth=payload.dateOfBirth,
        invitation_expiry_seconds=expiry,
        deliver=_invitation_delivery(payload.locale),
    )


@router.post("/users")
def assign_account(
    payload: AccountAssignmentRequest,
    actor: Actor = Depends(admin_operation),
    settings: Settings = Depends(config.settings),
    provider: Any = Depends(get_account_identity_provider),
) -> dict[str, Any]:
    """Open one active account and hand its initial password back exactly once."""
    return account_provisioning_service.assign_account(
        actor=legacy_user(actor),
        role=payload.role,
        email=payload.email,
        full_name=payload.fullName,
        date_of_birth=payload.dateOfBirth,
        provider=provider,
        issuer=_account_issuer(settings),
    )


@router.post("/users/invitations/{invitation_id}/reissue")
def reissue_account_invitation(
    invitation_id: str,
    payload: AccountInvitationReissueRequest,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Replace one undelivered invitation, reusing the number already allocated."""
    expiry = (
        payload.expirySeconds
        if payload.expirySeconds is not None
        else account_provisioning_service.DEFAULT_INVITATION_SECONDS
    )
    return account_provisioning_service.reissue_invitation(
        actor=legacy_user(actor),
        invitation_id=invitation_id,
        invitation_expiry_seconds=expiry,
        deliver=_invitation_delivery(payload.locale),
    )


@router.delete("/users/invitations/{invitation_id}")
def revoke_account_invitation(
    invitation_id: str,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    return account_provisioning_service.revoke_invitation(
        actor=legacy_user(actor), invitation_id=invitation_id
    )


@router.post("/users/{user_id}/password-reset")
def reset_account_password(
    user_id: str,
    payload: AccountPasswordResetRequest,
    actor: Actor = Depends(admin_operation),
    settings: Settings = Depends(config.settings),
    provider: Any = Depends(get_account_password_administrator),
) -> dict[str, Any]:
    """Set one temporary password the account must replace at its next sign-in.

    The provider password is set `Permanent=True` on purpose. `Permanent=False`
    parks the account in the provider's own FORCE_CHANGE_PASSWORD challenge,
    which this build has no route to answer, so the account could sign in
    nowhere. The obligation is carried locally instead: the profile flag raised
    here lets the account authenticate and then refuses every route but the
    self-service password change.

    An administrator can reset any account but a peer administrator's, so the
    audit row is written before the response is built and a failed write fails
    the command. Refusals are recorded too, from the same helper.
    """
    profile = _account_profile_or_404(user_id)
    _guard_peer_admin_credentials(actor=actor, target_id=user_id, profile=profile)
    email = _account_email_or_409(profile)
    account_provisioning_service.require_password_change_at_next_sign_in(user_id, profile)
    temporary_password = account_provisioning_service.generate_initial_password()
    try:
        provider.admin_set_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            Password=temporary_password,
            Permanent=True,
        )
    except Exception as exc:
        raise SecurityDecisionError(SecurityErrorCode.IDENTITY_PROVIDER_UNAVAILABLE) from exc
    _record_account_admin_event(
        actor=actor,
        target_id=user_id,
        event_type="account_password_reset",
        action="reset_account_password",
        reason_code=payload.reason,
        evidence_reference=f"account-number:{profile.get('account_number') or ''}",
    )
    return {
        "userId": user_id,
        "temporaryPassword": temporary_password,
        "mustChangePasswordAtNextSignIn": True,
    }


@router.post("/users/{user_id}/status")
def change_account_status(
    user_id: str,
    payload: AccountStatusChangeRequest,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Move one account along the status machine. Archive is as far as it goes."""
    profile = _account_profile_or_404(user_id)
    current = account_lifecycle.status_of(profile)
    account_lifecycle.transition(
        profile,
        current,
        payload.status,
        account_lifecycle.LifecycleActor(
            account_lifecycle.Trigger.ADMIN,
            user_id=actor.user_id,
            role=actor.role.value,
        ),
        payload.reason,
    )
    return {
        "userId": user_id,
        "accountStatus": payload.status,
        "previousStatus": current.value if current else "",
    }


@router.post("/users/parent-links")
def assign_parent_link(
    body: AdminParentLinkRequest,
    actor: Actor = Depends(admin_operation),
) -> dict[str, Any]:
    """Administrator assignment is trusted and audited, so it starts active."""
    try:
        link = parent_link_service.assign_link(
            parent_id=body.parent_id,
            student_id=body.student_id,
            actor_id=actor.user_id,
            relationship=body.relationship,
        )
    except parent_link_repo.ParentLinkConflict as exc:
        raise parent_link_service.ParentLinkError("link_already_exists") from exc
    _record_account_admin_event(
        actor=actor,
        target_id=body.student_id,
        event_type="parent_link_assigned",
        action="assign_parent_link",
        reason_code=body.relationship,
        evidence_reference=f"parent-link:{body.parent_id}->{body.student_id}",
    )
    return link


@router.post("/parent-links/revoke", response_model=AdminParentLinkRevokeResponse)
@admin_target_provider(PARENT_LINK_TARGET)
async def revoke_parent_link(
    body: AdminParentLinkRevokeRequest,
    actor: Actor = Depends(admin_operation),
) -> AdminParentLinkRevokeResponse:
    """End a parent-student relationship: both sides of its link in one write.

    Only a link with an open side can be revoked. An account that is no longer
    usable does not stop it - that is the relationship an administrator most
    needs to close. Either side having moved since it was read refuses the
    whole write and nothing changes (#208).
    """
    try:
        closed = current_relationship.revoke(
            body.parent_id,
            body.student_id,
            actor_id=actor.user_id,
            now=_now_iso(),
        )
    except parent_link_repo.ParentLinkConflict as exc:
        raise parent_link_service.ParentLinkError("link_revoke_conflict") from exc
    if closed is None:
        raise parent_link_service.ParentLinkError("link_not_open")
    _record_account_admin_event(
        actor=actor,
        target_id=body.student_id,
        event_type="parent_link_revoked",
        action="revoke_parent_link",
        reason_code=body.reason,
        evidence_reference=f"parent-link:{body.parent_id}->{body.student_id}",
    )
    return AdminParentLinkRevokeResponse(
        parent_id=closed.parent_id,
        student_id=closed.student_id,
        relationship=closed.relationship or "child",
        status=closed.status or "",
        link_updated_at=closed.version or "",
    )
