# Roadmap: v5.14 Verification And Login Reliability

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.13 Payment And Entitlement Production Completion

## Goal

Make email verification, login-code policy, account activation, resend/confirm, and support recovery reliable across backend, frontend, and admin support surfaces.

## Why This Is The Current Milestone

v5.8 replaced placeholder email verification with Cognito sign-up confirmation and explicitly deferred login-code/passwordless behavior. v5.10 added frontend verification UX and account operations visibility. Those capabilities need a product-level reliability closeout so real users can register, verify, log in, recover from common failures, and receive clear support-safe status.

## Current Reality To Verify

- Backend has Cognito sign-up confirmation, verification state fields, resend/confirm behavior, and account operations visibility from prior milestones.
- Frontend has verification UX, but v5.14 must verify no stale/demo/half-enabled auth paths remain visible.
- Login-code/passwordless behavior was explicitly deferred and must not remain half-present without a real Cognito custom-auth implementation.
- Live email/Cognito smoke may be externally gated depending on environment credentials and deployment status.

## Implementation Strategy

- Start with a reality audit and canonical policy contract before changing auth behavior.
- Prefer one dependable login path over multiple incomplete login paths.
- Keep support evidence bounded: statuses, timestamps, request IDs, and support actions, not secrets/codes/tokens.
- Add backend contract tests before frontend recovery polish.
- Verify locally with deterministic Cognito/service fixtures; document live smoke as blocked or completed.

## Phases

- [x] **Phase 242: Verification And Login Reality Audit** - Map current Cognito/local/frontend/support verification behavior and define the v5.14 policy contract.
- [x] **Phase 243: Backend Verification Resend Confirm Reliability** - Harden registration confirmation, resend, confirm, activation, and profile state consistency.
- [ ] **Phase 244: Login Code And Passwordless Policy Resolution** - Complete or remove half-enabled login-code/passwordless behavior and lock the canonical login policy.
- [ ] **Phase 245: Frontend Verification Recovery And Admin Support Visibility** - Make verification/login recovery states usable in frontend and support/admin surfaces.
- [ ] **Phase 246: v5.14 Verification Login Reliability Gate** - Verify backend/frontend behavior, docs, live-smoke status, state, and next milestone decision.

## Phase Details

### Phase 242: Verification And Login Reality Audit

**Goal**: Define the exact verification/login reliability implementation contract from current backend/frontend behavior and prior milestones.
**Depends on**: v5.13 completion.
**Requirements**: AUTHREL-01
**Status**: Complete.
**Success Criteria**:

1. Current Cognito sign-up confirmation, local profile verification fields, resend/confirm endpoints, token-return behavior, frontend screens, and admin/account-operations views are mapped to files/routes/services.
2. Implemented, partially implemented, demo-only, stale, locally verified, and externally blocked behavior is separated in an evidence table.
3. Login-code/passwordless references are classified as supported, hidden, or deferred.
4. v5.14 canonical verification/login policy, out-of-scope behavior, and release evidence expectations are documented.

### Phase 243: Backend Verification Resend Confirm Reliability

**Goal**: Make backend registration verification, resend, confirm, activation, and local profile state consistent.
**Depends on**: Phase 242.
**Requirements**: VERIFY-01
**Status**: Complete.
**Success Criteria**:

1. Register/resend/confirm/login paths produce consistent Cognito/local verification state.
2. Expired, wrong-code, already-confirmed, missing-profile, disabled-user, and rate-limited cases return clear support-safe errors.
3. Account operations verification state reflects resend eligibility, confirmation status, and support action.
4. Focused backend tests cover successful and failed verification lifecycle behavior.

### Phase 244: Login Code And Passwordless Policy Resolution

**Goal**: Remove or complete login-code/passwordless behavior so users see one dependable auth policy.
**Depends on**: Phase 243.
**Requirements**: LOGIN-01
**Status**: Active.
**Success Criteria**:

1. Product-visible login-code/passwordless surfaces are either backed by real Cognito custom auth or hidden/deferred.
2. Email/password login remains the canonical verified-account login path unless custom auth is fully implemented.
3. Unverified accounts are refused token return with clear frontend/support-safe messaging.
4. Focused tests cover canonical login success, unverified login refusal, unsupported login-code attempts, and policy documentation.

### Phase 245: Frontend Verification Recovery And Admin Support Visibility

**Goal**: Make verification/login recovery states clear and actionable for users and support/admins.
**Depends on**: Phase 244.
**Requirements**: SUPPORT-01
**Status**: Planned.
**Success Criteria**:

1. Frontend verification/login screens render pending, expired, wrong-code, rate-limited, verified, and support-needed states clearly.
2. Admin/support account operations surfaces show bounded verification evidence, resend eligibility, recovery state, and support action.
3. Support/admin recovery actions are explicit, audited, and exclude raw codes/secrets/tokens.
4. Focused frontend/backend tests cover verification recovery and admin support visibility.

### Phase 246: v5.14 Verification Login Reliability Gate

**Goal**: Close v5.14 with evidence that verification/login reliability is locally complete and externally blocked items are explicit.
**Depends on**: Phase 245.
**Requirements**: VERIFY-48
**Status**: Planned.
**Success Criteria**:

1. Focused backend tests pass for verification lifecycle, login policy, support visibility, and recovery audit.
2. Frontend lint/build and focused e2e pass for verification/login recovery workflows.
3. Live Cognito/email smoke is recorded as blocked or completed based on environment availability.
4. Docs, roadmap, requirements, state, milestone snapshots, and release evidence are updated.
5. Next milestone recommendation is explicit and separates usage/quota stability from external auth-provider activation.

## Future Milestone Directions

- **v5.15 Usage, Quota, And Product Stability**: usage metering gaps, quota reconciliation, user-visible usage explanations, support views, health checks, and regression gates.
- **External Auth Delivery Activation**: production Cognito/email delivery smoke, custom-auth rollout, native auth handoff, and deliverability evidence if credentials/rollout approvals unblock.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 242 Verification And Login Reality Audit | v5.14 | 1/1 | Complete | 2026-07-05 |
| 243 Backend Verification Resend Confirm Reliability | v5.14 | 1/1 | Complete | 2026-07-05 |
| 244 Login Code And Passwordless Policy Resolution | v5.14 | 0/1 | Active | - |
| 245 Frontend Verification Recovery And Admin Support Visibility | v5.14 | 0/1 | Planned | - |
| 246 v5.14 Verification Login Reliability Gate | v5.14 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTHREL-01 | Phase 242 | Complete |
| VERIFY-01 | Phase 243 | Complete |
| LOGIN-01 | Phase 244 | Active |
| SUPPORT-01 | Phase 245 | Planned |
| VERIFY-48 | Phase 246 | Planned |
