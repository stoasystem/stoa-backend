---
gsd_state_version: 1.0
milestone: v1.7
milestone_name: Recovery Evidence Export & Admin Credential Operations
status: active
last_updated: "2026-06-05T10:58:27+02:00"
last_activity: 2026-06-05
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 2
  completed_plans: 2
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v1.7 starts production admin credential operations and metadata-only recovery evidence export.

## Current Position

Phase: 39 of 41 (2 of 4 for v1.7)
Plan: 39-01
Status: Complete
Last activity: 2026-06-05 - Phase 39 metadata-only export backend completed.

Progress: [█████-----] 50%

## Performance Metrics

**Velocity:**

- Historical plans completed through v1.5: 33
- Historical plans completed through v1.6: 38
- Active milestone plans created: 2
- Active milestone plans completed: 2
- Average duration: -
- Total execution time this milestone: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 38 | 1/1 complete | - | - |
| 39 | 1/1 complete | - | - |
| 40 | 0 complete | - | - |
| 41 | 0 complete | - | - |

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

### Pending Todos

- Plan Phase 40 admin export UI and read-only smoke.
- Add export controls to `/admin/report-operations`.
- Keep production smoke read-only until export UI exists.

### Blockers/Concerns

- CDK deploys package `../stoa-backend/dist`; Phase 33 added manifest and fail-fast guard, but CI must still prove the GitHub checkout layout after merge.
- Production admin credential ownership and rotation cadence must be assigned by operations before routine support use.
- Export scans must remain bounded; avoid introducing broad table scans into the admin UI.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Recovery expansion | Incident-wide generation retry | Future candidate after evidence export | v1.6 requirements |
| Infrastructure | Step Functions/SQS/new table/new bucket/new Lambda/new GSI | Deferred unless existing resources prove insufficient | v1.6 requirements |
| Audit storage | Compliance-grade WORM evidence | Future security/compliance decision | v1.6 requirements |
| Product expansion | Report editing, PDF, multilingual delivery, billing, analytics, ticket integration | Out of scope for v1.7 | v1.6 requirements |

## Session Continuity

Last session: 2026-06-05 10:39 +02:00
Stopped at: Phase 39 complete; Phase 40 is next.
Resume file: None

## Operator Next Steps

- Plan Phase 40 admin export UI.
- Implement frontend export controls and local browser smoke.
- Keep production UI smoke read-only.
