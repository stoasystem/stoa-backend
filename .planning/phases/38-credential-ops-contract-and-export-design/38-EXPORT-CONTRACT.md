# Phase 38 Export Contract: Recovery Evidence

**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Ready for Phase 39 implementation
**Created:** 2026-06-05

## Goal

Provide admin-only metadata export for recovery jobs, targets, and audit evidence without exposing private report artifacts or creating a new recovery mutation path.

## Proposed API

Phase 39 should implement a read-only endpoint under the existing admin router:

```text
GET /admin/reports/recovery-evidence
```

Supported query modes:

| Mode | Required params | Optional params | Notes |
|------|-----------------|-----------------|-------|
| One job | `job_id` | `include_targets`, `include_job_audit`, `target_limit`, `audit_limit`, `next_target_token`, `next_audit_token` | Preferred exact evidence path |
| Recent jobs page | none | `limit`, `next_token`, `status` | Uses existing bounded recovery job list pattern |
| Time window | `from`, `to` | `limit`, `max_scan_pages`, `status` | Allowed only with bounded scan cap and `complete=false` when cap is reached |

If `job_id` is present, the endpoint must not scan for jobs. It should read the job summary by key, then query targets/audit by job partition as requested.

## Bounds

Recommended defaults:

| Parameter | Default | Maximum |
|-----------|---------|---------|
| `limit` | 25 | 100 |
| `target_limit` | 50 | 100 |
| `audit_limit` | 50 | 100 |
| `max_scan_pages` | 2 | 5 |

Rules:

- Reject requests with neither `job_id` nor an explicit bounded recent/time-window mode if Phase 39 chooses to require a `scope` param.
- Reject invalid pagination tokens with 400.
- Return `complete=false` and a continuation token when bounded scans do not exhaust the candidate set.
- Do not silently run unbounded full-table scans.

## Response Shape

Top-level response:

```json
{
  "exported_at": "2026-06-05T08:00:00Z",
  "request_id": "redacted-api-request-id",
  "scope": "recovery_job",
  "complete": true,
  "filters": {
    "job_id": "job-123"
  },
  "jobs": [],
  "targets": [],
  "job_audit": [],
  "report_audit": [],
  "next_tokens": {
    "jobs": null,
    "targets": null,
    "job_audit": null,
    "report_audit": null
  },
  "privacy": {
    "metadata_only": true,
    "private_artifact_fields_omitted": true
  }
}
```

`report_audit` should remain empty unless the request includes a precise report identity or Phase 39 adds a safe target-to-report audit expansion with explicit caps.

## Allowlisted Fields

### Job Summary

- `job_id`
- `job_type`
- `status`
- `reason` after redaction
- `created_by`
- `created_at`
- `updated_at`
- `started_at`
- `completed_at`
- `cancellation_requested_by`
- `cancellation_requested_at`
- `filters` after redaction
- `target_count`
- `pending_count`
- `attempted_count`
- `success_count`
- `refused_count`
- `not_found_count`
- `failed_count`
- `skipped_cancelled_count`
- `stop_reason`

### Target Summary

- `target_id`
- `report_id`
- `parent_id`
- `student_id`
- `student_name`
- `week_start`
- `result`
- `status`
- `email_status`
- `detail` after redaction
- `error_class`
- `attempted_at`
- `completed_at`

### Audit Summary

- `event_id`
- `event_at`
- `report_id`
- `parent_id`
- `student_id`
- `week_start`
- `actor`
- `action`
- `reason` after redaction
- `source`
- `result`
- `before` after redaction
- `after` after redaction
- `error_class`
- `error_message` after redaction
- `correlation_id`

## Explicit Denylist

Export responses, logs, UI render paths, and test fixtures must not include:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `s3_key`
- Any field ending in `_s3_key`
- Presigned URLs
- Public S3 URLs
- Raw report JSON
- Raw report HTML
- Cognito access tokens
- Cognito ID tokens
- Refresh tokens
- Browser cookies
- Browser local/session storage
- Full raw DynamoDB items

Phase 39 tests should assert these strings and fields are absent from serialized responses.

## Read-only Semantics

The export endpoint must not:

- Create recovery jobs.
- Update recovery jobs.
- Update recovery job targets.
- Update report summary items.
- Retry generation.
- Resend email.
- Invoke Lambda workers.
- Read S3 report artifacts.
- Write S3 report artifacts.

If Phase 39 adds an audit event for export access, it must be a read-only evidence access event. It must not reuse mutation action names such as `resend_email`, `retry_generation`, `create_resend_job`, or `request_cancellation`.

## Existing Resource Fit

Existing backend building blocks are sufficient for the v1.7 MVP if Phase 39 keeps the exact job export path primary:

- `report_repo.get_recovery_job(job_id)` reads one job summary by key.
- `report_repo.list_recovery_job_targets(job_id, limit, last_key)` queries one job partition.
- `report_repo.list_recovery_job_audit_events(job_id, limit, last_key)` queries one job partition.
- Admin router response helpers already serialize job, target, and audit metadata through allowlisted Pydantic models.
- `_redact_audit_metadata` already strips keys ending in `_s3_key` and `s3_key`.
- `report_recovery_service.redact_private_artifact_text` already redacts private artifact text in string fields.

Known constraint:

- `report_repo.list_recovery_jobs` currently uses a bounded table scan with a filter for recovery job summaries. This is acceptable for small release-gate recent-page evidence only when capped, but it is not a scalable incident-wide export primitive.

CDK decision:

- No CDK change is required for Phase 39 MVP if implementation reuses the existing API Lambda, DynamoDB table, Cognito admin auth, and frontend admin route.
- A new GSI or orchestration resource remains out of scope unless Phase 39 proves bounded export cannot satisfy operator needs.

## Implementation Recommendation For Phase 39

- Add a small service module, for example `src/stoa/services/report_recovery_evidence_service.py`, to keep route handlers thin and make allowlist tests direct.
- Reuse existing router response helpers or extract them into shared serializers if circular imports can be avoided cleanly.
- Prefer `job_id` export first, then recent jobs page export.
- Treat time-window export as best-effort bounded evidence with `complete=false` when scan caps are reached.
- Add tests in `tests/test_admin_report_ops.py` for admin-only access, non-admin rejection, bounds, read-only behavior, and denylist absence.
