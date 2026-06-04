---
phase: 25
phase_name: Bulk Email Resend Recovery
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 25: Bulk Email Resend Recovery - Context

## Phase Boundary

Build a backend admin recovery path for selected `email_failed` weekly reports.

This phase delivers:

- Admin-only bulk resend endpoint for selected parent/student/week report identifiers.
- Backend-enforced batch size cap.
- Independent per-report validation and result reporting.
- Reuse of private HTML artifacts through backend-mediated S3 reads.
- Per-report resend audit fields for success and failure.
- Focused backend tests.

This phase does not implement frontend UI, large asynchronous incident jobs, regeneration of successful reports, or live verification.

## Decisions

### Endpoint Shape

- Add `POST /admin/reports/bulk-resend`.
- Request body uses `reports: [{ parent_id, student_id, week_start }]`.
- Enforce a maximum of 25 selected reports per request.
- Preserve input order in the result list.

### Result Semantics

- `success`: report was `email_failed`, private HTML artifact was read by the backend, and email send succeeded.
- `refused`: report exists but is not eligible for resend or is missing email/artifact metadata.
- `not_found`: no report exists for the selected parent/student/week.
- `failed`: report was eligible but backend artifact read or email send failed.

### Audit Fields

- Reuse the existing single-report resend audit fields:
  - `resend_attempted_at`
  - `resend_completed_at` on success
  - `email_failed_at` on failure
  - `last_operation=resend_email`
  - `last_operation_result=success|failed`
  - `last_operation_by`
  - `last_operation_at`
  - `updated_at`

## Code Context

- `src/stoa/routers/admin.py` already has a single-report resend endpoint.
- Existing resend path reads private HTML through `report_artifact_service.get_report_html`.
- Existing resend path sends email through `notify_service.send_weekly_report_email`.
- Existing helper `_safe_error_message` redacts private report artifact paths before persistence.

## Deferred Ideas

- Async incident-wide resend job.
- Immutable audit log table.
- Admin UI bulk selection and result rendering, covered by Phase 26.
