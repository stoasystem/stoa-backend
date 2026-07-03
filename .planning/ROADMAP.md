# Roadmap: v5.10 Account Operations Frontend And Production Readiness

**Status:** Active
**Created:** 2026-07-03
**Reality refresh:** `.planning/phases/222-current-reality-refresh-and-frontend-account-ops-contract/222-CURRENT-REALITY-REFRESH.md`
**Prior milestone:** v5.9 Parent Admin Operations Visibility

## Goal

Turn the completed v5.6-v5.9 backend account operations capabilities into user-visible frontend flows and production-readiness evidence.

## Why This Is The Next Milestone

The current backend has moved past the original final-polish gaps:

- v5.6 resolves effective entitlement and enforces question quota from parent billing/manual override.
- v5.7 records privacy-safe question usage ledger events and reconciles them with counters.
- v5.8 implements Cognito-backed email verification and explicitly defers unsupported passwordless login-code behavior.
- v5.9 exposes consolidated parent/admin account operations APIs.

The remaining product gap is that these states are not yet fully visible or actionable in the frontend. The frontend has parent subscription/billing screens and admin subscription views, but no typed client or route for `/parents/me/account-operations`, no admin account-operations detail route, and no full email-verification confirm/resend UI.

## Current Reality

Backend evidence:

- `src/stoa/services/entitlement_service.py` resolves linked-student entitlement from parent binding, billing status, manual override, and student fallback.
- `src/stoa/routers/questions.py` uses effective entitlement for daily question quota and records usage ledger events after counter increment.
- `src/stoa/services/usage_ledger_service.py` records question usage events, supports idempotent retries, reconciles counters, and builds parent/admin summaries.
- `src/stoa/routers/auth.py` supports email verification confirm/resend and explicitly gates login-code endpoints as deferred.
- `src/stoa/services/account_operations_service.py` aggregates billing, entitlement, usage, verification, child binding, and support state.
- `src/stoa/routers/parents.py` exposes `/parents/me/account-operations`.
- `src/stoa/routers/admin.py` exposes `/admin/account-operations/parents/{parent_id}`.

Frontend evidence:

- `/Users/zhdeng/stoa-frontend/src/services/parent/parentApi.ts` has subscription and billing calls but no account-operations client.
- `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts` has subscription billing calls but no account-operations client.
- `/Users/zhdeng/stoa-frontend/src/app/router/AppRouter.tsx` has parent and admin routes, but no parent account operations page and no admin account operations detail page.
- `/Users/zhdeng/stoa-frontend/src/services/auth/authApi.ts` has login/register/current-user/locale calls, but no email verification resend/confirm client.

## Implementation Strategy

- Treat v5.10 as a frontend-first product milestone with backend contract checks.
- Do not reopen v5.6-v5.9 backend primitives unless frontend integration finds a concrete contract gap.
- Add typed frontend clients and query keys before pages.
- Put parent-facing account state into a real parent page/dashboard surface.
- Put admin support detail into an admin route that can inspect one parent by ID and explain blockers/warnings.
- Add email verification confirm/resend UX so the v5.8 backend lifecycle is actually usable.
- Close with build/lint/e2e evidence and production read-only smoke planning.

## Phases

- [x] **Phase 222: Reality Refresh And Frontend Account Operations Contract** - Reconcile code, docs, stoa_docs, and frontend gaps; define exact frontend/API contract.
- [x] **Phase 223: Email Verification UX Integration** - Add frontend auth clients and pages/states for verification confirm/resend and login/register pending states.
- [ ] **Phase 224: Parent Account Operations UI** - Add parent account operations API types/hooks and parent-visible account state page or dashboard section.
- [ ] **Phase 225: Admin Account Operations Console** - Add admin account operations API types/hooks and support-grade parent detail workflow.
- [ ] **Phase 226: v5.10 Frontend And Production Readiness Gate** - Verify frontend build/lint/e2e, backend contract compatibility, docs, and production read-only smoke checklist.

## Phase Details

### Phase 222: Reality Refresh And Frontend Account Operations Contract

**Goal**: Make the next build plan reflect current code reality instead of stale v5.6-v5.9 planning assumptions.
**Depends on**: v5.9 completion evidence.
**Requirements**: FRONTOPS-01
**Success Criteria**:

1. Current backend capabilities are mapped to concrete route/service/test evidence.
2. Current frontend gaps are mapped to concrete files and missing route/client evidence.
3. `stoa_docs` PRD/HLD/PLAN expectations are reconciled against shipped backend/frontend reality.
4. v5.10 frontend contract defines response fields, UI states, role boundaries, and no-demo-fallback expectations.
5. Planning docs and next-development queue are updated.

### Phase 223: Email Verification UX Integration

**Goal**: Make the v5.8 email verification lifecycle usable in the web frontend.
**Depends on**: Phase 222.
**Requirements**: FRONTOPS-02
**Success Criteria**:

1. Frontend auth service exposes typed resend and confirm verification calls.
2. Register flow shows pending-verification state without treating it as a completed login.
3. Login flow handles `email_verification_required` responses with a clear verification action path.
4. Verification confirm/resend UI covers sent, already verified, expired, rate-limited, and invalid-code states.
5. Focused frontend tests cover registration pending, resend, confirm, and login blocked until verified.

### Phase 224: Parent Account Operations UI

**Goal**: Let parents see the account state that v5.9 exposes.
**Depends on**: Phase 223.
**Requirements**: FRONTOPS-03
**Success Criteria**:

1. Parent API service and query keys include `/parents/me/account-operations`.
2. Parent UI shows billing status, effective entitlement, child usage, verification state, binding state, and support state.
3. Ready, attention, blocked, no-child, inactive-billing, unverified, and unreconciled-usage states render clearly.
4. UI does not use demo fallback for account operations data.
5. Frontend tests cover loaded, empty, attention, blocked, loading, and API-error states.

### Phase 225: Admin Account Operations Console

**Goal**: Give admins a practical support view for one parent account.
**Depends on**: Phase 224.
**Requirements**: FRONTOPS-04
**Success Criteria**:

1. Admin API service and query keys include `/admin/account-operations/parents/{parent_id}`.
2. Admin route supports looking up one parent ID from subscription/billing context or direct input.
3. Admin detail shows parent verification, billing summary/events, child binding, entitlement, usage, and support blockers/warnings.
4. Missing parent and non-admin access states are handled without leaking internals.
5. Frontend tests cover ready, attention, missing-parent, loading, and API-error states.

### Phase 226: v5.10 Frontend And Production Readiness Gate

**Goal**: Close v5.10 with usable frontend evidence and a production read-only verification path.
**Depends on**: Phase 225.
**Requirements**: VERIFY-43
**Success Criteria**:

1. Frontend build, lint, and focused e2e tests pass for account verification and account operations.
2. Backend contract tests or focused backend tests still pass for v5.6-v5.9 routes used by the frontend.
3. Docs, state, roadmap, and stoa_docs gap audit reflect v5.10 completion or remaining gaps.
4. Production read-only smoke checklist covers login, verification-visible states, parent account operations, admin account operations, and privacy boundaries.
5. Next milestone recommendation is updated.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 222 Reality Refresh And Frontend Account Operations Contract | v5.10 | 1/1 | Complete | 2026-07-03 |
| 223 Email Verification UX Integration | v5.10 | 1/1 | Complete | 2026-07-03 |
| 224 Parent Account Operations UI | v5.10 | 0/1 | Planned | - |
| 225 Admin Account Operations Console | v5.10 | 0/1 | Planned | - |
| 226 v5.10 Frontend And Production Readiness Gate | v5.10 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FRONTOPS-01 | Phase 222 | Complete |
| FRONTOPS-02 | Phase 223 | Complete |
| FRONTOPS-03 | Phase 224 | Planned |
| FRONTOPS-04 | Phase 225 | Planned |
| VERIFY-43 | Phase 226 | Planned |
