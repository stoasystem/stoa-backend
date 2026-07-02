# Requirements: v5.6 Core Product Operations Completion

**Milestone:** v5.6
**Status:** Active planning
**Created:** 2026-07-02
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`, `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`

## Purpose

Complete the operational product details that must work before real users can reliably use STOA: paid access, usage tracking, login verification code policy, email verification, customer billing state, and admin support visibility.

The previous v5.6 native app plan was premature. Native apps remain useful later, but they should not precede core account/payment/usage correctness.

## Implementation Strategy

- Audit the existing auth, billing, subscription, quota, and admin code paths before implementation.
- Define a deterministic entitlement model from manual plan state, provider billing state, rollout controls, and admin overrides.
- Add a durable usage ledger for plan-governed actions such as questions, OCR/AI usage, and teacher-help requests.
- Complete email verification and login-code behavior with explicit state transitions, expiry, resend, and failure handling.
- Expose customer/admin visibility for plan, usage, verification, billing, and support status.
- Keep focus on functional completeness during internal development; broad production security testing is not the priority for this phase.

## Requirements

### COREOPS-01 Core Product Operations Gap Audit And Contract

Implementers have a concrete contract for the missing paid/auth/usage details before code expands.

Acceptance criteria:

- Existing auth, subscription, billing, quota, usage, email verification, forgot/reset password, and admin visibility behavior is documented from code.
- Missing details are classified as must-build now, defer, or external prerequisite.
- Effective entitlement state is defined from subscription tier, billing status, manual admin override, provider events, and rollout controls.
- Usage ledger event types, dimensions, retention, summaries, and admin query requirements are defined.
- Verification-code lifecycle for email verification and login-code policy is defined.

### COREOPS-02 Paid Entitlements And Usage Ledger

Paid access and plan-governed usage are tracked through reliable backend state.

Acceptance criteria:

- Effective entitlement calculation is deterministic, testable, and exposed through a stable internal service/API shape.
- Plan-governed actions write durable usage events with actor, subject, product area, period, entitlement source, and idempotency metadata.
- Daily/monthly counters can derive from or reconcile with usage ledger state.
- Admins can inspect usage by parent/student/user, period, product area, and entitlement source.
- Tests cover free, paid, pending payment, canceled/expired, manual override, and quota exhaustion states.

### COREOPS-03 Email Verification And Login Code Completion

Account verification and login-code behavior are explicit product flows, not placeholders.

Acceptance criteria:

- Email verification supports requested, sent, verified, expired, failed, and resent states.
- Verification codes have expiry, resend, attempt-limit, and already-verified behavior.
- Login verification-code policy is implemented or explicitly resolved to the supported product policy.
- Forgot/reset password remains compatible with existing Cognito-backed behavior.
- Tests cover success, wrong code, expired code, resend, already verified, and account/login effects.

### COREOPS-04 Customer And Admin Billing Usage Visibility

Customers and admins can understand paid access, usage, and verification state without inspecting raw data stores.

Acceptance criteria:

- Parent/customer subscription views distinguish plan, billing status, entitlement status, renewal/cancel state, and usage summary.
- Admin views expose account verification status, usage ledger summary, effective entitlement, billing provider state, and support timestamps.
- Required internal admin actions are explicit, bounded, and audit-friendly.
- API responses avoid silent demo fallback and expose actionable frontend state.
- Tests cover customer/admin response shapes for key paid/auth/usage states.

### VERIFY-39 v5.6 Core Product Operations Release Gate

v5.6 closes with end-to-end evidence for the core product operations flows.

Acceptance criteria:

- Focused tests pass for paid entitlement, usage ledger, verification code, login/account state, and customer/admin visibility.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.6 work.
- Release evidence identifies backend/frontend commits and explicitly documents deferred native app, live provider, or production rollout items.
- Final audit records rollout state: contract-ready, entitlement-ready, usage-ready, verification-ready, support-visible, blocked, or deferred.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Native iOS/Android app buildout after core account/payment/usage correctness.
- Live APNS/FCM provider credentials and app-store release.
- Rich curriculum editor frontend implementation.
- Live warehouse/BI deployment.
- Real external support provider/CRM activation.

## Out of Scope

- Native app implementation in this milestone.
- Final live Stripe/TWINT customer charging unless external prerequisites are ready.
- Real external support provider or CRM/customer writes.
- Fully autonomous AI tutoring without human review.
- Broad compliance/security hardening unrelated to paid/auth/usage functionality.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| COREOPS-01 | Phase 201 | Planned |
| COREOPS-02 | Phase 202 | Planned |
| COREOPS-03 | Phase 203 | Planned |
| COREOPS-04 | Phase 204 | Planned |
| VERIFY-39 | Phase 205 | Planned |
