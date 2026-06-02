---
phase: 10-scheduled-job-orchestration
plan: 01
subsystem: backend
tags: [reports, scheduler, lambda, idempotency, orchestration]
requires:
  - phase: 09-report-storage-and-email-delivery
    provides: Store-and-send report service
provides:
  - Scheduled weekly report Lambda handler
  - Previous Zurich week calculation
  - Linked parent/student pair discovery
  - Atomic report generation claim
  - Structured job counts
affects: [parent-report-api, backend-report-verification]
tech-stack:
  added: []
  patterns:
    - Testable job runner with Lambda handler wrapper
    - DynamoDB conditional claim before generation/email side effects
    - Per-pair failure isolation with operational logs
key-files:
  created:
    - tests/test_weekly_reports_job.py
  modified:
    - src/stoa/db/repositories/report_repo.py
    - src/stoa/jobs/weekly_reports.py
    - src/stoa/services/report_service.py
    - tests/test_parent_children.py
key-decisions:
  - "Default scheduled jobs target the previous Europe/Zurich calendar week."
  - "Pair discovery scans linked student profiles using the existing `parent_id` MVP convention."
  - "A conditional DynamoDB claim is written before aggregation/generation/S3/SES side effects."
  - "Claimed jobs that fail are marked `generation_failed` so future runs are not permanently locked."
patterns-established:
  - "Phase 11 can rely on generated/email/email_failed/generation_failed statuses in report records."
requirements-completed: [JOB-01, JOB-02, JOB-03, JOB-04, JOB-05]
duration: 55min
completed: 2026-06-02
---

# Phase 10 Plan 01 Summary

**Scheduled weekly report job orchestration**

## Accomplishments

- Replaced the weekly report Lambda stub with a real scheduled job runner.
- Added previous Zurich calendar week calculation and explicit event week override support.
- Added linked parent/student pair discovery from student profiles.
- Added idempotent orchestration using existing report lookup plus an atomic DynamoDB conditional claim before side effects.
- Added per-pair generation flow: aggregation, Bedrock/fallback generation, storage, and email.
- Added structured counts for attempted, generated, skipped existing, email sent, and failed reports.
- Added focused job tests plus repository conditional claim tests.

## Task Commits

1. **Scheduled weekly report orchestration** - `58d5565` (`feat(10): orchestrate scheduled weekly reports`)

## Verification

- `uv run --extra dev pytest tests/test_weekly_reports_job.py tests/test_parent_children.py tests/test_report_service.py -q` - passed, 82 tests
- `uv run --extra dev ruff check src/stoa/jobs/weekly_reports.py src/stoa/db/repositories/report_repo.py src/stoa/services/report_service.py tests/test_weekly_reports_job.py tests/test_parent_children.py tests/test_report_service.py` - passed

## Issues Encountered

- Code review found check-then-act idempotency was not atomic. Fixed with `try_claim_report_generation`.
- Code review found claims could become permanent stale locks after post-claim failures. Fixed by marking `generation_failed` on exception.
- Code review asked for stronger EventBridge evidence. Verified Phase 6 CDK already targets `stoa.jobs.weekly_reports.handler` and added an EventBridge-shaped handler test.

## Next Phase Readiness

Phase 11 can expose stored generated report fields and status details through the parent API and frontend report page.
