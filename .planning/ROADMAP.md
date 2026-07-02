# Roadmap: v5.6 Core Product Operations Completion

**Status:** Active planning
**Created:** 2026-07-02
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Complete the product-operation details required for real user usage before starting native app buildout: paid access, usage tracking, account verification, login verification codes, billing state, and admin visibility.

## Purpose

STOA has many advanced learning, reporting, dispatch, and billing foundations, but several basic production-facing details are still incomplete. If those remain missing, a real user can sign up, pay, use quota, or recover/login to an account without the platform having a reliable source of truth for entitlement, usage, and verification state.

v5.6 answers: "When a real parent/student pays, logs in, verifies email, consumes quota, and needs support/admin inspection, what exact backend state changes and admin/customer surfaces prove the product is working?"

## Implementation Strategy

- Re-audit existing billing, subscription, quota, auth, email verification, password reset, and admin visibility paths before coding.
- Build a unified entitlement/usage model that connects paid billing state to effective plan limits and per-user/per-student usage ledgers.
- Replace the current placeholder email verification policy with explicit verification-code lifecycle and status transitions.
- Add or complete login verification code flows where required by product policy, while preserving existing Cognito-backed password login/session refresh.
- Add admin and customer-facing billing/usage/verification visibility so support can explain account state without inspecting raw data stores.
- Prioritize functionality and internal product completeness; avoid broad unrelated security/compliance work in this internal-development phase.

## Phases

- [ ] **Phase 201: Core Product Operations Gap Audit And Contract** - Audit current paid access, usage, auth verification, login code, email verification, and admin visibility gaps; define exact state model and implementation boundaries.
- [ ] **Phase 202: Paid Entitlements And Usage Ledger** - Connect billing/subscription state to effective plan limits and create a durable usage ledger/admin query surface.
- [ ] **Phase 203: Email Verification And Login Code Completion** - Implement or complete verification-code lifecycle for email verification and login-code flows required by product policy.
- [ ] **Phase 204: Customer And Admin Billing Usage Visibility** - Expose parent/customer and admin surfaces for plan, payment, entitlement, usage, verification, and support state.
- [ ] **Phase 205: v5.6 Core Product Operations Release Gate** - Verify end-to-end paid/usage/auth-verification behavior, update docs, and recommend the next milestone.

## Phase Details

### Phase 201: Core Product Operations Gap Audit And Contract

**Goal**: Establish the exact missing backend/product details for paid access, usage ledger, account verification, login codes, email verification, and admin visibility.
**Depends on**: Existing auth/account lifecycle, subscription operations, billing provider readiness, daily quota tracking, admin user views, and current `stoa_docs` gap list.
**Requirements**: COREOPS-01
**Success Criteria** (what must be TRUE):

  1. Existing paid, subscription, quota, billing, auth, forgot/reset password, email verification, and admin visibility behavior is documented from code.
  2. Missing flows are classified as must-build now, defer, or external prerequisite.
  3. Effective entitlement state is defined from subscription tier, billing status, manual admin overrides, and provider events.
  4. Usage ledger events, dimensions, retention, admin queries, and customer-facing summaries are defined.
  5. Verification-code lifecycle for email verification and login-code policy is defined.

**Plans**: 0/1 plans complete

Plans:

- [ ] 201-01: Audit and define core product operations completion contract.

### Phase 202: Paid Entitlements And Usage Ledger

**Goal**: Make paid plan state and quota usage reliable enough for real user operations.
**Depends on**: Phase 201
**Requirements**: COREOPS-02
**Success Criteria** (what must be TRUE):

  1. Effective entitlement calculation is deterministic and auditable.
  2. Question/AI/OCR/teacher-help or other plan-governed usage writes durable usage events.
  3. Daily/monthly counters derive from or reconcile with the usage ledger.
  4. Admins can inspect usage by parent/student/user, period, product area, and entitlement source.
  5. Tests cover free, paid, pending payment, canceled/expired, manual override, and quota exhaustion states.

**Plans**: 0/1 plans created

Plans:

- [ ] 202-01: Implement paid entitlement and usage ledger.

### Phase 203: Email Verification And Login Code Completion

**Goal**: Complete user verification details that currently behave as placeholders or partial Cognito handoffs.
**Depends on**: Phase 202
**Requirements**: COREOPS-03
**Success Criteria** (what must be TRUE):

  1. Email verification has explicit requested, sent, verified, expired, failed, and resent states.
  2. Verification codes are stored/validated through a backend-mediated lifecycle with expiry and attempt limits.
  3. Login verification-code behavior is implemented or explicitly scoped to a supported policy such as password login plus email verification.
  4. Forgot/reset password remains compatible with existing Cognito behavior.
  5. Tests cover successful verification, wrong code, expired code, resend, already verified, and login/account-state effects.

**Plans**: 0/1 plans created

Plans:

- [ ] 203-01: Implement email verification and login code completion.

### Phase 204: Customer And Admin Billing Usage Visibility

**Goal**: Make plan, payment, entitlement, usage, and verification state visible enough for customer self-service and admin support.
**Depends on**: Phase 203
**Requirements**: COREOPS-04
**Success Criteria** (what must be TRUE):

  1. Parent/customer subscription views distinguish plan, billing status, entitlement status, renewal/cancel state, and usage summary.
  2. Admin views show account verification status, usage ledger summary, current entitlement, billing provider state, and support-relevant timestamps.
  3. Admin actions needed for internal development are explicit, audited, and bounded.
  4. API responses avoid silent demo fallback and expose actionable state for frontend implementation.
  5. Tests cover customer and admin response shapes for the main paid/auth/usage states.

**Plans**: 0/1 plans created

Plans:

- [ ] 204-01: Implement customer and admin billing usage visibility.

### Phase 205: v5.6 Core Product Operations Release Gate

**Goal**: Close v5.6 with end-to-end verification of paid access, usage ledger, verification codes, customer/admin visibility, and updated next-stage docs.
**Depends on**: Phase 204
**Requirements**: VERIFY-39
**Success Criteria** (what must be TRUE):

  1. Focused backend tests pass for paid entitlement, usage ledger, verification code, login/account state, and admin/customer visibility.
  2. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.6 work.
  3. Release evidence identifies exact commit SHAs and any frontend/native follow-up requirements.
  4. Final audit records rollout state: contract-ready, entitlement-ready, usage-ready, verification-ready, support-visible, blocked, or deferred.
  5. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans created

Plans:

- [ ] 205-01: Verify v5.6 core product operations release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 201 Core Product Operations Gap Audit And Contract | v5.6 | 0/1 | Active | - |
| 202 Paid Entitlements And Usage Ledger | v5.6 | 0/1 | Planned | - |
| 203 Email Verification And Login Code Completion | v5.6 | 0/1 | Planned | - |
| 204 Customer And Admin Billing Usage Visibility | v5.6 | 0/1 | Planned | - |
| 205 v5.6 Core Product Operations Release Gate | v5.6 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| COREOPS-01 | Phase 201 | Planned |
| COREOPS-02 | Phase 202 | Planned |
| COREOPS-03 | Phase 203 | Planned |
| COREOPS-04 | Phase 204 | Planned |
| VERIFY-39 | Phase 205 | Planned |

---
*Last updated: 2026-07-02 after correcting v5.6 toward core product operations completion.*
