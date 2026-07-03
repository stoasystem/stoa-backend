# Final-Polish Product Milestone Queue

**Date:** 2026-07-03
**Basis:** `201-CURRENT-REALITY-AUDIT.md`

Phase 201 identified that the remaining entitlement, usage, verification, and operations-visibility work is too large to treat as a few implementation phases inside one broad milestone. The work is now split into complete feature milestones. v5.6 is active; v5.7 through v5.9 are planned follow-up milestones.

## v5.6: Effective Entitlements And Paid Access Enforcement

Purpose: make paid access actually affect linked student usage limits.

Implementation phases:

- Phase 202: Entitlement Contract And Access Policy.
- Phase 203: Entitlement Resolver Service And Parent Child Mapping.
- Phase 204: Student Paid Access Enforcement.
- Phase 205: Entitlement Visibility And Focused Tests.
- Phase 206: v5.6 Entitlement Release Gate.

Detailed tasks:

- Define effective entitlement inputs: student profile tier, parent billing status, parent profile tier, parent-child binding, manual override, rollout controls, failed/pending/canceled payment states, and internal/test bypasses.
- Implement a resolver service that returns effective plan, limits, entitlement source, current period, blocking reason, and support/admin explanation.
- Apply active parent paid entitlement to linked students when the binding is active and the billing state allows access.
- Keep free/pending/canceled/payment-failed states deterministic; do not silently grant paid access when the source state is ambiguous.
- Replace misleading auth profile output such as hardcoded `subscriptionStatus="trial"` and `plan="free_trial"` where a real effective entitlement is available.
- Enforce resolved entitlement in question quota first; leave other plan-governed actions to v5.7 instrumentation unless they already share the same quota gate.
- Add focused tests for linked-student paid quota, free fallback, pending/canceled fallback, manual override, parent/admin visibility shape, and resolver edge cases.

Release gate:

- Backend tests pass for entitlement resolver and question quota enforcement.
- Parent-paid linked student can use the intended quota in local/integration evidence.
- Free or inactive billing does not receive paid quota.
- Admin/manual override behavior is explicit and test-covered.
- Roadmap, requirements, state, and milestone summary are updated.

## v5.7: Usage Ledger And Quota Reconciliation

Purpose: record user/student consumption durably enough for support, billing review, quota investigation, and later customer-facing usage summaries.

Detailed tasks:

- Define usage event contract: event ID, actor user ID, subject/student ID, parent ID, product area, action, quantity, entitlement source, plan period, idempotency key, created-at timestamp, and display-safe metadata.
- Add usage event repository/service using the existing DynamoDB patterns unless an access pattern requires a new table/index.
- Write idempotent usage events for question submit, OCR/AI answer generation, teacher-help request, chat message, and hint request.
- Keep the current question counter as the enforcement path until ledger reconciliation is proven.
- Add reconciliation/projection behavior that can compare counters with ledger events for the same student and period.
- Add admin usage query by parent/student/user, period, product area, action, and entitlement source.
- Prepare parent/customer usage summary response shape for v5.9 visibility.

Release gate:

- Ledger writes are idempotent and do not double-count retried requests.
- Existing quota tests remain compatible.
- Admin can inspect usage events/summaries without raw database access.
- Reconciliation evidence documents how current counters and ledger rows agree.

## v5.8: Email Verification And Login Code Policy

Purpose: make account verification real and remove ambiguity around login-code behavior.

Detailed tasks:

- Replace default product verification state with `pending_verification` unless an explicit internal bypass flag is active.
- Add verification request/send/verify/resend/expire/fail/already-verified behavior.
- Store code material safely with expiry, attempt count, resend count, last-sent timestamp, and invalidation of replaced active codes.
- Add endpoints and service logic for request verification, resend verification, and confirm verification.
- Define login-code policy:
  - Low-risk path: password login remains primary and email code is only account verification.
  - If product requires login-by-code, implement a Cognito-compatible custom-auth or equivalent session-producing design.
- Preserve existing Cognito forgot/reset password behavior.
- Add customer/admin-visible verification state fields for v5.9.

Release gate:

- New account verification state is no longer misleading.
- Wrong, expired, resent, already-verified, and successful code paths are test-covered.
- Login-code policy is explicit in API behavior and docs.
- Existing password login, refresh, logout, forgot, and reset flows remain stable.

## v5.9: Parent Admin Operations Visibility

Purpose: make the effective account state visible to parents and admins so support does not need direct database inspection.

Detailed tasks:

- Add parent account summary with current plan, effective entitlement, billing status, current-period usage summary, email verification state, and available actions.
- Add admin account detail with entitlement source, manual override state, billing provider status, recent provider event, usage summary/recent events, quota state, verification status, and support timestamps.
- Add bounded support actions where the backend already has safe primitives; leave risky write operations to later explicit requirements.
- Connect frontend/admin handoff contracts so product surfaces know exactly which fields are available.
- Produce final core-operations closeout evidence: backend tests, API response samples, docs, and next-expansion decision.

Release gate:

- Parent/customer and admin response shapes cover entitlement, billing, usage, and verification.
- Admin-only API checks are documented.
- Final audit decides whether native app, rich curriculum editor UI, live warehouse/BI, external support activation, or production content import should be next.

## Later Expansion Candidates

- Native iOS/Android app implementation and app-store rollout.
- Live APNS/FCM provider activation.
- Final live Stripe/TWINT production activation after provider/finance prerequisites are available.
- External support provider/CRM activation.
- Rich curriculum editor frontend implementation and production content import.
- Live warehouse/BI deployment.
