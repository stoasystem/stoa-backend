# Roadmap: v5.6 Core Product Operations Completion

**Status:** Active planning
**Created:** 2026-07-02
**Updated:** 2026-07-02 after code-reality audit
**Research:** `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-CURRENT-REALITY-AUDIT.md`

## Goal

Complete the real-user operational layer before any native app buildout: paid entitlement, usage ledger, account/email verification, login-code policy, customer billing state, and admin support visibility.

## Current Reality

The codebase already has useful foundations:

- Cognito-backed password registration/login/refresh/logout and forgot/reset password.
- Parent subscription and billing endpoints.
- Stripe checkout, webhook handling, billing events, rollout controls, refunds, and accounting handoff.
- Daily question quota counters.
- Admin user update and subscription billing/request views.

The current gaps are lower-level product correctness:

- Registration marks email as verified by backend policy instead of running a real email verification lifecycle.
- Login has no separate login-code flow; it is password-only Cognito auth.
- Billing activation updates the parent profile, but student question quota reads the student's own `subscription_tier`.
- Usage is an atomic daily counter, not a durable ledger that can explain product area, entitlement source, period, and idempotency.
- Parent/admin views do not yet expose a complete paid entitlement, usage, and verification support picture.

## Implementation Strategy

- Keep Cognito password auth and existing billing routes stable.
- Add an effective entitlement resolver before changing quota enforcement.
- Add a durable usage ledger beside existing counters, then reconcile counters from ledger behavior.
- Implement real email verification and resolve login-code product policy explicitly.
- Add customer/admin visibility after entitlement and ledger semantics are stable.
- Focus on functionality and internal product completeness; avoid broad unrelated security/compliance work in this phase.

## Phases

- [x] **Phase 201: Core Product Operations Gap Audit And Contract** - Document current code reality, classify gaps, and lock implementation order.
- [ ] **Phase 202: Effective Entitlements And Paid Access Enforcement** - Resolve paid access from parent billing/manual overrides and apply it to student usage limits.
- [ ] **Phase 203: Usage Ledger And Quota Reconciliation** - Add durable plan-governed usage events and reconcile daily/monthly counters.
- [ ] **Phase 204: Email Verification And Login Code Policy** - Replace placeholder email verification and decide/implement login-code behavior.
- [ ] **Phase 205: Customer Admin Visibility And Release Gate** - Expose customer/admin support state and close v5.6 with focused verification.

## Phase Details

### Phase 201: Core Product Operations Gap Audit And Contract

**Goal**: Establish the real feature state from code and reset the development plan around the missing paid/auth/usage details.
**Depends on**: Existing auth/account lifecycle, subscription operations, billing provider readiness, daily quota tracking, admin user views, and current `stoa_docs` gap list.
**Requirements**: COREOPS-01
**Success Criteria** (what must be TRUE):

  1. Current auth/register/login/forgot/reset/email-verification behavior is documented with code references.
  2. Current subscription/billing/manual-plan behavior is documented with code references.
  3. Current quota/usage/admin/customer visibility behavior is documented with code references.
  4. Missing flows are classified as must-build now, defer, or external prerequisite.
  5. Phase 202-205 implementation order is updated around the real gaps.

**Plans**: 1/1 plans complete

Plans:

- [x] 201-01: Audit and define core product operations completion contract.

### Phase 202: Effective Entitlements And Paid Access Enforcement

**Goal**: Make paid plan state determine actual usable limits for linked students.
**Depends on**: Phase 201
**Requirements**: COREOPS-02
**Success Criteria** (what must be TRUE):

  1. Effective entitlement resolver combines student profile, parent binding, parent subscription tier, billing status, manual overrides, rollout controls, cancellation/expiry, and pending payment.
  2. Student question quota uses effective entitlement instead of only the student's local `subscription_tier`.
  3. Active parent paid billing can grant the intended student limits; canceled/expired/past-due states fall back according to policy.
  4. Manual admin overrides remain supported and visible as entitlement source.
  5. Tests cover free student, paid parent-linked student, pending checkout, active invoice-paid, canceled/expired, manual override, and missing binding.

**Plans**: 0/1 plans created

Plans:

- [ ] 202-01: Implement effective entitlements and paid access enforcement.

### Phase 203: Usage Ledger And Quota Reconciliation

**Goal**: Make plan-governed usage durable, inspectable, and reconcilable with counters.
**Depends on**: Phase 202
**Requirements**: COREOPS-03
**Success Criteria** (what must be TRUE):

  1. Plan-governed actions write usage events with actor, subject, product area, action, quantity, entitlement source, period, and idempotency metadata.
  2. Existing daily question counters remain compatible while usage ledger is introduced.
  3. Question submission, OCR/AI answer generation, teacher-help request, and chat/hint counters have a clear ledger/counter policy.
  4. Admin usage query can inspect usage by parent/student/user, period, product area, and entitlement source.
  5. Tests cover idempotent event writes, quota exhaustion, ledger/counter consistency, and basic admin usage queries.

**Plans**: 0/1 plans created

Plans:

- [ ] 203-01: Implement usage ledger and quota reconciliation.

### Phase 204: Email Verification And Login Code Policy

**Goal**: Turn verification from placeholder metadata into explicit account flows.
**Depends on**: Phase 203
**Requirements**: COREOPS-04
**Success Criteria** (what must be TRUE):

  1. Registration no longer silently treats new emails as product-verified unless intentionally configured for an internal environment.
  2. Email verification supports requested, sent, verified, expired, failed, resent, wrong-code, and already-verified states.
  3. Verification codes have expiry, attempt limits, resend behavior, and account-state effects.
  4. Login-code policy is explicit: either implement a supported email login-code flow or formally keep login password-only and remove unsupported UI/API expectations.
  5. Forgot/reset password remains compatible with existing Cognito behavior.

**Plans**: 0/1 plans created

Plans:

- [ ] 204-01: Implement email verification and login code policy.

### Phase 205: Customer Admin Visibility And Release Gate

**Goal**: Make paid/auth/usage state explainable to customers and admins, then close v5.6.
**Depends on**: Phase 204
**Requirements**: VERIFY-39
**Success Criteria** (what must be TRUE):

  1. Parent/customer views expose effective plan, billing status, entitlement source, usage summary, and email verification state.
  2. Admin views expose account verification status, effective entitlement, usage ledger summary, billing provider state, and support timestamps.
  3. Focused backend tests pass for paid entitlement, usage ledger, verification code, login/account state, and customer/admin visibility.
  4. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.6 work.
  5. Final audit records rollout state and recommends v5.7.

**Plans**: 0/1 plans created

Plans:

- [ ] 205-01: Verify customer/admin visibility and v5.6 release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 201 Core Product Operations Gap Audit And Contract | v5.6 | 1/1 | Complete | 2026-07-02 |
| 202 Effective Entitlements And Paid Access Enforcement | v5.6 | 0/1 | Active | - |
| 203 Usage Ledger And Quota Reconciliation | v5.6 | 0/1 | Planned | - |
| 204 Email Verification And Login Code Policy | v5.6 | 0/1 | Planned | - |
| 205 Customer Admin Visibility And Release Gate | v5.6 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| COREOPS-01 | Phase 201 | Complete |
| COREOPS-02 | Phase 202 | Planned |
| COREOPS-03 | Phase 203 | Planned |
| COREOPS-04 | Phase 204 | Planned |
| VERIFY-39 | Phase 205 | Planned |

---
*Last updated: 2026-07-02 after code-reality audit and task reordering.*
