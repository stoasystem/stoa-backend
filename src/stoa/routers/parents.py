"""Parent routes — child list and weekly learning reports."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from stoa.db.dynamodb import get_table
from stoa.db.repositories import report_repo, user_repo
from stoa.deps import get_current_user, require_role
from stoa.models.report import WeeklyReportResponse

router = APIRouter()


class ChildSummary(BaseModel):
    user_id: str
    email: str
    grade: str | None
    subjects: list[str]


@router.get("/{parent_id}/children", response_model=list[ChildSummary])
async def list_children(
    parent_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the list of students linked to this parent."""
    role = user.get("role", "")
    uid = user["sub"]

    if role == "parent" and uid != parent_id:
        raise HTTPException(status_code=403, detail="Cannot view another parent's children")
    if role not in ("parent", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")

    # Query students whose parent_id matches
    table = get_table()
    result = table.scan(
        FilterExpression="#pid = :pid AND #role = :role",
        ExpressionAttributeNames={"#pid": "parent_id", "#role": "role"},
        ExpressionAttributeValues={":pid": parent_id, ":role": "student"},
    )
    children = result.get("Items", [])
    return [
        ChildSummary(
            user_id=c["user_id"],
            email=c["email"],
            grade=c.get("grade"),
            subjects=c.get("subjects", []),
        )
        for c in children
    ]


@router.get("/{parent_id}/reports/{week}", response_model=WeeklyReportResponse)
async def get_report(
    parent_id: str,
    week: str,
    user: dict = Depends(get_current_user),
):
    """Return the weekly report for a given ISO week (YYYY-MM-DD of Monday)."""
    role = user.get("role", "")
    uid = user["sub"]

    if role == "parent" and uid != parent_id:
        raise HTTPException(status_code=403, detail="Cannot view another parent's reports")
    if role not in ("parent", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")

    report = report_repo.get_report_by_week(parent_id, week)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for week '{week}'")

    return WeeklyReportResponse(**report)
