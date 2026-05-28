"""Admin routes — user management and platform statistics."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stoa.db.dynamodb import get_table
from stoa.db.repositories import user_repo
from stoa.deps import require_role
from stoa.models.question import QuestionStatus
from stoa.models.user import SubscriptionTier

router = APIRouter()


class UserUpdateRequest(BaseModel):
    subscription_tier: Optional[SubscriptionTier] = None
    is_active: Optional[bool] = None


class StatsResponse(BaseModel):
    total_users: int
    total_students: int
    total_parents: int
    total_teachers: int
    total_questions: int
    ai_resolved: int
    teacher_resolved: int
    escalated: int


@router.get("/users")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    role: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Paginated list of all platform users."""
    table = get_table()

    filter_expr = "#entity = :profile"
    attr_names = {"#entity": "SK"}
    attr_values = {":profile": "PROFILE"}

    if role:
        filter_expr += " AND #role = :role"
        attr_names["#role"] = "role"
        attr_values[":role"] = role

    result = table.scan(
        FilterExpression=filter_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        Limit=limit,
    )
    users = result.get("Items", [])
    # Strip PK/SK from response
    for u in users:
        u.pop("PK", None)
        u.pop("SK", None)

    return {"items": users, "count": len(users)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Update a user's subscription tier or active status."""
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    table = get_table()
    update_parts = []
    attr_values: dict = {}

    if body.subscription_tier is not None:
        update_parts.append("subscription_tier = :tier")
        attr_values[":tier"] = body.subscription_tier.value
    if body.is_active is not None:
        update_parts.append("is_active = :active")
        attr_values[":active"] = body.is_active

    if not update_parts:
        return {"user_id": user_id, "message": "Nothing to update"}

    table.update_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeValues=attr_values,
    )
    return {"user_id": user_id, "updated": {k.lstrip(":"): v for k, v in attr_values.items()}}


@router.get("/stats", response_model=StatsResponse)
async def get_stats(user: dict = Depends(require_role("admin"))):
    """Return aggregate platform metrics (full-table scan — small scale only)."""
    table = get_table()

    # Count user profiles
    user_scan = table.scan(
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
        ProjectionExpression="#role",
        ExpressionAttributeNames={"#role": "role"},
    )
    users = user_scan.get("Items", [])

    counts = {"student": 0, "parent": 0, "teacher": 0}
    for u in users:
        r = u.get("role", "")
        if r in counts:
            counts[r] += 1

    # Count questions by status
    q_scan = table.scan(
        FilterExpression="SK = :meta",
        ExpressionAttributeValues={":meta": "META"},
        ProjectionExpression="#s",
        ExpressionAttributeNames={"#s": "status"},
    )
    questions = [
        q for q in q_scan.get("Items", [])
        if q.get("status") in (s.value for s in QuestionStatus)
    ]

    ai_resolved = sum(1 for q in questions if q.get("status") == QuestionStatus.AI_ANSWERED.value)
    teacher_resolved = sum(1 for q in questions if q.get("status") == QuestionStatus.RESOLVED.value)
    escalated = sum(
        1 for q in questions
        if q.get("status") in (QuestionStatus.ESCALATED.value, QuestionStatus.TEACHER_ACTIVE.value)
    )

    return StatsResponse(
        total_users=len(users),
        total_students=counts["student"],
        total_parents=counts["parent"],
        total_teachers=counts["teacher"],
        total_questions=len(questions),
        ai_resolved=ai_resolved,
        teacher_resolved=teacher_resolved,
        escalated=escalated,
    )
