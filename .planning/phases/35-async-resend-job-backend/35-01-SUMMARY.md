# Phase 35 Summary

**Status:** Complete
**Completed:** 2026-06-04

## Delivered

- Added async resend recovery job APIs:
  - `POST /admin/reports/recovery-jobs/resend-email/preview`
  - `POST /admin/reports/recovery-jobs/resend-email`
  - `GET /admin/reports/recovery-jobs`
  - `GET /admin/reports/recovery-jobs/{job_id}`
  - `GET /admin/reports/recovery-jobs/{job_id}/results`
  - `POST /admin/reports/recovery-jobs/{job_id}/cancel`
- Added durable job summary and target snapshot rows under `REPORT_RECOVERY_JOB#{job_id}`.
- Added async worker execution through the existing weekly report Lambda using `job=report_recovery_resend_email`.
- Worker rereads targets, checks cancellation, conditionally claims target and report resend state, calls the shared resend service, and records per-target outcomes.
- Added job audit events for creation, run start, target outcomes, cancellation request, and cancellation/completion.
- Added conservative caps: max 25 targets, max 5 scan pages, Lambda time remaining floor, and failure threshold.
- Added API Lambda env `WEEKLY_REPORT_FUNCTION_NAME` and CDK `weekly_report_function.grant_invoke(api_function)`.

## Requirement Status

- JOB-01 through JOB-09: Complete.
- AUDIT-05: Complete for successful, refused, failed, and cancelled backend recovery paths.

## Residual Risk

- The MVP uses bounded scans and existing resources. If production incidents exceed these bounds, a later milestone should consider Step Functions, SQS, a dedicated worker, or a recovery-job GSI.
- Preview confirmation is scope-hash based and revalidates current targets at creation time; it is not a long-lived persisted preview object.
