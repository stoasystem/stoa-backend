---
gsd_state_version: 1.0
milestone: v5.12
milestone_name: Curriculum Editor And Content Migration Buildout
status: Active
last_updated: "2026-07-05T00:00:00.000Z"
last_activity: 2026-07-05 — Completed Phase 232 reality refresh, kept v5.12 active, and clarified future milestones as new feature/safety/stability buildouts
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 5
  completed_plans: 1
  percent: 20
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.12 Curriculum Editor And Content Migration Buildout.

## Current Position

Phase: 233 Backend Special Authorization Editor Patch Validation Diff And Audit APIs
Plan: 233 Backend special authorization and editor APIs
Status: Active
Last activity: 2026-07-05 — Phase 232 completed; next implementation starts by replacing broad curriculum authoring role checks with backend-granted capability checks.

## Accumulated Context

### Decisions

- v5.10 is complete: email verification UX, parent account operations UI, admin account operations console, focused frontend e2e, backend contract evidence, and production read-only smoke planning.
- v5.11 is complete: governed multi-action usage ledger taxonomy, chat/teacher-help/practice/assignment/generation instrumentation, reconciliation, account operations compatibility, 72 focused backend tests, and Ruff.
- v5.1 was readiness-complete, not implementation-complete. Its audit explicitly deferred rich editor frontend, draft patch/update, validation preview, diff, audit-read, migration service/API/UI, evidence persistence, and rollback metadata.
- v5.12 remains the active curriculum editor and content migration buildout milestone.
- Curriculum editing is not a default teacher/tutor permission. v5.12 must require backend-granted curriculum capabilities such as `curriculum_author`, `curriculum_reviewer`, and `curriculum_publisher`/`migration_operator`.
- Future milestones should be new functional, safety, or stability buildouts, not renamed v5.12 phases.
- External activation work remains deferred until prerequisites unblock: live Stripe/TWINT, external support provider, live notification providers, APNS/FCM, production warehouse/BI.
- Published student/parent curriculum reads, adaptive assignment behavior, and v5.11 usage ledger compatibility must remain stable while authoring/migration tools are added.

### Pending Todos

- Implement Phase 233 backend special authorization, editor patch, validation, diff, and audit APIs.
- Implement Phase 234 backend content migration service and APIs.
- Implement Phase 235 frontend curriculum editor and migration console.
- Close Phase 236 with backend/frontend release evidence and next milestone recommendation.
- Plan future milestones as independent feature/safety/stability work: paid access completion, verification/login reliability, and usage/quota/product stability.

### Blockers/Concerns

- Frontend implementation work is in `/Users/zhdeng/stoa-frontend`, outside this backend repo's write root.
- Actual production content import depends on approved source material being available; v5.12 can build the repeatable pipeline without importing unapproved sources.
- Production deploy/live smoke remains separate from local functional readiness.
- Payment, verification, and usage features have planning/test evidence in prior milestones, but the next milestone queue must audit real product behavior again before assuming production completeness.

## Operator Next Steps

- Start Phase 233 by replacing `AUTHOR_ROLES = {"admin", "tutor", "teacher"}` with backend-granted curriculum capabilities and focused authorization tests.
