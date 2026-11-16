"""Request and response models of the admin report routes, and their shared projections."""

from typing import Any

from pydantic import BaseModel, Field

from stoa.security.admin_authorization import AdminTargetProvider
from stoa.services import report_recovery_service


HANDOFF_FIXTURE_TARGET = AdminTargetProvider(
    "scalar", "body",
    ("fixture.parent_id", "fixture.student_id", "fixture.week_start"),
    ("fixture.parent_id", "fixture.student_id", "fixture.week_start"),
    required=False,
    reference_only=("reason", "operator_note", "release_evidence", "fixture.fixture_name"),
    resolver="support_handoff",
)


GOVERNANCE_REFERENCE_TARGETS = AdminTargetProvider(
    "collection", "body",
    ("references.job_id", "references.parent_id", "references.student_id", "references.week_start"),
    ("references.job_id", "references.parent_id", "references.student_id", "references.week_start"),
    maximum=10,
    required=False,
    collection_path="references",
    reference_only=("reason", "release_evidence", "break_glass", "evidence_references"),
)


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
    code: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
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
    code: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
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
    code: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    detail: str | None = None
    error_class: str | None = None
    attempted_at: str | None = None
    completed_at: str | None = None


class RecoveryJobTargetsResponse(BaseModel):
    items: list[RecoveryJobTargetResponse]
    count: int
    next_token: str | None = None


class SupportHandoffFixtureReference(BaseModel):
    fixture_name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = None
    student_id: str | None = None
    week_start: str | None = None
    expected_artifact_version: str | None = None


class SupportHandoffPackageRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    destination_mode: str = Field(default="preview", min_length=1, max_length=50)
    recovery_job_ids: list[str] = Field(default_factory=list, max_length=5)
    include_targets: bool = True
    include_job_audit: bool = True
    include_report_audit: bool = False
    target_limit: int = Field(default=50, ge=1, le=100)
    audit_limit: int = Field(default=50, ge=1, le=100)
    release_evidence: dict[str, Any] | None = None
    fixture: SupportHandoffFixtureReference | None = None
    operator_note: str | None = Field(default=None, max_length=1000)


class SupportHandoffRetryRequest(BaseModel):
    reason: str = Field(default="retry provider delivery", min_length=1, max_length=500)


class SupportHandoffProviderSyncRequest(BaseModel):
    provider_event_id: str = Field(..., min_length=1, max_length=200)
    provider_status: str = Field(..., min_length=1, max_length=100)
    provider_updated_at: str = Field(..., min_length=1, max_length=100)
    provider_assignee: str | None = Field(default=None, max_length=200)
    provider_priority: str | None = Field(default=None, max_length=100)


class SupportHandoffMessageRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=100)
    destination: str = Field(default="customer_email", min_length=1, max_length=100)
    trigger: str = Field(default="manual", min_length=1, max_length=100)
    customer_opted_out: bool = False


class AuditRetentionReference(BaseModel):
    scope: str = Field(..., min_length=1, max_length=50)
    job_id: str | None = Field(default=None, max_length=200)
    parent_id: str | None = Field(default=None, max_length=200)
    student_id: str | None = Field(default=None, max_length=200)
    week_start: str | None = Field(default=None, max_length=50)
    package_id: str | None = Field(default=None, max_length=200)
    release_evidence: dict[str, Any] | None = None


class AuditRetentionStatusRequest(BaseModel):
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    limit: int = Field(default=10, ge=1, le=10)


class AuditRetentionManifestRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    retention_category: str = Field(default="operational", min_length=1, max_length=50)
    retention_action: str = Field(default="seal_metadata", min_length=1, max_length=50)
    target_limit: int = Field(default=25, ge=1, le=100)
    audit_limit: int = Field(default=25, ge=1, le=100)


class ImmutableEvidencePersistRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    retention_category: str = Field(default="operational", min_length=1, max_length=50)
    target_limit: int = Field(default=25, ge=1, le=100)
    audit_limit: int = Field(default=25, ge=1, le=100)


class LegalHoldMetadataRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    action: str = Field(default="apply", min_length=1, max_length=50)
    policy_id: str = Field(default="operational-default", min_length=1, max_length=100)


class RetentionGovernanceStatusRequest(BaseModel):
    policy_version: str = Field(default="retention-policy-v1", min_length=1, max_length=120)
    references: list[AuditRetentionReference] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=10)


class RetentionApprovalMetadataRequest(BaseModel):
    policy_version: str = Field(..., min_length=1, max_length=120)
    retention_mode: str = Field(..., min_length=1, max_length=50)
    retention_days: int = Field(..., ge=1, le=3650)
    policy_owner: str = Field(..., min_length=1, max_length=200)
    legal_compliance_approver: str = Field(..., min_length=1, max_length=200)
    approval_state: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=1, max_length=500)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    next_review_due_at: str | None = Field(default=None, max_length=80)


class LegalHoldReviewMetadataRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    references: list[AuditRetentionReference] = Field(..., min_length=1, max_length=10)
    owner: str = Field(..., min_length=1, max_length=200)
    reviewer: str = Field(..., min_length=1, max_length=200)
    review_cadence: str = Field(..., min_length=1, max_length=100)
    outcome: str = Field(default="reviewed", min_length=1, max_length=50)
    next_review_due_at: str | None = Field(default=None, max_length=80)
    break_glass: dict[str, Any] | None = None


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
