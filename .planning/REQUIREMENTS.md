# Requirements: v5.6 Core Product Operations Completion

**Milestone:** v5.6
**Status:** Active planning
**Created:** 2026-07-02
**Updated:** 2026-07-02 after code-reality audit
**Research:** `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-CURRENT-REALITY-AUDIT.md`

## Purpose

Complete the operational product details that must work before real users can reliably use STOA: paid access, usage tracking, login verification code policy, email verification, customer billing state, and admin support visibility.

The previous native app plan was premature. Native apps remain useful later, but they should not precede core account/payment/usage correctness.

## Requirements

### COREOPS-01 Core Product Operations Gap Audit And Contract

Implementers have a code-grounded audit of the missing paid/auth/usage details before code expands.

Acceptance criteria:

- Existing auth/register/login/forgot/reset/email-verification behavior is documented with code references.
- Existing subscription, billing, manual plan, webhook, and rollout-control behavior is documented with code references.
- Existing quota/usage behavior and admin/customer visibility are documented with code references.
- Missing details are classified as must-build now, defer, or external prerequisite.
- Phase 202-205 implementation order is updated from the real gaps.

### COREOPS-02 Effective Entitlements And Paid Access Enforcement

Paid access affects actual student limits through a deterministic entitlement resolver.

Acceptance criteria:

- Effective entitlement resolver combines student profile, parent binding, parent subscription tier, billing status, manual overrides, rollout controls, cancellation/expiry, and pending payment.
- Student question quota uses effective entitlement rather than only the student's local `subscription_tier`.
- Active paid parent billing can grant linked student limits according to product policy.
- Pending, canceled, expired, failed-payment, missing-binding, and manual-override states have deterministic fallback behavior.
- Tests cover free student, paid parent-linked student, pending checkout, active invoice-paid, canceled/expired, manual override, and missing binding.

### COREOPS-03 Usage Ledger And Quota Reconciliation

Plan-governed usage is durably recorded and inspectable.

Acceptance criteria:

- Usage event records include actor, subject, parent/student relationship where available, product area, action, quantity, entitlement source, period, idempotency key, and timestamp.
- Existing daily question counters remain compatible while ledger writes are introduced.
- Question submission, OCR/AI answer generation, teacher-help request, chat, and hint usage have a clear ledger/counter policy.
- Admin can inspect usage by parent/student/user, period, product area, and entitlement source.
- Tests cover idempotent event writes, quota exhaustion, ledger/counter consistency, and admin usage queries.

### COREOPS-04 Email Verification And Login Code Policy

Account verification and login-code behavior are explicit product flows, not placeholders.

Acceptance criteria:

- Registration no longer silently treats new emails as product-verified unless intentionally configured for an internal environment.
- Email verification supports requested, sent, verified, expired, failed, resent, wrong-code, and already-verified states.
- Verification codes have expiry, resend, attempt-limit, and account-state behavior.
- Login-code policy is explicit: implement a supported email login-code flow or formally keep login password-only and remove unsupported UI/API expectations.
- Forgot/reset password remains compatible with existing Cognito-backed behavior.

### VERIFY-39 Customer Admin Visibility And v5.6 Release Gate

v5.6 closes with customer/admin visibility and end-to-end evidence for the core product operations flows.

Acceptance criteria:

- Parent/customer views distinguish effective plan, billing status, entitlement source, renewal/cancel state, usage summary, and email verification status.
- Admin views expose account verification status, usage ledger summary, effective entitlement, billing provider state, and support timestamps.
- Focused tests pass for paid entitlement, usage ledger, verification code, login/account state, and customer/admin visibility.
- Release evidence identifies backend/frontend commits and explicitly documents deferred native app, live provider, or production rollout items.
- Final audit records rollout state and updates the next milestone recommendation.

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
| COREOPS-01 | Phase 201 | Complete |
| COREOPS-02 | Phase 202 | Planned |
| COREOPS-03 | Phase 203 | Planned |
| COREOPS-04 | Phase 204 | Planned |
| VERIFY-39 | Phase 205 | Planned |
