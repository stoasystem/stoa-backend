# Requirements: v1.8 Incident Generation Retry Jobs

**Created:** 2026-06-05
**Status:** Active milestone requirements
**Source:** v1.7 final audit deferred items and autonomous next-milestone selection

## Milestone Goal

Allow admins to run bounded async `generation_failed` recovery jobs through the existing recovery job platform, while preserving metadata-only evidence, cancellation, auditability, and production safety.

## Success Criteria

- Admins can preview eligible `generation_failed` targets before creating a mutation job.
- Admins can create a bounded async `retry_generation` job after preview confirmation.
- The weekly report Lambda can execute `retry_generation` jobs target-by-target with stable target snapshots, cancellation, stop conditions, and per-target results.
- Job list/detail/result/audit/export surfaces distinguish `resend_email` from `retry_generation`.
- Tests prove admin-only authorization, bounds, privacy boundary, idempotent claims, cancellation, and no new infrastructure requirement.
- Release gate records deploy/build/CDK evidence and production read-only UI/API smoke without creating a production mutation job.

## Functional Requirements

### GENJOB-01 Generation Retry Preview

Admins can preview a bounded `generation_failed` retry job from filters before any mutation.

Acceptance criteria:

- Preview accepts status, week, parent, student, reason, and max target bounds.
- Preview only allows `generation_failed` scope.
- Preview returns eligible/refused/missing counts and metadata-only samples.
- Preview token binds filters, reason, operation, and target IDs.

### GENJOB-02 Generation Retry Job Creation

Admins can create a `retry_generation` job only after confirming a current preview.

Acceptance criteria:

- Create rejects stale/mismatched preview tokens.
- Create rejects empty eligible scopes.
- Created job has `job_type=retry_generation`.
- Target snapshot includes only metadata-safe report IDs, parent/student IDs, week, status, and result state.
- Create writes append-only job audit evidence and invokes the weekly report Lambda asynchronously.

### GENJOB-03 Generation Retry Worker Execution

The worker executes stable targets with cancellation and stop conditions.

Acceptance criteria:

- Worker accepts event `job=report_recovery_retry_generation`.
- Worker uses existing report recovery service to retry one target at a time.
- Worker records `success`, `refused`, `not_found`, `failed`, or `skipped_cancelled` per target.
- Worker updates job counters and terminal status.
- Worker respects Lambda time floor and failure threshold.

### GENJOB-04 Authorization, Privacy, And Audit

Generation retry jobs preserve existing admin-only and metadata-only boundaries.

Acceptance criteria:

- Preview/create/list/detail/results/audit reject non-admin callers.
- Responses omit `weekly-reports/`, S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, and customer-sensitive artifact payloads.
- Audit events redact private artifact markers and include actor, action, reason, source, result, target metadata, and job correlation ID.

### GENJOB-05 Admin UI

The admin report operations UI supports async generation retry jobs without confusing them with resend jobs.

Acceptance criteria:

- UI lets admins choose job type `Resend email` or `Retry generation`.
- UI adjusts status defaults and labels for the selected job type.
- UI can preview/start generation retry jobs, poll jobs, view results/audit, and export evidence.
- UI copy preserves read-only versus mutation distinction.

### GENJOB-06 v1.8 Release Gate

v1.8 closes with release evidence and read-only production verification.

Acceptance criteria:

- Release gate records backend/frontend deploy evidence when performed.
- Lambda manifest and runtime state are recorded.
- CDK diff is recorded and any Lambda code asset drift is classified.
- Production browser smoke loads `/admin/report-operations`, verifies generation retry job UI presence, calls only GET APIs, and performs no production mutation.

## Non-Functional Requirements

- Reuse existing API Lambda, weekly report Lambda, DynamoDB table, Cognito admin auth, and admin route by default.
- Do not add Step Functions, SQS, new tables, new buckets, new Lambdas, or new GSIs in v1.8 unless current implementation cannot satisfy bounded generation retry jobs.
- Keep target caps conservative.
- Keep production verification read-only unless a named safe fixture and explicit mutation approval path exists.

## Out of Scope

- Resume failed/skipped subsets as a new job - v1.9.
- Support ticket integration or evidence packages - v1.9.
- Report editing - v2.0.
- WORM audit storage.
- PDF generation, multilingual delivery, billing, analytics, and broader admin expansion.

## Traceability

| Requirement | Primary Phase | Status |
|-------------|---------------|--------|
| GENJOB-01 | Phase 42/43 | Planned |
| GENJOB-02 | Phase 43 | Planned |
| GENJOB-03 | Phase 43 | Planned |
| GENJOB-04 | Phase 43/45 | Planned |
| GENJOB-05 | Phase 44 | Complete |
| GENJOB-06 | Phase 45 | Planned |
