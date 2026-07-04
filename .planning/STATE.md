---
gsd_state_version: 1.0
milestone: v5.13
milestone_name: Payment And Entitlement Production Completion
status: planning
last_updated: "2026-07-04T23:17:00.774Z"
last_activity: 2026-07-04
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
**Current focus:** v5.13 Payment And Entitlement Production Completion.

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-07-05 — Milestone v5.13 started and requirements/roadmap initialized

## Accumulated Context

### Decisions

- v5.10 is complete: email verification UX, parent account operations UI, admin account operations console, focused frontend e2e, backend contract evidence, and production read-only smoke planning.
- v5.11 is complete: governed multi-action usage ledger taxonomy, chat/teacher-help/practice/assignment/generation instrumentation, reconciliation, account operations compatibility, 72 focused backend tests, and Ruff.
- v5.1 was readiness-complete, not implementation-complete. Its audit explicitly deferred rich editor frontend, draft patch/update, validation preview, diff, audit-read, migration service/API/UI, evidence persistence, and rollback metadata.
- v5.12 remains the active curriculum editor and content migration buildout milestone.
- Curriculum editing is not a default teacher/tutor permission. v5.12 must require backend-granted curriculum capabilities such as `curriculum_author`, `curriculum_reviewer`, and `curriculum_publisher`/`migration_operator`.
- Phase 233 is complete: backend curriculum editor mutations now require explicit capabilities, and patch, validation preview, diff, and audit-read APIs are available for Phase 235 frontend work.
- Phase 234 is complete: backend migration dry-run/apply/evidence APIs are available, dry-run is non-mutating, apply requires confirmation, and evidence/audit/rollback metadata are recorded.
- Phase 235 is complete: frontend `/admin/curriculum` now exposes the curriculum worklist, draft editor, validation/diff/audit review tools, migration dry-run/apply flow, and migration evidence lookup against real backend APIs with no demo fallback for API failures.
- Phase 236 is complete: v5.12 is closed as `curriculum-buildout-ready` with backend focused tests, frontend build/lint/e2e, release gate, and milestone audit.
- v5.13 is active: paid-access completion must audit real checkout/paywall/entitlement behavior before implementation, then connect provider reconciliation, entitlement activation, usage-limit compatibility, parent-facing state, and admin billing support evidence.
- Future milestones should be new functional, safety, or stability buildouts, not renamed v5.12 phases.
- External activation work remains deferred until prerequisites unblock: live Stripe/TWINT, external support provider, live notification providers, APNS/FCM, production warehouse/BI.
- Published student/parent curriculum reads, adaptive assignment behavior, and v5.11 usage ledger compatibility must remain stable while authoring/migration tools are added.

### Pending Todos

- Execute Phase 237 Payment Reality Audit And Contract Refresh.
- Keep future milestones independent: verification/login reliability and usage/quota/product stability.

### Blockers/Concerns

- Frontend implementation work is in `/Users/zhdeng/stoa-frontend`, outside this backend repo's write root; Phase 235 frontend implementation is committed there as `dff7430`.
- Actual production content import depends on approved source material being available; v5.12 can build the repeatable pipeline without importing unapproved sources.
- Production deploy/live smoke remains separate from local functional readiness.
- Payment, verification, and usage features have planning/test evidence in prior milestones, but the next milestone queue must audit real product behavior again before assuming production completeness.
- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.

## Operator Next Steps

- Start Phase 237 with a reality audit and contract refresh before changing payment behavior.
