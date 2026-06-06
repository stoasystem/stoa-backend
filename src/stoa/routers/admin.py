"""Admin routes — user management, report operations, and platform statistics."""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from stoa.db.dynamodb import get_table
from stoa.db.repositories import report_repo, user_repo
from stoa.deps import require_role
from stoa.models.question import QuestionStatus
from stoa.models.user import SubscriptionTier
from stoa.services import (
    report_artifact_edit_service,
    report_edit_service,
    release_evidence_service,
    report_recovery_evidence_service,
    report_recovery_job_service,
    report_recovery_service,
)

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


class ReportResendTarget(BaseModel):
    parent_id: str
    student_id: str
    week_start: str


class BulkReportResendRequest(BaseModel):
    reports: list[ReportResendTarget] = Field(..., min_length=1, max_length=25)


class BulkReportResendItemResult(BaseModel):
    parent_id: str
    student_id: str
    week_start: str
    result: str
    report_id: str | None = None
    status: str | None = None
    email_status: str | None = None
    operation: str = "resend_email"
    operation_result: str | None = None
    updated_at: str | None = None
    detail: str | None = None
    error_class: str | None = None


class BulkReportResendResponse(BaseModel):
    operation: str
    count: int
    results: list[BulkReportResendItemResult]


class ReportGenerationRetryResponse(BaseModel):
    report_id: str
    status: str
    email_status: str | None = None
    operation: str
    operation_result: str
    updated_at: str
    artifacts: dict[str, bool]


class ReportEditDraftRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    proposed_fields: dict[str, Any] = Field(..., min_length=1)


class ReportEditDraftResponse(BaseModel):
    draft_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    proposed_fields: dict[str, str | None]
    status: str
    applied_by: str | None = None
    applied_at: str | None = None


class ReportEditApplyResponse(BaseModel):
    operation: str
    operation_result: str
    draft: ReportEditDraftResponse
    report: dict[str, Any]


class ReportArtifactEditPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    proposed_fields: dict[str, Any] = Field(..., min_length=1)


class ReportArtifactEditDiffItem(BaseModel):
    field: str
    before: Any = None
    after: Any = None
    changed: bool


class ReportArtifactEditPreviewResponse(BaseModel):
    draft_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    source_artifact_version_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    proposed_fields: dict[str, Any]
    diff: list[ReportArtifactEditDiffItem]
    status: str
    applied_by: str | None = None
    applied_at: str | None = None
    artifact_version_id: str | None = None


class ReportArtifactEditApplyRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactEditApplyResponse(BaseModel):
    operation: str
    operation_result: str
    draft: ReportArtifactEditPreviewResponse
    report: dict[str, Any]


class ReportArtifactRollbackPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactRollbackPreviewResponse(BaseModel):
    preview_id: str
    report_id: str
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    source_updated_at: str | None = None
    source_artifact_version_id: str | None = None
    target_artifact_version_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None
    status: str
    validation_result: str
    applied_by: str | None = None
    applied_at: str | None = None
    artifact_version_id: str | None = None


class ReportArtifactRollbackApplyRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ReportArtifactRollbackApplyResponse(BaseModel):
    operation: str
    operation_result: str
    preview: ReportArtifactRollbackPreviewResponse
    report: dict[str, Any]


class ReportAuditEventResponse(BaseModel):
    event_id: str
    event_at: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    actor: str | None = None
    action: str
    reason: str | None = None
    source: str | None = None
    result: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    error_class: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None


class ReportAuditListResponse(BaseModel):
    items: list[ReportAuditEventResponse]
    count: int
    next_token: str | None = None
    scope: str


class RecoveryJobFilters(BaseModel):
    status: str = "email_failed"
    week_start: str | None = None
    parent_id: str | None = None
    student_id: str | None = None


class RecoveryJobPreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    filters: RecoveryJobFilters = Field(default_factory=RecoveryJobFilters)
    max_targets: int = Field(default=25, ge=1, le=25)


class RecoveryJobPreviewTarget(BaseModel):
    target_id: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    student_name: str | None = None
    week_start: str | None = None
    status: str | None = None
    email_status: str | None = None
    artifacts: dict[str, bool]
    eligibility: str
    refusal_reason: str | None = None


class RecoveryJobResumePreviewTarget(RecoveryJobPreviewTarget):
    source_result: str | None = None
    detail: str | None = None
    error_class: str | None = None


class RecoveryJobPreviewResponse(BaseModel):
    operation: str
    reason: str
    requested_by: str
    filters: dict[str, str | None]
    max_targets: int
    scanned_pages: int
    eligible_count: int
    refused_count: int
    missing_count: int
    sample: list[RecoveryJobPreviewTarget]
    preview_token: str


class RecoveryJobResumePreviewRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    results: list[str] = Field(default_factory=lambda: ["failed", "refused", "not_found"])
    max_targets: int = Field(default=25, ge=1, le=25)


class RecoveryJobResumePreviewResponse(BaseModel):
    operation: str
    source_job_id: str
    job_type: str
    reason: str
    requested_by: str
    result_filters: list[str]
    max_targets: int
    scanned_targets: int
    eligible_count: int
    refused_count: int
    missing_count: int
    sample: list[RecoveryJobResumePreviewTarget]
    preview_token: str


class RecoveryJobResumeCreateRequest(RecoveryJobResumePreviewRequest):
    preview_token: str = Field(..., min_length=1)


class RecoveryJobCreateRequest(RecoveryJobPreviewRequest):
    preview_token: str = Field(..., min_length=1)


class RecoveryJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    reason: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    cancellation_requested_by: str | None = None
    cancellation_requested_at: str | None = None
    filters: dict[str, Any] | None = None
    target_count: int = 0
    pending_count: int = 0
    attempted_count: int = 0
    success_count: int = 0
    refused_count: int = 0
    not_found_count: int = 0
    failed_count: int = 0
    skipped_cancelled_count: int = 0
    stop_reason: str | None = None
    source_job_id: str | None = None
    resume_result_filters: list[str] | None = None


class RecoveryJobListResponse(BaseModel):
    items: list[RecoveryJobResponse]
    count: int
    next_token: str | None = None


class RecoveryJobTargetResponse(BaseModel):
    target_id: str
    report_id: str | None = None
    parent_id: str | None = None
    student_id: str | None = None
    student_name: str | None = None
    week_start: str | None = None
    result: str
    status: str | None = None
    email_status: str | None = None
    detail: str | None = None
    error_class: str | None = None
    attempted_at: str | None = None
    completed_at: str | None = None


class RecoveryJobTargetsResponse(BaseModel):
    items: list[RecoveryJobTargetResponse]
    count: int
    next_token: str | None = None


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
        last_key = report_repo.decode_admin_page_token(next_token)
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
        next_token=report_repo.encode_admin_page_token(result.get("LastEvaluatedKey")),
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


@router.post("/reports/bulk-resend", response_model=BulkReportResendResponse)
async def bulk_resend_report_emails(
    request: BulkReportResendRequest,
    user: dict = Depends(require_role("admin")),
):
    """Resend selected failed report emails with independent per-item results."""
    operator = _operator_id(user)
    results: list[BulkReportResendItemResult] = []

    for target in request.reports:
        report = report_repo.get_report_for_child_by_week(target.parent_id, target.student_id, target.week_start)
        if not report:
            results.append(
                BulkReportResendItemResult(
                    parent_id=target.parent_id,
                    student_id=target.student_id,
                    week_start=target.week_start,
                    result="not_found",
                    operation_result="not_found",
                    detail="Report not found",
                )
            )
            continue

        try:
            resend = report_recovery_service.resend_report_email(
                report,
                operator=operator,
                reason="admin_selected_bulk_resend",
            )
        except report_recovery_service.ReportRecoveryError as exc:
            results.append(_bulk_resend_error_result(target, report, exc))
            continue

        results.append(
            BulkReportResendItemResult(
                parent_id=target.parent_id,
                student_id=target.student_id,
                week_start=target.week_start,
                result="success",
                report_id=resend.report_id,
                status=resend.status,
                email_status=resend.email_status,
                operation=resend.operation,
                operation_result=resend.operation_result,
                updated_at=resend.updated_at,
            )
        )

    return BulkReportResendResponse(operation="bulk_resend_email", count=len(results), results=results)


@router.post(
    "/reports/recovery-jobs/resend-email/preview",
    response_model=RecoveryJobPreviewResponse,
)
async def preview_resend_recovery_job(
    request: RecoveryJobPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded async resend recovery job before mutation."""
    try:
        return report_recovery_job_service.preview_resend_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/resend-email",
    response_model=RecoveryJobResponse,
)
async def create_resend_recovery_job(
    request: RecoveryJobCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded async resend recovery job after preview confirmation."""
    try:
        job = report_recovery_job_service.create_resend_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/retry-generation/preview",
    response_model=RecoveryJobPreviewResponse,
)
async def preview_generation_retry_recovery_job(
    request: RecoveryJobPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded async generation retry recovery job before mutation."""
    try:
        return report_recovery_job_service.preview_generation_retry_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/retry-generation",
    response_model=RecoveryJobResponse,
)
async def create_generation_retry_recovery_job(
    request: RecoveryJobCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded async generation retry recovery job after preview confirmation."""
    try:
        job = report_recovery_job_service.create_generation_retry_job(
            reason=request.reason,
            operator=_operator_id(user),
            filters=request.filters.model_dump(),
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/{job_id}/resume/preview",
    response_model=RecoveryJobResumePreviewResponse,
)
async def preview_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumePreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Preview a bounded resume job from a prior recovery job target subset."""
    try:
        return report_recovery_job_service.preview_resume_job(
            source_job_id=job_id,
            reason=request.reason,
            operator=_operator_id(user),
            results=request.results,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc


@router.post(
    "/reports/recovery-jobs/{job_id}/resume",
    response_model=RecoveryJobResponse,
)
async def create_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumeCreateRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded resume job from a prior recovery job target subset."""
    try:
        job = report_recovery_job_service.create_resume_job(
            source_job_id=job_id,
            reason=request.reason,
            operator=_operator_id(user),
            results=request.results,
            preview_token=request.preview_token,
            max_targets=request.max_targets,
        )
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


@router.get("/reports/recovery-evidence")
async def export_recovery_evidence(
    request: Request,
    job_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    include_targets: bool = Query(default=True),
    include_job_audit: bool = Query(default=True),
    target_limit: int = Query(default=50, ge=1, le=100),
    audit_limit: int = Query(default=50, ge=1, le=100),
    next_target_token: Optional[str] = Query(default=None),
    next_audit_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Export metadata-only report recovery evidence for release/support review."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    try:
        if job_id:
            response = _export_recovery_job_evidence(
                job_id=job_id,
                request_id=request_id,
                include_targets=include_targets,
                include_job_audit=include_job_audit,
                target_limit=target_limit,
                audit_limit=audit_limit,
                next_target_token=next_target_token,
                next_audit_token=next_audit_token,
            )
        else:
            response = _export_recent_recovery_jobs(
                request_id=request_id,
                status=status,
                limit=limit,
                next_token=next_token,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    report_recovery_evidence_service.log_export_access(
        actor=operator,
        request_id=request_id,
        scope=response["scope"],
        filters=response["filters"],
        result_counts={
            "jobs": len(response["jobs"]),
            "targets": len(response["targets"]),
            "job_audit": len(response["job_audit"]),
            "report_audit": len(response["report_audit"]),
        },
        status="success",
    )
    return response


@router.get("/reports/recovery-jobs/{job_id}/support-package")
async def export_recovery_job_support_package(
    request: Request,
    job_id: str,
    include_targets: bool = Query(default=True),
    include_job_audit: bool = Query(default=True),
    include_report_audit: bool = Query(default=False),
    target_limit: int = Query(default=50, ge=1, le=100),
    audit_limit: int = Query(default=50, ge=1, le=100),
    next_target_token: Optional[str] = Query(default=None),
    next_audit_token: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None, max_length=500),
    user: dict = Depends(require_role("admin")),
):
    """Export a support-safe metadata package for one recovery job."""
    request_id = _request_id(request)
    operator = _operator_id(user)
    try:
        response = _export_recovery_job_support_package(
            job_id=job_id,
            request_id=request_id,
            include_targets=include_targets,
            include_job_audit=include_job_audit,
            include_report_audit=include_report_audit,
            target_limit=target_limit,
            audit_limit=audit_limit,
            next_target_token=next_target_token,
            next_audit_token=next_audit_token,
            operator_note=note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    report_recovery_evidence_service.log_export_access(
        actor=operator,
        request_id=request_id,
        scope=response["scope"],
        filters={"job_id": job_id, "source_job_id": response.get("source_job", {}).get("job_id") if response.get("source_job") else None},
        result_counts={
            "targets": len(response["targets"]),
            "job_audit": len(response["job_audit"]),
            "report_audit": len(response["report_audit"]),
        },
        status="success",
    )
    return response


@router.post("/reports/release-evidence/validate")
async def validate_release_evidence(
    bundle: dict[str, Any] = Body(...),
    user: dict = Depends(require_role("admin")),
):
    """Validate and redact a release evidence bundle without mutating reports."""
    return release_evidence_service.validate_release_bundle(bundle)


@router.get("/reports/release-evidence/fixture-status")
async def get_release_fixture_status(
    fixture_name: str = Query(..., min_length=1),
    parent_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    week_start: Optional[str] = Query(default=None),
    expected_artifact_version: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """Inspect one approved safe fixture without exposing private artifact metadata."""
    approved = release_evidence_service.approved_fixture_config(fixture_name)
    resolved_parent_id = parent_id or approved.get("parent_id")
    resolved_student_id = student_id or approved.get("student_id")
    resolved_week_start = week_start or approved.get("week_start")
    report = None
    audit_events: list[dict[str, Any]] = []

    if resolved_parent_id and resolved_student_id and resolved_week_start:
        report = report_repo.get_report_for_child_by_week(
            resolved_parent_id,
            resolved_student_id,
            resolved_week_start,
        )
        if report:
            audit_result = report_repo.list_report_audit_events(report["report_id"], limit=10)
            audit_events = audit_result.get("Items", [])

    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=expected_artifact_version,
    )


@router.get("/reports/recovery-jobs", response_model=RecoveryJobListResponse)
async def list_recovery_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List async report recovery jobs."""
    try:
        last_key = report_repo.decode_recovery_job_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_recovery_jobs(limit=limit, last_key=last_key)
    items = [_recovery_job_response(item) for item in result.get("Items", [])]
    return RecoveryJobListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
    )


@router.get("/reports/recovery-jobs/{job_id}", response_model=RecoveryJobResponse)
async def get_recovery_job(
    job_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Get one async report recovery job."""
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")
    return _recovery_job_response(job)


@router.get("/reports/recovery-jobs/{job_id}/results", response_model=RecoveryJobTargetsResponse)
async def list_recovery_job_results(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List metadata-only target results for one async recovery job."""
    if not report_repo.get_recovery_job(job_id):
        raise HTTPException(status_code=404, detail="Recovery job not found")
    try:
        last_key = report_repo.decode_recovery_job_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_recovery_job_targets(job_id, limit=limit, last_key=last_key)
    items = [_recovery_job_target_response(item) for item in result.get("Items", [])]
    return RecoveryJobTargetsResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
    )


@router.post("/reports/recovery-jobs/{job_id}/cancel", response_model=RecoveryJobResponse)
async def cancel_recovery_job(
    job_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Request cooperative cancellation for an async report recovery job."""
    try:
        job = report_recovery_job_service.cancel_recovery_job(job_id, operator=_operator_id(user))
    except report_recovery_job_service.RecoveryJobError as exc:
        raise _recovery_job_http_error(exc) from exc
    return _recovery_job_response(job)


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
    try:
        result = report_recovery_service.resend_report_email(
            report,
            operator=_operator_id(user),
            reason="admin_single_resend",
        )
    except report_recovery_service.ReportRecoveryError as exc:
        raise _report_recovery_http_error(exc) from exc
    return ReportResendResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=result.email_status,
        operation=result.operation,
        operation_result=result.operation_result,
        updated_at=result.updated_at,
    )


def _bulk_resend_error_result(
    target: ReportResendTarget,
    report: dict,
    exc: report_recovery_service.ReportRecoveryError,
) -> BulkReportResendItemResult:
    result = "failed" if exc.status_code >= 500 else "refused"
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report resend failed"
    return BulkReportResendItemResult(
        parent_id=target.parent_id,
        student_id=target.student_id,
        week_start=target.week_start,
        result=result,
        report_id=report.get("report_id"),
        status=report.get("status"),
        email_status=report.get("email_status"),
        operation_result=result,
        detail=detail,
        error_class=exc.error_class,
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/retry-generation",
    response_model=ReportGenerationRetryResponse,
)
async def retry_report_generation(
    parent_id: str,
    student_id: str,
    week_start: str,
    user: dict = Depends(require_role("admin")),
):
    """Retry generation for one generation-failed weekly report."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_recovery_service.retry_report_generation(
            report,
            parent_id=parent_id,
            student_id=student_id,
            week_start=week_start,
            operator=_operator_id(user),
            reason="admin_single_generation_retry",
        )
    except report_recovery_service.ReportRecoveryError as exc:
        raise _report_recovery_http_error(exc) from exc
    return ReportGenerationRetryResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=result.email_status,
        operation=result.operation,
        operation_result=result.operation_result,
        updated_at=result.updated_at,
        artifacts=result.artifacts or {"json_available": False, "html_available": False},
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts",
    response_model=ReportEditDraftResponse,
)
async def create_report_edit_draft(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportEditDraftRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        draft = report_edit_service.create_edit_draft(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            proposed_fields=body.proposed_fields,
            correlation_id=_request_id(request),
        )
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditDraftResponse(**draft)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}",
    response_model=ReportEditDraftResponse,
)
async def get_report_edit_draft(
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        draft = report_edit_service.get_edit_draft(report, draft_id)
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditDraftResponse(**draft)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/edit-drafts/{draft_id}/apply",
    response_model=ReportEditApplyResponse,
)
async def apply_report_edit_draft(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Apply one valid metadata-only report edit draft."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_edit_service.apply_edit_draft(
            report,
            draft_id=draft_id,
            operator=_operator_id(user),
            correlation_id=_request_id(request),
        )
    except report_edit_service.ReportEditError as exc:
        raise _report_edit_http_error(exc) from exc
    return ReportEditApplyResponse(
        operation="edit_report",
        operation_result="success",
        draft=ReportEditDraftResponse(**result["draft"]),
        report=result["report"],
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews",
    response_model=ReportArtifactEditPreviewResponse,
)
async def create_report_artifact_edit_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportArtifactEditPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.create_artifact_edit_preview(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            proposed_fields=body.proposed_fields,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditPreviewResponse(**preview)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews/{draft_id}",
    response_model=ReportArtifactEditPreviewResponse,
)
async def get_report_artifact_edit_preview(
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.get_artifact_edit_preview(report, draft_id)
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditPreviewResponse(**preview)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-edit-previews/{draft_id}/apply",
    response_model=ReportArtifactEditApplyResponse,
)
async def apply_report_artifact_edit_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    draft_id: str,
    body: ReportArtifactEditApplyRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply one bounded report artifact edit preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_artifact_edit_service.apply_artifact_edit_preview(
            report,
            draft_id=draft_id,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactEditApplyResponse(
        operation="edit_report_artifact",
        operation_result="success",
        draft=ReportArtifactEditPreviewResponse(**result["draft"]),
        report=result["report"],
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews",
    response_model=ReportArtifactRollbackPreviewResponse,
)
async def create_report_artifact_rollback_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    body: ReportArtifactRollbackPreviewRequest,
    user: dict = Depends(require_role("admin")),
):
    """Create a bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.create_artifact_rollback_preview(
            report,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackPreviewResponse(**preview)


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews/{preview_id}",
    response_model=ReportArtifactRollbackPreviewResponse,
)
async def get_report_artifact_rollback_preview(
    parent_id: str,
    student_id: str,
    week_start: str,
    preview_id: str,
    user: dict = Depends(require_role("admin")),
):
    """Read a bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        preview = report_artifact_edit_service.get_artifact_rollback_preview(report, preview_id)
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackPreviewResponse(**preview)


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/artifact-rollback-previews/{preview_id}/apply",
    response_model=ReportArtifactRollbackApplyResponse,
)
async def apply_report_artifact_rollback_preview(
    request: Request,
    parent_id: str,
    student_id: str,
    week_start: str,
    preview_id: str,
    body: ReportArtifactRollbackApplyRequest,
    user: dict = Depends(require_role("admin")),
):
    """Apply one bounded report artifact rollback preview."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        result = report_artifact_edit_service.apply_artifact_rollback_preview(
            report,
            preview_id=preview_id,
            operator=_operator_id(user),
            reason=body.reason,
            correlation_id=_request_id(request),
        )
    except report_artifact_edit_service.ReportArtifactEditError as exc:
        raise _report_artifact_edit_http_error(exc) from exc
    return ReportArtifactRollbackApplyResponse(
        operation="rollback_report_artifact",
        operation_result="success",
        preview=ReportArtifactRollbackPreviewResponse(**result["preview"]),
        report=result["report"],
    )


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/audit",
    response_model=ReportAuditListResponse,
)
async def list_report_audit_events(
    parent_id: str,
    student_id: str,
    week_start: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List append-only audit events for one report recovery timeline."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    try:
        last_key = report_repo.decode_audit_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    result = report_repo.list_report_audit_events(report["report_id"], limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in result.get("Items", [])]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(result.get("LastEvaluatedKey")),
        scope="report",
    )


@router.get(
    "/reports/recovery-jobs/{job_id}/audit",
    response_model=ReportAuditListResponse,
)
async def list_recovery_job_audit_events(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    """List append-only audit events for a report recovery job timeline."""
    try:
        last_key = report_repo.decode_audit_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc

    result = report_repo.list_recovery_job_audit_events(job_id, limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in result.get("Items", [])]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=report_repo.encode_audit_page_token(result.get("LastEvaluatedKey")),
        scope="recovery_job",
    )


def _get_report_or_404(parent_id: str, student_id: str, week_start: str) -> dict:
    report = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _export_recovery_job_evidence(
    *,
    job_id: str,
    request_id: str | None,
    include_targets: bool,
    include_job_audit: bool,
    target_limit: int,
    audit_limit: int,
    next_target_token: str | None,
    next_audit_token: str | None,
) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")

    targets: list[dict] = []
    target_next_token = None
    if include_targets:
        target_last_key = report_repo.decode_recovery_job_page_token(next_target_token)
        target_result = report_repo.list_recovery_job_targets(
            job_id,
            limit=target_limit,
            last_key=target_last_key,
        )
        targets = target_result.get("Items", [])
        target_next_token = report_repo.encode_recovery_job_page_token(target_result.get("LastEvaluatedKey"))

    job_audit: list[dict] = []
    audit_next_token = None
    if include_job_audit:
        audit_last_key = report_repo.decode_audit_page_token(next_audit_token)
        audit_result = report_repo.list_recovery_job_audit_events(
            job_id,
            limit=audit_limit,
            last_key=audit_last_key,
        )
        job_audit = audit_result.get("Items", [])
        audit_next_token = report_repo.encode_audit_page_token(audit_result.get("LastEvaluatedKey"))

    return report_recovery_evidence_service.build_export_response(
        scope="recovery_job",
        request_id=request_id,
        filters={
            "job_id": job_id,
            "include_targets": include_targets,
            "include_job_audit": include_job_audit,
            "target_limit": target_limit,
            "audit_limit": audit_limit,
        },
        jobs=[job],
        targets=targets,
        job_audit=job_audit,
        next_tokens={
            "targets": target_next_token,
            "job_audit": audit_next_token,
        },
    )


def _export_recovery_job_support_package(
    *,
    job_id: str,
    request_id: str | None,
    include_targets: bool,
    include_job_audit: bool,
    include_report_audit: bool,
    target_limit: int,
    audit_limit: int,
    next_target_token: str | None,
    next_audit_token: str | None,
    operator_note: str | None,
) -> dict[str, Any]:
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Recovery job not found")
    source_job = None
    source_job_id = job.get("source_job_id")
    if source_job_id:
        source_job = report_repo.get_recovery_job(str(source_job_id))

    targets: list[dict] = []
    target_next_token = None
    if include_targets or include_report_audit:
        target_last_key = report_repo.decode_recovery_job_page_token(next_target_token)
        target_result = report_repo.list_recovery_job_targets(
            job_id,
            limit=target_limit,
            last_key=target_last_key,
        )
        targets = target_result.get("Items", [])
        target_next_token = report_repo.encode_recovery_job_page_token(target_result.get("LastEvaluatedKey"))

    job_audit: list[dict] = []
    audit_next_token = None
    if include_job_audit:
        audit_last_key = report_repo.decode_audit_page_token(next_audit_token)
        audit_result = report_repo.list_recovery_job_audit_events(
            job_id,
            limit=audit_limit,
            last_key=audit_last_key,
        )
        job_audit = audit_result.get("Items", [])
        audit_next_token = report_repo.encode_audit_page_token(audit_result.get("LastEvaluatedKey"))

    report_audit: list[dict] = []
    if include_report_audit:
        remaining = audit_limit
        for target in targets:
            if remaining <= 0:
                break
            report_id = target.get("report_id")
            if not report_id:
                continue
            audit_result = report_repo.list_report_audit_events(str(report_id), limit=remaining)
            events = audit_result.get("Items", [])
            report_audit.extend(events)
            remaining -= len(events)

    return report_recovery_evidence_service.build_support_package_response(
        request_id=request_id,
        job=job,
        source_job=source_job,
        targets=targets if include_targets else [],
        job_audit=job_audit,
        report_audit=report_audit,
        operator_note=operator_note,
        next_tokens={
            "targets": target_next_token if include_targets else None,
            "job_audit": audit_next_token,
            "report_audit": None,
        },
    )


def _export_recent_recovery_jobs(
    *,
    request_id: str | None,
    status: str | None,
    limit: int,
    next_token: str | None,
) -> dict[str, Any]:
    last_key = report_repo.decode_recovery_job_page_token(next_token)
    result = report_repo.list_recovery_jobs(limit=limit, last_key=last_key)
    jobs = result.get("Items", [])
    if status:
        jobs = [job for job in jobs if job.get("status") == status]
    return report_recovery_evidence_service.build_export_response(
        scope="recent_recovery_jobs",
        request_id=request_id,
        filters={
            "status": status,
            "limit": limit,
        },
        jobs=jobs,
        next_tokens={
            "jobs": report_repo.encode_recovery_job_page_token(result.get("LastEvaluatedKey")),
        },
    )


def _request_id(request: Request) -> str | None:
    for header in ("x-request-id", "x-amzn-requestid", "x-amzn-trace-id", "x-correlation-id"):
        value = request.headers.get(header)
        if value:
            return report_recovery_service.redact_private_artifact_text(value)[:240]
    return None


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
            "generation_error_message": report_recovery_service.redact_private_artifact_text(
                report.get("generation_error_message")
            ),
        },
        delivery={
            "parent_email": report.get("parent_email"),
            "email_sent_at": report.get("email_sent_at"),
            "email_failed_at": report.get("email_failed_at"),
            "email_error_class": report.get("email_error_class"),
            "email_error_message": report_recovery_service.redact_private_artifact_text(
                report.get("email_error_message")
            ),
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
        "edit_artifact": {
            "enabled": bool(report.get("json_s3_key") and (report.get("html_s3_key") or report.get("s3_key"))),
            "reason": None
            if report.get("json_s3_key") and (report.get("html_s3_key") or report.get("s3_key"))
            else "Report is missing editable artifacts",
        },
        "rollback_artifact": {
            "enabled": bool(
                report.get("json_s3_key")
                and (report.get("html_s3_key") or report.get("s3_key"))
                and report.get("previous_json_s3_key")
                and report.get("previous_html_s3_key")
            ),
            "reason": None
            if (
                report.get("json_s3_key")
                and (report.get("html_s3_key") or report.get("s3_key"))
                and report.get("previous_json_s3_key")
                and report.get("previous_html_s3_key")
            )
            else "Report is missing rollback artifact metadata",
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


def _report_recovery_http_error(exc: report_recovery_service.ReportRecoveryError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report recovery operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)


def _recovery_job_http_error(exc: report_recovery_job_service.RecoveryJobError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Recovery job operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)


def _report_edit_http_error(exc: report_edit_service.ReportEditError) -> HTTPException:
    detail = report_recovery_service.redact_private_artifact_text(exc.detail) or "Report edit operation failed"
    return HTTPException(status_code=exc.status_code, detail=detail)


def _report_artifact_edit_http_error(
    exc: report_artifact_edit_service.ReportArtifactEditError,
) -> HTTPException:
    detail = (
        report_recovery_service.redact_private_artifact_text(exc.detail)
        or "Report artifact edit operation failed"
    )
    return HTTPException(status_code=exc.status_code, detail=detail)


def _recovery_job_response(job: dict) -> RecoveryJobResponse:
    return RecoveryJobResponse(
        job_id=str(job.get("job_id", "")),
        job_type=str(job.get("job_type", "")),
        status=str(job.get("status", "")),
        reason=report_recovery_service.redact_private_artifact_text(job.get("reason")),
        created_by=job.get("created_by"),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        cancellation_requested_by=job.get("cancellation_requested_by"),
        cancellation_requested_at=job.get("cancellation_requested_at"),
        filters=_redact_audit_metadata(job.get("filters")),
        target_count=int(job.get("target_count") or 0),
        pending_count=int(job.get("pending_count") or 0),
        attempted_count=int(job.get("attempted_count") or 0),
        success_count=int(job.get("success_count") or 0),
        refused_count=int(job.get("refused_count") or 0),
        not_found_count=int(job.get("not_found_count") or 0),
        failed_count=int(job.get("failed_count") or 0),
        skipped_cancelled_count=int(job.get("skipped_cancelled_count") or 0),
        stop_reason=job.get("stop_reason"),
        source_job_id=job.get("source_job_id"),
        resume_result_filters=job.get("resume_result_filters"),
    )


def _recovery_job_target_response(item: dict) -> RecoveryJobTargetResponse:
    return RecoveryJobTargetResponse(
        target_id=str(item.get("target_id", "")),
        report_id=item.get("report_id"),
        parent_id=item.get("parent_id"),
        student_id=item.get("student_id"),
        student_name=item.get("student_name"),
        week_start=item.get("week_start"),
        result=str(item.get("result", "")),
        status=item.get("status"),
        email_status=item.get("email_status"),
        detail=report_recovery_service.redact_private_artifact_text(item.get("detail")),
        error_class=item.get("error_class"),
        attempted_at=item.get("attempted_at"),
        completed_at=item.get("completed_at"),
    )


def _report_audit_event_response(item: dict) -> ReportAuditEventResponse:
    return ReportAuditEventResponse(
        event_id=str(item.get("event_id", "")),
        event_at=str(item.get("event_at", "")),
        report_id=item.get("report_id"),
        parent_id=item.get("parent_id"),
        student_id=item.get("student_id"),
        week_start=item.get("week_start"),
        actor=item.get("actor"),
        action=str(item.get("action", "")),
        reason=item.get("reason"),
        source=item.get("source"),
        result=str(item.get("result", "")),
        before=_redact_audit_metadata(item.get("before")),
        after=_redact_audit_metadata(item.get("after")),
        error_class=item.get("error_class"),
        error_message=report_recovery_service.redact_private_artifact_text(item.get("error_message")),
        correlation_id=item.get("correlation_id"),
    )


def _redact_audit_metadata(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        str(key): report_recovery_service.redact_private_artifact_text(raw) if isinstance(raw, str) else raw
        for key, raw in value.items()
        if not str(key).endswith("_s3_key") and str(key) != "s3_key"
    }
