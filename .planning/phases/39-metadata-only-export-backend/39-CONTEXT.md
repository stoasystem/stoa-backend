# Phase 39: Metadata-only Export Backend

**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Ready for implementation
**Created:** 2026-06-05

## Goal

Implement an admin-only read-only backend export endpoint for recovery evidence using the Phase 38 export contract.

## Requirements

- EXPORT-01: admin-only bounded metadata export for recovery job, target, result, and audit evidence.
- EXPORT-02: export privacy boundary that omits private S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, and artifact payloads.
- EXPORT-03: read-only export observability and evidence logging.

## Locked Decisions From Phase 38

- API path: `GET /admin/reports/recovery-evidence`.
- Exact `job_id` export is the preferred implementation path.
- Recent jobs export may reuse existing bounded recovery job list behavior.
- No CDK change is required for the MVP.
- No new AWS services, table, bucket, Lambda, queue, or GSI.
- Export payloads must use explicit allowlists.
- Export endpoint must not create recovery jobs, update reports/jobs/targets, retry generation, resend email, invoke workers, or touch S3.

## Relevant Code

- `src/stoa/routers/admin.py`
- `src/stoa/db/repositories/report_repo.py`
- `src/stoa/services/report_recovery_service.py`
- `tests/test_admin_report_ops.py`

## Verification Targets

- Non-admin callers receive 403 and repository functions are not called.
- Exact job export returns job, target, and audit metadata only.
- Recent jobs export is bounded and returns metadata only.
- Invalid pagination tokens return 400.
- Missing job returns 404.
- Oversized/unbounded parameters are rejected by FastAPI validation.
- Serialized responses omit `weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, presigned URLs, raw report HTML/JSON, and auth/session token markers.
- Focused backend tests pass.
