---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Report Recovery Production Rollout & Live Smoke
status: active
last_updated: "2026-06-04T18:32:00Z"
last_activity: 2026-06-04
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 5
  completed_plans: 4
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-04)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** Phase 32 - Operations Runbook, Observability, and Milestone Closeout

## Current Position

Phase: 32 of 32 (Operations Runbook, Observability, and Milestone Closeout)
Plan: 32-01 pending
Status: Phase 31 live smoke complete; runbook and final audit remain
Last activity: 2026-06-04 — Fixed admin report ops scan pagination, deployed scoped `stoa-api` SES permission, restored current Lambda package, completed safe non-customer retry/resend/bulk resend smoke, and confirmed fixture cleanup

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
| 28 | 1 complete | - | - |
| 29 | 1 complete | - | - |
| 30 | 1 complete | - | - |
| 31 | 1 complete | - | - |
| 32 | 0/1 planned | - | - |

**Recent Trend:**

- Last 5 plans: complete
- Trend: Phase 30/31 production verification found and remediated pagination, API SES IAM, and stale local Lambda package deployment gaps

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
- Phase 28 defines release readiness, evidence, rollback, CDK diff classification, and mutation safety gates before live smoke.
- Phase 29 verifies the production frontend route and bundle contain the report operations UI/API markers, production API URL, and no private artifact exposure markers; admin browser click-through remains residual manual evidence.
- Phase 30 verifies AWS identity, Lambda config, API health, unauth/invalid-token rejection, focused tests, focused ruff, CDK diff, temporary admin/parent account lifecycle cleanup, admin-auth list/detail HTTP 200, bounded-scan pagination second-page HTTP 200, and valid non-admin HTTP 403.
- Phase 31 verifies safe non-customer generation retry, single resend, selected bulk resend, audit/status updates, metadata-only response shapes, scoped `stoa-api` SES permission, current Lambda package restoration, and cleanup of temporary Cognito/DynamoDB/S3 fixture data.

### Pending Todos

- Write Phase 32 operations runbook, observability guidance, rollback checklist, final verification evidence, and milestone audit.

### Blockers/Concerns

- CDK deploys package `../stoa-backend/dist`; stale local `dist` can overwrite production Lambda code. Rebuild backend `dist` from current source before CDK deploys that touch Lambda assets, or use an IAM-only deployment path.
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

Last session: 2026-06-04 20:32 +02:00
Stopped at: Phase 32 pending after Phase 31 live smoke completion and cleanup.
Resume file: None
