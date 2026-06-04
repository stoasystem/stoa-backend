"""Admin routes — user management, report operations, and platform statistics."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stoa.db.dynamodb import get_table
from stoa.db.repositories import report_repo, user_repo
from stoa.deps import require_role
from stoa.models.question import QuestionStatus
from stoa.models.user import SubscriptionTier
from stoa.services import notify_service, report_artifact_service

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


class ReportOperationResponse(BaseModel):
    report_id: str
    parent_id: str
    student_id: str
    student_name: str | None = None
    week_start: str
    status: str | None = None
    email_status: str | None = None
    artifacts: dict[str, bool]
    generation: dict[str, str | None]
    delivery: dict[str, str | None]
    operations: dict[str, str | None]
    actions: dict[str, dict[str, str | bool | None]]


class ReportOperationListResponse(BaseModel):
    items: list[ReportOperationResponse]
    count: int
    next_token: str | None = None
    access_pattern: str


class ReportResendResponse(BaseModel):
    report_id: str
    status: str
    email_status: str
    operation: str
    operation_result: str
    updated_at: str


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


@router.get("/reports/ops", response_model=ReportOperationListResponse)
async def list_report_operations(
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    week_start: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List report operation metadata for admin triage."""
    try:
        last_key = report_repo.decode_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    result = report_repo.list_reports_for_admin(
        status=status,
        week_start=week_start,
        parent_id=parent_id,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
    )
    items = [_report_operation_response(report) for report in result.get("Items", [])]
    return ReportOperationListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_page_token(result.get("LastEvaluatedKey")),
        access_pattern="parent_gsi" if parent_id else "bounded_scan",
    )


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/ops",
    response_model=ReportOperationResponse,
)
async def get_report_operations(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Inspect report artifact and delivery metadata without exposing artifact content."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    return _report_operation_response(report)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/resend",
    response_model=ReportResendResponse,
)
async def resend_report_email(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Resend a failed report email using the existing private HTML artifact."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    if report.get("status") != "email_failed" and report.get("email_status") != "failed":
        raise HTTPException(status_code=409, detail="Report delivery is not failed")

    html_key = report.get("html_s3_key") or report.get("s3_key")
    parent_email = report.get("parent_email")
    if not html_key or not parent_email:
        raise HTTPException(status_code=422, detail="Report is missing email or HTML artifact metadata")

    operator = _operator_id(user)
    attempted_at = _now_iso()
    try:
        html = report_artifact_service.get_report_html(str(html_key))
        notify_service.send_weekly_report_email(
            str(parent_email),
            html,
            subject=f"STOA weekly report for {report.get('student_name') or 'Student'}",
        )
    except Exception as exc:
        failed_at = _now_iso()
        report_repo.update_report_status(
            report["report_id"],
            "email_failed",
            email_status="failed",
            email_failed_at=failed_at,
            email_error_class=type(exc).__name__,
            email_error_message=str(exc)[:240],
            resend_attempted_at=attempted_at,
            last_operation="resend_email",
            last_operation_at=failed_at,
            last_operation_by=operator,
            last_operation_result="failed",
            updated_at=failed_at,
        )
        raise HTTPException(status_code=502, detail="Report resend failed") from exc

    sent_at = _now_iso()
    report_repo.update_report_status(
        report["report_id"],
        "email_sent",
        email_status="sent",
        email_sent_at=sent_at,
        resend_attempted_at=attempted_at,
        resend_completed_at=sent_at,
        last_operation="resend_email",
        last_operation_at=sent_at,
        last_operation_by=operator,
        last_operation_result="success",
        updated_at=sent_at,
    )
    return ReportResendResponse(
        report_id=report["report_id"],
        status="email_sent",
        email_status="sent",
        operation="resend_email",
        operation_result="success",
        updated_at=sent_at,
    )


def _get_report_or_404(parent_id: str, student_id: str, week_start: str) -> dict:
    report = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _report_operation_response(report: dict) -> ReportOperationResponse:
    return ReportOperationResponse(
        report_id=report.get("report_id", ""),
        parent_id=report.get("parent_id", ""),
        student_id=report.get("student_id", ""),
        student_name=report.get("student_name"),
        week_start=report.get("week_start", ""),
        status=report.get("status"),
        email_status=report.get("email_status"),
        artifacts={
            "json_available": bool(report.get("json_s3_key")),
            "html_available": bool(report.get("html_s3_key") or report.get("s3_key")),
        },
        generation={
            "generated_at": report.get("generated_at"),
            "generation_failed_at": report.get("generation_failed_at"),
            "generation_error_class": report.get("generation_error_class"),
            "generation_error_message": report.get("generation_error_message"),
        },
        delivery={
            "parent_email": report.get("parent_email"),
            "email_sent_at": report.get("email_sent_at"),
            "email_failed_at": report.get("email_failed_at"),
            "email_error_class": report.get("email_error_class"),
            "email_error_message": report.get("email_error_message"),
        },
        operations={
            "last_operation": report.get("last_operation"),
            "last_operation_at": report.get("last_operation_at"),
            "last_operation_by": report.get("last_operation_by"),
            "last_operation_result": report.get("last_operation_result"),
            "resend_attempted_at": report.get("resend_attempted_at"),
            "resend_completed_at": report.get("resend_completed_at"),
        },
        actions=_report_action_eligibility(report),
    )


def _report_action_eligibility(report: dict) -> dict[str, dict[str, str | bool | None]]:
    status = report.get("status")
    email_status = report.get("email_status")
    can_resend = status == "email_failed" or email_status == "failed"
    can_retry_generation = status == "generation_failed"
    return {
        "resend_email": {
            "enabled": can_resend,
            "reason": None if can_resend else _disabled_reason(status, "email_failed"),
        },
        "retry_generation": {
            "enabled": can_retry_generation,
            "reason": None if can_retry_generation else _disabled_reason(status, "generation_failed"),
        },
    }


def _disabled_reason(status: str | None, required_status: str) -> str:
    if not status:
        return f"Report status is missing; requires {required_status}"
    return f"Report status is {status}; requires {required_status}"


def _operator_id(user: dict) -> str:
    return str(
        user.get("sub")
        or user.get("username")
        or user.get("email")
        or "unknown-admin"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
