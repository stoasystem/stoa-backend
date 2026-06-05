---
gsd_state_version: 1.0
milestone: v1.8
milestone_name: Incident Generation Retry Jobs
status: active
last_updated: "2026-06-05T13:18:19+02:00"
last_activity: 2026-06-05
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 3
  completed_plans: 3
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v1.8 starts bounded async `generation_failed` retry jobs.

## Current Position

Phase: 45 of 45 (3 of 4 for v1.8)
Plan: 45-01
Status: Active
Last activity: 2026-06-05 - Phase 44 admin generation retry job UI completed.

Progress: [████████--] 75%

## Performance Metrics

**Velocity:**

- Historical plans completed through v1.5: 33
- Historical plans completed through v1.6: 38
- Active milestone plans created: 3
- Active milestone plans completed: 3
- Average duration: -
- Total execution time this milestone: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 42 | 1/1 complete | - | - |
| 43 | 1/1 complete | - | - |
| 44 | 1/1 complete | - | - |
| 45 | 0/1 planned | - | - |

**Recent Trend:**

- Last completed milestone: v1.6 shipped 5/5 phases and 28/28 requirements.
- Trend: Production verification is now strong enough to turn metadata-only operational evidence into a reusable release gate.

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- v1.7 starts at Phase 38 because v1.6 ended at Phase 37.
- v1.7 selects metadata-only recovery target/job/audit export from deferred follow-ups before larger mutation or orchestration work.
- Production admin credential ownership/rotation is included because v1.6 created the long-lived secret-backed admin path but left operational ownership as follow-up.
- Existing Lambda/DynamoDB/admin UI resources should be reused unless Phase 38 proves a concrete missing access pattern.
- Export payloads must use explicit metadata allowlists and preserve the no-private-artifact boundary proven in v1.6 production browser smoke.
- Phase 38 decided that exact `job_id` export is the preferred Phase 39 implementation path and no CDK change is required for the MVP.
- Phase 39 implemented the admin-only `GET /admin/reports/recovery-evidence` backend without CDK changes.
- Phase 40 added frontend export controls in `/admin/report-operations` and verified local browser smoke without production calls.
- Phase 41 release gate passed with backend/frontend deploy evidence, Lambda manifest evidence, production API/browser smoke, and no production recovery mutation.
- v1.8 promotes incident-wide `generation_failed` retry as the next bounded recovery expansion and keeps new AWS orchestration deferred unless evidence requires it.
- Phase 43 added `retry_generation` as a second async recovery job type without CDK changes.
- Phase 44 added shared resend/generation retry controls to the admin report operations UI and verified frontend e2e privacy coverage.

### Pending Todos

- Execute Phase 45 release gate and read-only production verification.

### Blockers/Concerns

- CDK deploys package `../stoa-backend/dist`; Phase 33 added manifest and fail-fast guard, but CI must still prove the GitHub checkout layout after merge.
- Production admin credential ownership and rotation cadence must be assigned by operations before routine support use.
- Export scans must remain bounded; avoid introducing broad table scans into the admin UI.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Infrastructure | Step Functions/SQS/new table/new bucket/new Lambda/new GSI | Deferred unless existing resources prove insufficient | v1.6 requirements |
| Audit storage | Compliance-grade WORM evidence | Future security/compliance decision | v1.6 requirements |
| Product expansion | Report editing, PDF, multilingual delivery, billing, analytics, ticket integration | Out of scope for v1.7 | v1.6 requirements |

## Session Continuity

Last session: 2026-06-05 10:39 +02:00
Stopped at: Phase 44 complete; Phase 45 release gate is next.
Resume file: None

## Operator Next Steps

- Execute v1.8 Phase 45, then archive and continue with v1.9.
