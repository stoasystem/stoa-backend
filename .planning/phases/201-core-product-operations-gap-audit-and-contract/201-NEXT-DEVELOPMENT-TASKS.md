# v5.6 Next Development Tasks

**Date:** 2026-07-02
**Basis:** `201-CURRENT-REALITY-AUDIT.md`

## Phase 202: Effective Entitlements And Paid Access Enforcement

Task 202-A: Create entitlement resolver.

- Inputs: user profile, parent/student binding, parent profile, parent billing summary, manual override, billing status, rollout controls.
- Output: effective plan, limits, entitlement source, billing state, period, blocking reason, support explanation.
- First integration point: question quota.

Task 202-B: Apply parent paid entitlement to linked students.

- If parent billing is active and child binding is active, student gets paid plan limits.
- If billing is checkout_pending/past_due/canceled/payment_failed, use explicit fallback policy.
- If no active binding exists, keep student free unless student has direct override.

Task 202-C: Replace misleading auth plan output.

- Stop returning hardcoded `subscriptionStatus="trial"` and `plan="free_trial"` when real entitlement is available.
- Add tests for student/parent/admin profile outputs.

## Phase 203: Usage Ledger And Quota Reconciliation

Task 203-A: Add usage event repository/service.

- Event fields: event ID, actor user ID, subject/student ID, parent ID, product area, action, quantity, entitlement source, period key, idempotency key, created at.
- Use DynamoDB single-table patterns unless a specific access pattern proves insufficient.

Task 203-B: Write usage events for plan-governed actions.

- Question submit.
- OCR/AI answer generation.
- Teacher-help request.
- Chat message.
- Hint request.

Task 203-C: Keep counters compatible.

- Current daily question counter remains the enforcement path until ledger is proven.
- Add reconciliation behavior or summary projection for admin/customer display.

Task 203-D: Add admin usage query.

- Query by parent/student/user, period, product area, and entitlement source.
- Start with bounded scans if acceptable for internal development; optimize later if access patterns require it.

## Phase 204: Email Verification And Login Code Policy

Task 204-A: Replace placeholder email verification status.

- Registration should create `pending_verification` unless an explicit internal bypass flag is enabled.
- Add verification request/send/verify/resend/expire/fail states.

Task 204-B: Add verification code storage and validation.

- Store hashed or otherwise non-plain code material, expiry, attempts, resend count, last sent at.
- Confirm wrong-code, expired, already-verified, and resend behavior.

Task 204-C: Decide login-code policy.

- Preferred low-risk policy for current architecture: password login remains primary; email verification code is separate.
- If product requires login-by-code, plan Cognito custom auth or another token-compatible design before implementation.

Task 204-D: Keep forgot/reset password stable.

- Existing Cognito forgot/reset behavior remains the password recovery path.

## Phase 205: Customer/Admin Visibility And Release Gate

Task 205-A: Parent/customer account state.

- Add effective plan, billing status, entitlement source, usage summary, and email verification state to subscription/account views.

Task 205-B: Admin support state.

- Add account verification status, effective entitlement, usage ledger summary, billing provider status, and support timestamps to admin views.

Task 205-C: Release gate tests.

- Focused backend tests for:
  - parent-paid linked student quota
  - free/pending/canceled/manual override entitlement
  - usage ledger write/idempotency
  - email verification success/wrong/expired/resend
  - customer/admin response shapes

Task 205-D: Update milestone docs.

- Requirements, roadmap, state, gap audit, remaining-feature queue, and final milestone audit.
