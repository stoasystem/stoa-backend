---
gsd_state_version: 1.0
milestone: v5.14
milestone_name: Verification And Login Reliability
status: active
last_updated: "2026-07-05T01:30:00.000Z"
last_activity: 2026-07-05 — Phase 246 backend gate passed; frontend focused e2e blocked by platform usage-limit approval
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 5
  completed_plans: 4
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v5.14 Verification And Login Reliability.

## Current Position

Phase: 246 v5.14 Verification Login Reliability Gate
Plan: Run final backend/frontend evidence checks and close v5.14 with blocked live-smoke notes.
Status: Active
Last activity: 2026-07-05 — Phase 246 backend tests/Ruff passed and frontend build evidence exists; focused frontend e2e is blocked by local execution approval quota.

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
- Phase 237 is complete: canonical paid-state APIs are `/parents/me/subscription*`; legacy frontend `/billing/*` client still uses demo fallback and must not decide paid access after Phase 238.
- Phase 238 is complete: frontend `/billing` now reads `/parents/me/subscription` for subscription, usage, and feature access; checkout creation targets `/parents/me/subscription/checkout`; paid-state API failures render visibly instead of falling back to mock subscription data.
- Phase 239 is complete: duplicate Stripe webhooks now create support-visible dedup events, stale older provider events are recorded as ignored, and active paid access cannot be downgraded by an older failed-payment event.
- Phase 240 is complete: billing responses now include bounded supportEvidence, and frontend admin billing/account-operations surfaces render support action plus duplicate/stale reconciliation counts.
- Phase 241 is complete: backend tests/Ruff, frontend build/lint, and focused billing e2e passed; live Stripe/TWINT smoke remains blocked on external credentials, webhook endpoint, finance acceptance, and rollout approval.
- v5.14 is active: verification/login reliability must audit Cognito/local/frontend behavior first, then harden resend/confirm/login policy, resolve half-enabled login-code behavior, add support visibility, and close with local release evidence.
- Phase 242 is complete: backend Cognito sign-up confirmation, local verification state, resend/confirm endpoints, token-return blocking, frontend verification screens, admin/account-operations support views, login-code deferral, demo-only fallback boundaries, and externally blocked live-smoke evidence are documented.
- Phase 243 is complete: backend auth now handles idempotent confirm, stale Cognito-already-confirmed local repair, disabled account login/resend, and structured verification errors; `.venv/bin/pytest tests/test_auth_account_lifecycle.py` and Ruff passed.
- Phase 244 is complete: email/password plus verified email is the canonical product login path; passwordless/login-code remains deferred, frontend has no product login-code path, and backend tests assert deferred/no-token responses.
- Phase 245 is complete: backend verification public state now includes supportRecoveryState/supportAction, admin verification responses expose them, parent/admin account operations render recovery evidence, frontend build passed, and frontend commit `f2e96df` contains the UI change.
- Future milestones should be new functional, safety, or stability buildouts, not renamed v5.12 phases.
- External activation work remains deferred until prerequisites unblock: live Stripe/TWINT, external support provider, live notification providers, APNS/FCM, production warehouse/BI.
- Published student/parent curriculum reads, adaptive assignment behavior, and v5.11 usage ledger compatibility must remain stable while authoring/migration tools are added.

### Pending Todos

- Re-run focused frontend e2e when external-write/dev-server execution permission is available: `npm run test:e2e -- auth.spec.ts admin-account-operations.spec.ts parent-account-operations.spec.ts` in `/Users/zhdeng/stoa-frontend`.
- Execute Phase 246 v5.14 Verification Login Reliability Gate.
- Keep future milestones independent: verification/login reliability and usage/quota/product stability.

### Blockers/Concerns

- Frontend implementation work is in `/Users/zhdeng/stoa-frontend`, outside this backend repo's write root; Phase 235 frontend implementation is committed there as `dff7430`.
- Actual production content import depends on approved source material being available; v5.12 can build the repeatable pipeline without importing unapproved sources.
- Production deploy/live smoke remains separate from local functional readiness.
- Payment, verification, and usage features have planning/test evidence in prior milestones, but the next milestone queue must audit real product behavior again before assuming production completeness.
- Live Stripe/TWINT smoke remains blocked unless approved production credentials, registered webhook endpoint, finance acceptance, and explicit rollout enablement are available.

## Operator Next Steps

- Audit current verification/login behavior and define the v5.14 implementation contract.
