# Phase 46 Resume Contract

**Status:** Accepted
**Date:** 2026-06-05

## Job Type

Resume does not introduce a third worker operation type. A resumed job inherits the source job's `job_type`:

- source `resend_email` -> resumed `resend_email`
- source `retry_generation` -> resumed `retry_generation`

The resumed job stores:

```json
{
  "source_job_id": "job-...",
  "resume_result_filters": ["failed", "refused"],
  "resume_from": {
    "job_id": "job-...",
    "job_type": "retry_generation"
  }
}
```

## Source Job Eligibility

Allowed source job statuses:

- `completed`
- `completed_with_failures`
- `cancelled`
- `failed`
- `stopped_failure_threshold`
- `stopped_time_floor`

Not allowed:

- `queued`
- `running`
- `cancellation_requested`
- unknown/missing source jobs

Rationale: resume must operate on stable completed or stopped target results, not concurrently mutating target state.

## Target Result Eligibility

Allowed result filters:

- `failed`
- `refused`
- `not_found`
- `skipped_cancelled`

Default result filters:

- `failed`
- `refused`
- `not_found`

`success` and `pending` are never resumable.

## Preview API

Endpoint:

```text
POST /admin/reports/recovery-jobs/{job_id}/resume/preview
```

Request:

```json
{
  "reason": "Incident retry after provider recovery",
  "results": ["failed", "refused", "not_found"],
  "max_targets": 25
}
```

Response:

```json
{
  "operation": "resume_recovery_job",
  "source_job_id": "job-1",
  "job_type": "retry_generation",
  "reason": "Incident retry after provider recovery",
  "requested_by": "admin-sub",
  "result_filters": ["failed", "refused", "not_found"],
  "max_targets": 25,
  "scanned_targets": 25,
  "eligible_count": 3,
  "refused_count": 0,
  "missing_count": 0,
  "sample": [],
  "preview_token": "..."
}
```

Preview token binds to:

- operation: `resume_recovery_job`
- source job id
- inherited job type
- result filters
- operator reason
- max targets
- eligible target ids
- target snapshot hash

## Create API

Endpoint:

```text
POST /admin/reports/recovery-jobs/{job_id}/resume
```

Request:

```json
{
  "reason": "Incident retry after provider recovery",
  "results": ["failed", "refused", "not_found"],
  "preview_token": "...",
  "max_targets": 25
}
```

Create behavior:

1. Recompute preview from the source job target snapshot.
2. Reject if preview token mismatches.
3. Reject if no eligible targets remain.
4. Create a new recovery job with inherited `job_type`.
5. Store target snapshots copied from source targets with `result=pending`.
6. Store `source_job_id` and `resume_result_filters` on the new job.
7. Write audit event `create_resume_job`.
8. Invoke existing worker event for inherited job type.

## Audit Actions

Source job audit:

- `create_resume_job`

Resumed job audit:

- existing run/target/complete actions for inherited job type

Preview is read-only and does not write audit records.

Audit metadata:

```json
{
  "source_job_id": "job-1",
  "resumed_job_id": "job-2",
  "job_type": "retry_generation",
  "result_filters": ["failed"],
  "target_count": 2
}
```

## Privacy Boundary

Resume preview/create responses expose only existing target metadata:

- report id
- parent id
- student id
- student name
- week start
- status
- email status
- result/detail/error class

Denied:

- `weekly-reports/`
- S3 keys
- presigned URLs
- raw report JSON
- raw report HTML
- auth/session tokens
- artifact payloads
