"""Parent routes - child list and weekly learning reports."""
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import report_repo, user_repo
from stoa.deps import get_current_user, require_role
from stoa.models.report import WeeklyReportResponse

router = APIRouter()


@dataclass(frozen=True)
class ResolvedParent:
    claims_sub: str
    email: str
    parent_user_id: str
    profile: dict[str, Any]


class ChildSummary(BaseModel):
    id: str
    userId: str
    name: str
    email: str
    grade: str | None
    subjects: list[str]
    relationship: str = "child"


class ChildListResponse(BaseModel):
    items: list[ChildSummary]


class LegacyChildSummary(BaseModel):
    user_id: str
    email: str
    grade: str | None
    subjects: list[str]


def _resolve_parent_profile(user: dict, settings: Settings) -> ResolvedParent:
    """Resolve a parent JWT to the local DynamoDB parent profile."""
    claims_sub = user.get("sub", "")
    if not claims_sub:
        raise HTTPException(status_code=401, detail="Missing authenticated user id")

    profile = user_repo.get_user(claims_sub)
    email = profile.get("email", "") if profile else ""

    if not profile:
        cognito_username = user.get("username", claims_sub)
        try:
            cognito = boto3.client("cognito-idp", region_name=settings.aws_region)
            data = cognito.admin_get_user(
                UserPoolId=settings.cognito_user_pool_id,
                Username=cognito_username,
            )
        except ClientError as exc:
            raise HTTPException(status_code=404, detail="Parent profile not found") from exc

        attrs = {attr["Name"]: attr["Value"] for attr in data.get("UserAttributes", [])}
        email = attrs.get("email", "")
        if email:
            profile = user_repo.get_user_by_email(email)

    if not profile:
        raise HTTPException(status_code=404, detail="Parent profile not found")
    if profile.get("role") != "parent":
        raise HTTPException(status_code=403, detail="Resolved profile is not a parent")

    return ResolvedParent(
        claims_sub=claims_sub,
        email=email or profile.get("email", ""),
        parent_user_id=profile["user_id"],
        profile=profile,
    )


def _scan_children_for_parent(parent_user_id: str) -> list[dict[str, Any]]:
    table = get_table()
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": "#pid = :pid AND #role = :role",
        "ExpressionAttributeNames": {"#pid": "parent_id", "#role": "role"},
        "ExpressionAttributeValues": {":pid": parent_user_id, ":role": "student"},
    }
    children: list[dict[str, Any]] = []

    while True:
        result = table.scan(**scan_kwargs)
        children.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return children
        scan_kwargs["ExclusiveStartKey"] = last_key


def _subjects_from_profile(profile: dict[str, Any]) -> list[str]:
    subjects = profile.get("primary_subjects")
    if subjects is None:
        subjects = profile.get("subjects", [])
    return subjects if isinstance(subjects, list) else []


def _child_summary_from_profile(profile: dict[str, Any]) -> ChildSummary:
    email = profile.get("email", "")
    name = profile.get("name") or (email.split("@")[0] if email else "")
    user_id = profile.get("user_id", "")
    return ChildSummary(
        id=user_id,
        userId=user_id,
        name=name,
        email=email,
        grade=profile.get("grade"),
        subjects=_subjects_from_profile(profile),
        relationship=profile.get("relationship", "child"),
    )


def _legacy_child_summary_from_profile(profile: dict[str, Any]) -> LegacyChildSummary:
    return LegacyChildSummary(
        user_id=profile.get("user_id", ""),
        email=profile.get("email", ""),
        grade=profile.get("grade"),
        subjects=_subjects_from_profile(profile),
    )


@router.get("/me/children", response_model=ChildListResponse)
async def list_my_children(
    user: dict = Depends(require_role("parent")),
    settings: Settings = Depends(get_settings),
):
    """Return children linked to the authenticated parent."""
    resolved = _resolve_parent_profile(user, settings)
    children = _scan_children_for_parent(resolved.parent_user_id)
    return ChildListResponse(items=[_child_summary_from_profile(child) for child in children])


@router.get("/{parent_id}/children", response_model=list[LegacyChildSummary])
async def list_children(
    parent_id: str,
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return the list of students linked to this parent."""
    role = user.get("role", "")

    if role not in ("parent", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")
    if role == "parent":
        resolved = _resolve_parent_profile(user, settings)
        if resolved.parent_user_id != parent_id:
            raise HTTPException(status_code=403, detail="Cannot view another parent's children")

    children = _scan_children_for_parent(parent_id)
    return [_legacy_child_summary_from_profile(child) for child in children]


@router.get("/{parent_id}/reports/{week}", response_model=WeeklyReportResponse)
async def get_report(
    parent_id: str,
    week: str,
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Return the weekly report for a given ISO week (YYYY-MM-DD of Monday)."""
    role = user.get("role", "")

    if role not in ("parent", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")
    if role == "parent":
        resolved = _resolve_parent_profile(user, settings)
        if resolved.parent_user_id != parent_id:
            raise HTTPException(status_code=403, detail="Cannot view another parent's reports")

    report = report_repo.get_report_by_week(parent_id, week)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for week '{week}'")

    return WeeklyReportResponse(**report)
