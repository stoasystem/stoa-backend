# Retry Generation Recovery Job Contract

**Job type:** `retry_generation`
**Worker event:** `{"job":"report_recovery_retry_generation","job_id":"..."}`
**Mutation:** retries generation for existing reports whose current status is `generation_failed`.

## Preview

Preview request:

- `reason`
- `filters.status` defaulting to `generation_failed`
- optional `filters.week_start`
- optional `filters.parent_id`
- optional `filters.student_id`
- `max_targets` bounded to existing recovery job maximum

Preview response:

- `operation=retry_generation`
- normalized filters
- `eligible_count`
- `refused_count`
- `missing_count`
- metadata-only sample targets
- preview token

Preview token binds:

- operation
- filters
- reason
- eligible target IDs

## Creation

Creation requires:

- current preview token
- non-empty eligible target set
- admin role
- required operator reason

Created job:

- `job_type=retry_generation`
- `status=queued`
- stable target snapshot
- counters initialized to pending targets
- append-only job audit event
- async weekly Lambda invocation

## Execution

Worker behavior:

1. Claim queued job as running.
2. Iterate pending targets in stable order.
3. Stop if cancellation is requested.
4. Stop if Lambda remaining time falls below floor.
5. Claim each target before side effects.
6. Re-read report by parent/student/week.
7. Run existing single-report generation retry service.
8. Record target result as `success`, `refused`, `not_found`, `failed`, or `skipped_cancelled`.
9. Update job counters and terminal status.
10. Append job audit events.

Terminal status:

- `completed`
- `completed_with_failures`
- `failed`
- `cancelled`

## Privacy Boundary

Responses and audit metadata must omit:

- `weekly-reports/`
- S3 object keys
- presigned URLs
- raw report JSON
- raw report HTML
- auth/session tokens
- customer-sensitive artifact payloads

Target snapshots may include:

- report ID
- parent ID
- student ID
- student name
- week start
- status
- email status
- artifact availability booleans

## Cancellation

Cancellation uses the existing cooperative model:

- Admin requests cancellation.
- Queued/running job moves to `cancellation_requested`.
- Worker marks future pending targets as `skipped_cancelled`.
- Completed target side effects are not rolled back.

## Out Of Scope

- Retrying successful, generated, email-sent, or email-failed reports.
- Resuming failed/skipped subset jobs.
- Step Functions/SQS orchestration.
- Production mutation smoke without a named safe fixture.

