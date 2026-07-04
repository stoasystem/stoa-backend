---
gsd_state_version: 1.0
milestone: v5.12
milestone_name: Curriculum Editor And Content Migration Buildout
status: Active planning
last_updated: "2026-07-04T22:09:41.000Z"
last_activity: 2026-07-05 — Reconciled current feature reality after v5.11 and selected v5.12 curriculum editor/migration buildout
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 5
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.12 Curriculum Editor And Content Migration Buildout.

## Current Position

Phase: 232 Curriculum Buildout Reality Refresh And Contract
Plan: 232 Refresh curriculum reality and define v5.12 build contract
Status: Active planning
Last activity: 2026-07-05 — Used current docs/code reality and v5.1 deferred audit to select curriculum editor/migration implementation as the next buildable milestone.

## Accumulated Context

### Decisions

- v5.10 is complete: email verification UX, parent account operations UI, admin account operations console, focused frontend e2e, backend contract evidence, and production read-only smoke planning.
- v5.11 is complete: governed multi-action usage ledger taxonomy, chat/teacher-help/practice/assignment/generation instrumentation, reconciliation, account operations compatibility, 72 focused backend tests, and Ruff.
- v5.1 was readiness-complete, not implementation-complete. Its audit explicitly deferred rich editor frontend, draft patch/update, validation preview, diff, audit-read, migration service/API/UI, evidence persistence, and rollback metadata.
- v5.12 should build curriculum editor and content migration tooling because it is internally buildable and not blocked by live provider credentials.
- External activation work remains deferred until prerequisites unblock: live Stripe/TWINT, external support provider, live notification providers, APNS/FCM, production warehouse/BI.
- Published student/parent curriculum reads, adaptive assignment behavior, and v5.11 usage ledger compatibility must remain stable while authoring/migration tools are added.

### Pending Todos

- Complete Phase 232 reality refresh and v5.12 build contract.
- Implement Phase 233 backend editor patch/validation/diff/audit APIs.
- Implement Phase 234 backend content migration service and APIs.
- Implement Phase 235 frontend curriculum editor and migration console.
- Close Phase 236 with backend/frontend release evidence and next milestone recommendation.
- Verify cleanup archive target before moving phase directories.

### Blockers/Concerns

- Frontend implementation work is in `/Users/zhdeng/stoa-frontend`, outside this backend repo's write root.
- Actual production content import depends on approved source material being available; v5.12 can build the repeatable pipeline without importing unapproved sources.
- Production deploy/live smoke remains separate from local functional readiness.

## Operator Next Steps

- Finish Phase 232 docs, then start Phase 233 backend editor APIs.
