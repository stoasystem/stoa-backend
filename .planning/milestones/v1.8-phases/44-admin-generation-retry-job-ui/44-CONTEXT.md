# Phase 44 Context

**Phase:** 44 - Admin Generation Retry Job UI
**Milestone:** v1.8 Incident Generation Retry Jobs
**Created:** 2026-06-05

## Context

Phase 43 added backend support for async `retry_generation` recovery jobs:

- `POST /admin/reports/recovery-jobs/retry-generation/preview`
- `POST /admin/reports/recovery-jobs/retry-generation`
- worker event `report_recovery_retry_generation`
- job/audit/result records using `job_type=retry_generation`

The admin frontend already had a resend-only async recovery job panel in `/admin/report-operations`. Phase 44 extends that panel to support both existing resend jobs and new generation retry jobs without exposing private report artifacts.

## Constraints

- Preserve existing resend UI behavior.
- Keep preview payloads metadata-only.
- Do not expose `weekly-reports/`, S3 keys, presigned URLs, raw JSON, or raw HTML.
- Keep job type labels explicit enough that admins do not confuse resend and generation retry jobs.
- Keep production read-only smoke for Phase 45 free of job creation or mutation.

