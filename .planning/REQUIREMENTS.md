# Requirements: v5.10 Account Operations Frontend And Production Readiness

**Milestone:** v5.10
**Status:** Active
**Created:** 2026-07-03
**Prior milestone:** v5.9 Parent Admin Operations Visibility

## Purpose

Make the completed backend account operations stack usable in the frontend and ready for production read-only verification.

v5.6-v5.9 completed backend entitlement, usage, verification, and operations visibility. v5.10 must move those capabilities from backend-only readiness into visible parent/admin/auth workflows.

## Requirements

### FRONTOPS-01 Reality Refresh And Frontend Contract

Acceptance criteria:

- Backend reality is mapped to current route/service/test evidence.
- Frontend reality is mapped to concrete missing API clients, query keys, routes, and pages.
- `stoa_docs` PRD/HLD/PLAN expectations are reconciled against current implementation state.
- v5.10 frontend contract defines role boundaries, response fields, UI states, and no-demo-fallback rules.
- Planning docs identify deferred work separately from v5.10 scope.

### FRONTOPS-02 Email Verification UX Integration

Acceptance criteria:

- Frontend auth API supports email verification resend and confirm calls.
- Registration handles pending verification without pretending login is complete.
- Login handles backend `email_verification_required` responses with an actionable verification path.
- Verification UI handles sent, already verified, expired, invalid code, rate-limited, and resend cooldown states.
- Focused frontend tests cover register-pending, login-blocked, resend, and confirm behavior.

### FRONTOPS-03 Parent Account Operations UI

Acceptance criteria:

- Parent frontend API and query keys support `/parents/me/account-operations`.
- Parent account operations UI displays billing status, effective entitlement, child usage, verification state, binding state, and support state.
- Ready, attention, blocked, no-child, inactive-billing, unverified, and unreconciled-usage states are represented.
- Account operations UI does not fall back to demo data when backend data fails.
- Focused frontend tests cover loaded, loading, empty, attention, blocked, and error states.

### FRONTOPS-04 Admin Account Operations Console

Acceptance criteria:

- Admin frontend API and query keys support `/admin/account-operations/parents/{parent_id}`.
- Admin route allows direct parent lookup and handoff from existing subscription/billing views where practical.
- Admin detail displays verification, billing summary/events, child binding, entitlement, usage, and support blockers/warnings.
- Missing parent, unauthorized, loading, and API-error states are handled.
- Focused frontend tests cover ready, attention, missing-parent, loading, and error states.

### VERIFY-43 v5.10 Frontend And Production Readiness Gate

Acceptance criteria:

- Frontend build, lint, and focused e2e tests pass.
- Backend focused contract checks pass for routes consumed by v5.10 frontend work.
- Docs, roadmap, state, and stoa_docs gap audit are updated.
- Production read-only smoke checklist is written for account verification, parent operations, admin operations, and privacy boundaries.
- Next milestone recommendation is explicit.

## Out of Scope

- New backend entitlement, usage, or verification primitives unless frontend integration reveals a concrete contract bug.
- Extending usage ledger beyond question submissions.
- Cognito custom-auth passwordless login-code implementation.
- Native iOS/Android app implementation.
- Final live Stripe/TWINT activation.
- Broad CRM/customer messaging and warehouse/BI dashboards.

## Future Milestones

- v5.11 Additional Usage Ledger Coverage for chat, hints, teacher-help, and practice/generation actions.
- v5.12 Native/Mobile Account Operations Client or rich curriculum editor frontend implementation, depending on product priority.
- External activation milestones for live Stripe/TWINT, support provider, notification provider, and warehouse/BI when prerequisites unblock.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FRONTOPS-01 | Phase 222 | Complete |
| FRONTOPS-02 | Phase 223 | Complete |
| FRONTOPS-03 | Phase 224 | Complete |
| FRONTOPS-04 | Phase 225 | Planned |
| VERIFY-43 | Phase 226 | Planned |
