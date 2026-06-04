---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Report Recovery Production Rollout & Live Smoke
status: planning
last_updated: "2026-06-04T16:04:37Z"
last_activity: 2026-06-04
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** Phase 28 - Release Readiness and Deployment Contract

## Current Position

Phase: 28 of 32 (Release Readiness and Deployment Contract)
Plan: —
Status: v1.5 planning started; Phase 28 ready for detailed planning
Last activity: 2026-06-04 — Started v1.5 Report Recovery Production Rollout & Live Smoke planning docs

## Performance Metrics

**Velocity:**

- Total plans completed: 33
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1-13 | 19 complete | - | - |
| 14-18 | 5 complete | - | - |
| 14 | 1 | - | - |
| 15 | 1 | - | - |
| 16 | 1 | - | - |
| 17 | 1 | - | - |
| 18 | 1 | - | - |
| 19 | 1 complete | - | - |
| 20 | 1 complete | - | - |
| 21 | 1 complete | - | - |
| 22 | 1 complete | - | - |
| 23 | 1 complete | - | - |
| 24 | 1 complete | - | - |
| 25 | 1 complete | - | - |
| 26 | 1 complete | - | - |
| 27 | 1 complete | - | - |
| 28 | 0/1 planned | - | - |
| 29 | 0/1 planned | - | - |
| 30 | 0/1 planned | - | - |
| 31 | 0/1 planned | - | - |
| 32 | 0/1 planned | - | - |

**Recent Trend:**

- Last 5 plans: complete
- Trend: v1.5 planning started after v1.4 report operations recovery workflow shipped and archived

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- v1.2 roadmap starts at Phase 14 because v1.1 ended at Phase 13.
- v1.2 blesses `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` as the canonical artifact key convention.
- v1.2 keeps report artifacts private and backend-mediated; no public S3 access or client direct S3 fetch is in scope.
- v1.2 uses existing CDK resources unless verification proves current reports bucket, Lambda env vars, or IAM grants are insufficient.
- v1.3 prioritizes reports bucket HTTPS enforcement, prefix-scoped IAM, artifact cleanup, and report operations tooling before broader report product expansion.
- Phase 19 uses `s3.Bucket(enforce_ssl=True)` for `StoaReportsBucket`; live AWS bucket policy denies `aws:SecureTransport=false`.
- Phase 20 scopes API and weekly report Lambda report artifact S3 actions to `weekly-reports/*`; no reports bucket-level permissions are retained.
- Phase 21 deletes deterministic smoke artifacts after readback and best-effort deletes partial JSON artifacts when HTML write fails.
- Phase 22 adds admin-only report operations metadata and failed-delivery resend endpoints with persisted audit fields.
- Phase 23 adds admin report operations list/detail metadata, bounded pagination, generation metadata, and action eligibility.
- Phase 24 adds admin-only single-report `generation_failed` retry with retry audit fields.
- Phase 25 adds admin-only selected bulk resend for `email_failed` reports with per-item results and shared resend audit fields.
- Phase 26 adds frontend admin report operations UI for filtering, detail inspection, generation retry, single resend, and selected bulk resend.
- Phase 27 verifies authorization, privacy, backend/frontend tests, and live deployment state for report operations recovery.
- v1.5 prioritizes production rollout, safe live smoke, runbook, observability, and rollback evidence before incident-wide async recovery automation.

### Pending Todos

- Plan Phase 28: Release Readiness and Deployment Contract.

### Blockers/Concerns

- No active blockers.
- `stoa-backend/dist` is a gitignored Lambda build artifact; future CDK diff reviews should treat Lambda asset hash changes separately from infrastructure drift.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Data access | Scan-based child lookup | Accepted MVP tech debt | v1.0 close |
| Operations | Manual report retry/resend and delivery audit trail | Follow-up candidate | v1.1 close |
| Report output | Multi-language reports and PDF export | Follow-up candidate | v1.1 close |
| Access control | Billing-gated report access | Follow-up candidate | v1.1 close |
| Artifact hardening | `enforce_ssl`, prefix-scoped IAM, lifecycle cleanup, broader operational tooling | Completed in v1.3 | v1.2 close |

## Session Continuity

Last session: 2026-06-04 18:04 +02:00
Stopped at: v1.5 planning docs started; Phase 28 ready for planning.
Resume file: None
