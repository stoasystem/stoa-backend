# Core Product Operations Completion Contract

## Function Purpose

v5.6 completes the product-operation layer that real users depend on before mobile app expansion:

- Paid access must translate into effective entitlement.
- User/student usage must be durably recorded and inspectable.
- Email verification must be a real stateful flow.
- Login verification-code policy must be explicit.
- Parents/customers and admins must see understandable billing, usage, and verification state.

## Not This Feature

- Not native iOS/Android app implementation.
- Not final live Stripe/TWINT activation unless prerequisites are available.
- Not external support provider or CRM activation.
- Not autonomous tutoring without human review.
- Not broad unrelated security/compliance testing.

## Current Concern

The platform has advanced planning around mobile, AI, curriculum, reports, and dispatch, but user testing found incomplete lower-level details:

- Paid functionality is not fully connected to visible/effective usage rights.
- Backend usage records are not comprehensive enough for support and billing.
- Login verification code behavior is incomplete or undefined.
- Email verification is currently not a complete customer-facing lifecycle.

## Effective Entitlement Model

Effective entitlement should be derived from:

- User role and account state.
- Subscription tier.
- Billing provider status.
- Manual admin override.
- Rollout controls.
- Cancellation, expiry, failed payment, or pending checkout state.
- Trial or internal/test state where allowed.

The model should return:

- Effective plan.
- Entitlement source.
- Limits.
- Current period.
- Blocking reason if access is limited.
- Support/admin explanation.

## Usage Ledger Model

Usage events should record:

- `event_id`.
- `actor_user_id`.
- `subject_user_id` or `student_id`.
- `parent_id` where relevant.
- `product_area`: question, OCR, AI answer, teacher help, assignment, report, billing.
- `action`.
- `quantity`.
- `entitlement_source`.
- `period_key`.
- `idempotency_key`.
- `created_at`.
- Optional metadata safe for admin/support display.

Initial priority should cover plan-governed actions:

- Question submission.
- OCR/AI answer generation where separately limited.
- Teacher-help request.
- Assignment or practice generation if limited.

## Verification Code Lifecycle

Email verification code states:

- `not_requested`.
- `requested`.
- `sent`.
- `verified`.
- `expired`.
- `failed`.
- `resent`.

Required behavior:

- Codes expire.
- Wrong attempts are counted.
- Resend creates a new active code or invalidates the previous code.
- Already verified accounts return stable success state.
- Verification updates customer/admin-visible account state.

## Login Code Policy

Phase 201 must resolve product policy:

- Option A: Password login remains primary; verification code is for email verification only.
- Option B: Add email-code login or second-factor code flow.

The chosen policy must be explicit before implementation. Existing Cognito-backed password/session behavior should not be broken.

## Customer Visibility

Parent/customer surfaces should expose:

- Current plan.
- Billing status.
- Effective entitlement.
- Usage summary for the current period.
- Email verification status.
- Actions available: verify email, resend verification, manage subscription, contact support.

## Admin Visibility

Admin/support surfaces should expose:

- Account verification state.
- Effective entitlement and source.
- Billing provider status and last provider event.
- Usage ledger summary and recent events.
- Quota/limit state.
- Support-relevant timestamps.
- Bounded admin actions with audit evidence where needed.

## Follow-Up Phases

- Phase 202: effective entitlements and paid access enforcement.
- Phase 203: usage ledger and quota reconciliation.
- Phase 204: email verification and login code policy.
- Phase 205: customer/admin visibility, release gate, evidence, and next milestone decision.
