"""Admin report recovery jobs: preview, create, resume, list and cancel."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from stoa.db import listing_index
from stoa.db.repositories import report_repo
from stoa.security.admin_authorization import (
    AdminTargetProvider,
    admin_operation,
    admin_target_provider,
)
from stoa.security.identity import Actor
from stoa.services.report_recovery_errors import RecoveryJobError, ReportRecoveryErrorCode
from stoa.services import (
    report_recovery_job_service,
    report_recovery_service,
)
from stoa.routers.admin._common import (
    _admin_items,
    _in_partition,
    _next_token,
    _start_key,
    RECOVERY_JOBS_SCOPE,
)
from stoa.routers.admin.report_schemas import (
    _redact_audit_metadata,
    _report_audit_event_response,
    RecoveryJobCreateRequest,
    RecoveryJobListResponse,
    RecoveryJobPreviewRequest,
    RecoveryJobPreviewResponse,
    RecoveryJobResponse,
    RecoveryJobResumeCreateRequest,
    RecoveryJobResumePreviewRequest,
    RecoveryJobResumePreviewResponse,
    RecoveryJobTargetResponse,
    RecoveryJobTargetsResponse,
    ReportAuditListResponse,
)


router = APIRouter()


RECOVERY_FILTER_TARGETS = AdminTargetProvider(
    "resolver_collection", "request",
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    maximum=25,
    reference_only=("reason", "max_targets", "preview_token", "filters.status"),
    resolver="report_recovery_filters",
)


RECOVERY_FILTER_PREVIEW_TARGETS = AdminTargetProvider(
    "resolver_collection", "request",
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    ("filters.parent_id", "filters.student_id", "filters.week_start"),
    maximum=25,
    required=False,
    reference_only=("reason", "max_targets", "filters.status"),
    resolver="report_recovery_filters",
)


RECOVERY_RESUME_TARGETS = AdminTargetProvider(
    "resolver_collection", "request", (),
    ("parent_id", "student_id", "week_start", "report_id"),
    maximum=25,
    reference_only=("reason", "results", "max_targets", "preview_token"),
    resolver="report_recovery_resume",
)


RECOVERY_RESUME_PREVIEW_TARGETS = AdminTargetProvider(
    "resolver_collection", "request", (),
    ("parent_id", "student_id", "week_start", "report_id"),
    maximum=25,
    required=False,
    reference_only=("reason", "results", "max_targets"),
    resolver="report_recovery_resume",
)


@router.post(
    "/reports/recovery-jobs/resend-email/preview",
    response_model=RecoveryJobPreviewResponse,
)
@admin_target_provider(RECOVERY_FILTER_PREVIEW_TARGETS)
async def preview_resend_recovery_job(
    request: RecoveryJobPreviewRequest,
    actor: Actor = Depends(admin_operation),
):
    """Preview a bounded async resend recovery job before mutation."""
    return report_recovery_job_service.preview_resend_job(
        reason=request.reason,
        operator=actor.user_id,
        filters=request.filters.model_dump(),
        max_targets=request.max_targets,
    )


@router.post(
    "/reports/recovery-jobs/resend-email",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_FILTER_TARGETS)
async def create_resend_recovery_job(
    request: RecoveryJobCreateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Create a bounded async resend recovery job after preview confirmation."""
    job = report_recovery_job_service.create_resend_job(
        reason=request.reason,
        operator=actor.user_id,
        filters=request.filters.model_dump(),
        preview_token=request.preview_token,
        max_targets=request.max_targets,
    )
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/retry-generation/preview",
    response_model=RecoveryJobPreviewResponse,
)
@admin_target_provider(RECOVERY_FILTER_PREVIEW_TARGETS)
async def preview_generation_retry_recovery_job(
    request: RecoveryJobPreviewRequest,
    actor: Actor = Depends(admin_operation),
):
    """Preview a bounded async generation retry recovery job before mutation."""
    return report_recovery_job_service.preview_generation_retry_job(
        reason=request.reason,
        operator=actor.user_id,
        filters=request.filters.model_dump(),
        max_targets=request.max_targets,
    )


@router.post(
    "/reports/recovery-jobs/retry-generation",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_FILTER_TARGETS)
async def create_generation_retry_recovery_job(
    request: RecoveryJobCreateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Create a bounded async generation retry recovery job after preview confirmation."""
    job = report_recovery_job_service.create_generation_retry_job(
        reason=request.reason,
        operator=actor.user_id,
        filters=request.filters.model_dump(),
        preview_token=request.preview_token,
        max_targets=request.max_targets,
    )
    return _recovery_job_response(job)


@router.post(
    "/reports/recovery-jobs/{job_id}/resume/preview",
    response_model=RecoveryJobResumePreviewResponse,
)
@admin_target_provider(RECOVERY_RESUME_PREVIEW_TARGETS)
async def preview_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumePreviewRequest,
    actor: Actor = Depends(admin_operation),
):
    """Preview a bounded resume job from a prior recovery job target subset."""
    return report_recovery_job_service.preview_resume_job(
        source_job_id=job_id,
        reason=request.reason,
        operator=actor.user_id,
        results=request.results,
        max_targets=request.max_targets,
    )


@router.post(
    "/reports/recovery-jobs/{job_id}/resume",
    response_model=RecoveryJobResponse,
)
@admin_target_provider(RECOVERY_RESUME_TARGETS)
async def create_resume_recovery_job(
    job_id: str,
    request: RecoveryJobResumeCreateRequest,
    actor: Actor = Depends(admin_operation),
):
    """Create a bounded resume job from a prior recovery job target subset."""
    job = report_recovery_job_service.create_resume_job(
        source_job_id=job_id,
        reason=request.reason,
        operator=actor.user_id,
        results=request.results,
        preview_token=request.preview_token,
        max_targets=request.max_targets,
    )
    return _recovery_job_response(job)


@router.get("/reports/recovery-jobs", response_model=RecoveryJobListResponse)
async def list_recovery_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """List async report recovery jobs."""
    indexed = report_repo.recovery_jobs_indexed()
    scope = f"{RECOVERY_JOBS_SCOPE}:listing" if indexed else RECOVERY_JOBS_SCOPE
    last_key = (
        _start_key(
            next_token,
            scope,
            key=listing_index.INDEX_KEY,
            within=lambda key: key["listing"] == report_repo.RECOVERY_JOB_LISTING,
        )
        if indexed
        else _start_key(next_token, scope)
    )
    result = report_repo.list_recovery_jobs(limit=limit, last_key=last_key, indexed=indexed)
    items = [_recovery_job_response(item) for item in _admin_items(result)]
    return RecoveryJobListResponse(
        items=items,
        count=len(items),
        next_token=_next_token(scope, result),
    )


@router.get("/reports/recovery-jobs/{job_id}", response_model=RecoveryJobResponse)
async def get_recovery_job(
    job_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Get one async report recovery job."""
    job = report_repo.get_recovery_job(job_id)
    if not job:
        raise RecoveryJobError(ReportRecoveryErrorCode.RECOVERY_JOB_NOT_FOUND)
    return _recovery_job_response(job)


@router.get("/reports/recovery-jobs/{job_id}/results", response_model=RecoveryJobTargetsResponse)
async def list_recovery_job_results(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """List metadata-only target results for one async recovery job."""
    if not report_repo.get_recovery_job(job_id):
        raise RecoveryJobError(ReportRecoveryErrorCode.RECOVERY_JOB_NOT_FOUND)
    scope = f"recovery_job_targets:{job_id}"
    last_key = _start_key(
        next_token, scope, within=_in_partition(f"REPORT_RECOVERY_JOB#{job_id}", "TARGET#")
    )
    result = report_repo.list_recovery_job_targets(job_id, limit=limit, last_key=last_key)
    items = [_recovery_job_target_response(item) for item in _admin_items(result)]
    return RecoveryJobTargetsResponse(
        items=items,
        count=len(items),
        next_token=_next_token(scope, result),
    )


@router.post("/reports/recovery-jobs/{job_id}/cancel", response_model=RecoveryJobResponse)
async def cancel_recovery_job(
    job_id: str,
    actor: Actor = Depends(admin_operation),
):
    """Request cooperative cancellation for an async report recovery job."""
    job = report_recovery_job_service.cancel_recovery_job(job_id, operator=actor.user_id)
    return _recovery_job_response(job)


@router.get(
    "/reports/recovery-jobs/{job_id}/audit",
    response_model=ReportAuditListResponse,
)
async def list_recovery_job_audit_events(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """List append-only audit events for a report recovery job timeline."""
    partition = f"REPORT_RECOVERY_JOB#{job_id}"
    scope = f"report_audit:{partition}"
    last_key = _start_key(next_token, scope, within=_in_partition(partition, "AUDIT#"))

    result = report_repo.list_recovery_job_audit_events(job_id, limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in _admin_items(result)]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=_next_token(scope, result),
        scope="recovery_job",
    )


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
        code=item.get("code") or None,
        params=report_recovery_job_service.stored_params(item.get("params")),
        detail=report_recovery_job_service.outcome_message(item),
        error_class=item.get("error_class"),
        attempted_at=item.get("attempted_at"),
        completed_at=item.get("completed_at"),
    )
