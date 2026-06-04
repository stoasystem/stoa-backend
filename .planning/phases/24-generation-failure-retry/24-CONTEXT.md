# Phase 24: Generation Failure Retry - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>

## Phase Boundary

Build a backend admin recovery path for one `generation_failed` weekly report.

This phase delivers:

- Admin-only retry endpoint for one parent/student/week report.
- Status validation that only accepts `generation_failed`.
- Retry using existing report generation, artifact storage, and email delivery services.
- Audit/status fields for retry attempt, completion/failure, operator, result, and error metadata.
- Focused backend tests.

This phase does not implement bulk resend, frontend UI, or live verification.

</domain>

<decisions>

## Implementation Decisions

### Retry Path

- Add `POST /admin/reports/{parent_id}/{student_id}/{week_start}/retry-generation`.
- Reuse existing `report_service` functions instead of duplicating generation logic.
- Do not call the scheduled job's `try_claim_report_generation`; the failed report record already exists.
- Keep retry scoped to one report triple only.

### Status Semantics

- Accept only `status == "generation_failed"`.
- Refuse `generated`, `email_sent`, `email_failed`, `generation_claimed`, pending, missing, and unknown statuses with HTTP 409.
- Treat successful artifact generation/storage as retry success even if the subsequent email delivery becomes `email_failed`.

### Audit Fields

- On success, write `generation_retry_attempted_at`, `generation_retry_completed_at`, `last_operation=retry_generation`, `last_operation_result=success`, `last_operation_by`, `last_operation_at`, and `updated_at`.
- On failure, keep status `generation_failed` and write `generation_failed_at`, `generation_error_class`, `generation_error_message`, `generation_retry_attempted_at`, `last_operation=retry_generation`, `last_operation_result=failed`, `last_operation_by`, `last_operation_at`, and `updated_at`.

</decisions>

<code_context>

## Existing Code Insights

- `report_service.store_and_send_weekly_report` writes canonical JSON/HTML artifacts and report metadata, then attempts email delivery.
- `report_service.build_weekly_report_record` and `_report_artifact_keys` preserve canonical report ID and key shape.
- `weekly_reports.run_weekly_report_job` cannot be reused directly because it discovers all pairs and uses a conditional claim path.
- `admin.py` already has `_get_report_or_404`, `_operator_id`, and `_now_iso` helpers.

</code_context>

<specifics>

## Specific Ideas

- Add `ReportGenerationRetryResponse`.
- Add endpoint tests to `tests/test_admin_report_ops.py`.
- Keep test fakes narrow: monkeypatch report repo lookup, report service payload/generate/store, and status update calls.

</specifics>

<deferred>

## Deferred Ideas

- Bulk generation retry.
- Regenerating successful reports.
- Frontend trigger.
- Async job/queue based retry.

</deferred>
