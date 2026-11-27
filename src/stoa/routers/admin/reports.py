"""Admin report operations: listing, resend, generation retry, audit and release evidence."""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from stoa.db import listing_index
from stoa.db.repositories import report_repo
from stoa.security.admin_authorization import (
    AdminTargetProvider,
    admin_operation,
    admin_target_provider,
)
from stoa.security.identity import Actor
from stoa.services.account_errors import AccountErrorCode, AccountViolation
from stoa.services import (
    release_evidence_service,
    report_recovery_job_service,
    report_recovery_service,
)
from stoa.routers.admin._common import (
    _admin_items,
    _admin_reports_scope,
    _admin_required_text,
    _in_partition,
    _next_token,
    _start_key,
    ADMIN_REPORTS_PARENT_KEY,
)
from stoa.routers.admin.report_schemas import (
    _report_audit_event_response,
    BulkReportResendItemResult,
    BulkReportResendRequest,
    BulkReportResendResponse,
    ReportAuditListResponse,
    ReportGenerationRetryResponse,
    ReportOperationListResponse,
    ReportOperationResponse,
    ReportResendResponse,
    ReportResendTarget,
    SupportHandoffFixtureReference,
)


router = APIRouter()


BULK_REPORT_TARGETS = AdminTargetProvider(
    "collection", "request",
    ("reports.parent_id", "reports.student_id", "reports.week_start"),
    ("reports.parent_id", "reports.student_id", "reports.week_start"),
    maximum=25,
    collection_path="reports",
)


@router.get("/reports/ops", response_model=ReportOperationListResponse)
async def list_report_operations(
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    week_start: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    next_token: Optional[str] = Query(default=None),
    actor: Actor = Depends(admin_operation),
):
    """List report operation metadata for admin triage."""
    indexed = False if parent_id else report_repo.reports_indexed()
    scope = report_repo.ADMIN_REPORTS_INDEX_SCOPE if indexed else _admin_reports_scope(parent_id)
    if parent_id:
        last_key = _start_key(
            next_token,
            scope,
            key=ADMIN_REPORTS_PARENT_KEY,
            within=lambda key: key["parent_id"] == parent_id,
        )
    elif indexed:
        last_key = _start_key(
            next_token,
            scope,
            key=listing_index.INDEX_KEY,
            within=lambda key: key["listing"] == report_repo.REPORT_LISTING,
        )
    else:
        last_key = _start_key(next_token, scope)

    result = report_repo.list_reports_for_admin(
        status=status,
        week_start=week_start,
        parent_id=parent_id,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
        indexed=indexed,
    )
    items = [_report_operation_response(report) for report in _admin_items(result)]
    return ReportOperationListResponse(
        items=items,
        count=len(items),
        next_token=_next_token(scope, result),
        access_pattern="parent_gsi" if parent_id else ("listing_index" if indexed else "bounded_scan"),
    )


@router.get(
    "/reports/{parent_id}/{student_id}/{week_start}/ops",
    response_model=ReportOperationResponse,
)
async def get_report_operations(
    parent_id: str,
    student_id: str,
    week_start: str,
    actor: Actor = Depends(admin_operation),
):
    """Inspect report artifact and delivery metadata without exposing artifact content."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    return _report_operation_response(report)


@router.post("/reports/bulk-resend", response_model=BulkReportResendResponse)
@admin_target_provider(BULK_REPORT_TARGETS)
async def bulk_resend_report_emails(
    request: BulkReportResendRequest,
    actor: Actor = Depends(admin_operation),
):
    """Resend selected failed report emails with independent per-item results."""
    operator = actor.user_id
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
                    code=AccountErrorCode.REPORT_NOT_FOUND.value,
                    detail=report_recovery_job_service.outcome_message(
                        {"code": AccountErrorCode.REPORT_NOT_FOUND.value}
                    ),
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


@router.post("/reports/release-evidence/validate")
async def validate_release_evidence(
    bundle: dict[str, Any] = Body(...),
    actor: Actor = Depends(admin_operation),
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
    actor: Actor = Depends(admin_operation),
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
            report_id = _admin_required_text(report.get("report_id"))
            audit_result = report_repo.list_report_audit_events(report_id, limit=10)
            audit_events = _admin_items(audit_result)

    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=expected_artifact_version,
    )


@router.post(
    "/reports/{parent_id}/{student_id}/{week_start}/resend",
    response_model=ReportResendResponse,
)
async def resend_report_email(
    parent_id: str,
    student_id: str,
    week_start: str,
    actor: Actor = Depends(admin_operation),
):
    """Resend a failed report email using the existing private HTML artifact."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    result = report_recovery_service.resend_report_email(
        report,
        operator=actor.user_id,
        reason="admin_single_resend",
    )
    return ReportResendResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=_admin_required_text(result.email_status),
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
    params = report_recovery_job_service.stored_params(dict(exc.params))
    return BulkReportResendItemResult(
        parent_id=target.parent_id,
        student_id=target.student_id,
        week_start=target.week_start,
        result=result,
        report_id=report.get("report_id"),
        status=report.get("status"),
        email_status=report.get("email_status"),
        operation_result=result,
        code=exc.code.value,
        params=params,
        detail=report_recovery_job_service.outcome_message({"code": exc.code.value, "params": params}),
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
    actor: Actor = Depends(admin_operation),
):
    """Retry generation for one generation-failed weekly report."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    result = report_recovery_service.retry_report_generation(
        report,
        parent_id=parent_id,
        student_id=student_id,
        week_start=week_start,
        operator=actor.user_id,
        reason="admin_single_generation_retry",
    )
    return ReportGenerationRetryResponse(
        report_id=result.report_id,
        status=result.status,
        email_status=result.email_status,
        operation=result.operation,
        operation_result=result.operation_result,
        updated_at=result.updated_at,
        artifacts=result.artifacts or {"json_available": False, "html_available": False},
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
    actor: Actor = Depends(admin_operation),
):
    """List append-only audit events for one report recovery timeline."""
    report = _get_report_or_404(parent_id, student_id, week_start)
    report_id = _admin_required_text(report.get("report_id"))
    partition = f"REPORT#{report_id}"
    scope = f"report_audit:{partition}"
    last_key = _start_key(next_token, scope, within=_in_partition(partition, "AUDIT#"))

    result = report_repo.list_report_audit_events(report_id, limit=limit, last_key=last_key)
    items = [_report_audit_event_response(item) for item in _admin_items(result)]
    return ReportAuditListResponse(
        items=items,
        count=len(items),
        next_token=_next_token(scope, result),
        scope="report",
    )


def _get_report_or_404(parent_id: str, student_id: str, week_start: str) -> dict:
    report = report_repo.get_report_for_child_by_week(parent_id, student_id, week_start)
    if not report:
        raise AccountViolation(AccountErrorCode.REPORT_NOT_FOUND)
    return report


def _support_handoff_fixture_response(fixture: SupportHandoffFixtureReference) -> dict[str, Any]:
    approved = release_evidence_service.approved_fixture_config(fixture.fixture_name)
    resolved_parent_id = fixture.parent_id or approved.get("parent_id")
    resolved_student_id = fixture.student_id or approved.get("student_id")
    resolved_week_start = fixture.week_start or approved.get("week_start")
    report = None
    audit_events: list[dict[str, Any]] = []
    if resolved_parent_id and resolved_student_id and resolved_week_start:
        report = report_repo.get_report_for_child_by_week(
            resolved_parent_id,
            resolved_student_id,
            resolved_week_start,
        )
        if report:
            report_id = _admin_required_text(report.get("report_id"))
            audit_result = report_repo.list_report_audit_events(report_id, limit=10)
            audit_events = _admin_items(audit_result)
    return release_evidence_service.build_fixture_inventory_response(
        fixture_name=fixture.fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=fixture.expected_artifact_version,
    )


def _sanitize_request_id(value: object) -> str | None:
    """Bound and redact a caller-supplied correlation header before it is stored."""
    text = report_recovery_service.redact_private_artifact_text(value) or ""
    if release_evidence_service.private_marker_hits(text):
        return "[REDACTED]"
    return text[:240] or None


def _request_id(request: Request) -> str | None:
    for header in ("x-request-id", "x-amzn-requestid", "x-amzn-trace-id", "x-correlation-id"):
        value = request.headers.get(header)
        if value:
            return _sanitize_request_id(value)
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
