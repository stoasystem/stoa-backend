# Current Reality Audit: Core Product Operations Final Polish

**Date:** 2026-07-02
**Scope:** paid functionality, usage records, login verification code policy, email verification, customer/admin billing and support visibility.

## Executive Summary

The current codebase has working foundations for Cognito password auth, parent subscription flows, Stripe checkout/webhooks, billing records, admin billing views, and daily question quota counters.

The product is not yet ready to treat those foundations as a complete real-user operations layer:

- Email verification is intentionally bypassed at registration.
- Login verification code behavior is not implemented.
- Parent paid billing does not yet clearly grant linked student usage limits.
- Usage records are counters, not a durable support/audit ledger.
- Parent/admin views do not show a complete entitlement + usage + verification picture.

## Reality Matrix

| Area | Current reality | Code evidence | Gap |
|------|-----------------|---------------|-----|
| Registration | Creates Cognito user with suppressed email, sets permanent password, adds role group, writes profile. | `src/stoa/routers/auth.py:277` | Functional registration exists. |
| Email verification | Cognito `email_verified` is set to `true`; profile uses `email_verification_status=admin_marked_verified`; no request/verify/resend lifecycle. | `src/stoa/routers/auth.py:290`, `src/stoa/routers/auth.py:379` | Must build real verification lifecycle or explicit internal-only bypass. |
| Login | Password-only Cognito `USER_PASSWORD_AUTH`; no login-code request/confirm flow. | `src/stoa/routers/auth.py:423` | Must decide and implement/login-code policy or remove unsupported expectation. |
| Forgot/reset password | Delegates to Cognito forgot/confirm flows and normalizes common errors. | `src/stoa/routers/auth.py:468` | Keep compatible while adding verification flows. |
| Auth profile output | `_build_user_out` hardcodes `subscriptionStatus="trial"` and `plan="free_trial"`. | `src/stoa/routers/auth.py:132` | Must expose real effective entitlement or avoid misleading plan state. |
| Parent subscription view | Returns current parent tier, plan benefits, pending request, and billing summary. | `src/stoa/services/subscription_service.py:106`, `src/stoa/routers/parents.py:653` | Needs effective entitlement and usage summary, not only billing/request state. |
| Checkout | Creates Stripe checkout/billing row with `checkout_pending`, readiness, provider lookup rows, and billing event. | `src/stoa/services/subscription_service.py:121` | Good foundation; not enough for student access enforcement. |
| Webhook activation | Stripe transition writes billing state and updates parent profile `subscription_tier` when status is active/canceled. | `src/stoa/services/subscription_service.py:2528`, `src/stoa/services/subscription_service.py:2650` | Parent profile updates, but linked student entitlement is not resolved in question quota. |
| Question quota | Reads `student_profile.subscription_tier` and checks a per-student daily counter. | `src/stoa/routers/questions.py:31`, `src/stoa/routers/questions.py:99` | Must use effective entitlement from parent billing/binding/manual override. |
| Daily usage counter | Atomic counter at `PK=USAGE#{student_id}`, `SK=QUESTION#{day}`, with `count`, `expires_at`, `usage_type`. | `src/stoa/db/repositories/question_repo.py:31` | Counter exists, but not durable ledger with event identity, entitlement source, period, product area, or admin query dimensions. |
| Chat/hint limits | Separate counter helper increments usage rows and raises 429 after update. | `src/stoa/services/rate_limit.py:13` | Needs unified usage ledger policy and possibly pre-limit semantics. |
| Parent billing API | Parent can inspect provider billing status. | `src/stoa/routers/parents.py:684` | Does not include full usage/verification/support state. |
| Admin billing API | Admin can list/open billing, readiness, rollout controls, refunds, accounting export, and subscription requests. | `src/stoa/routers/admin.py:1089` | Lacks admin usage ledger and account verification operations. |
| Admin user update | Admin can directly update `subscription_tier` and `is_active`. | `src/stoa/routers/admin.py:1062` | Manual override should become explicit entitlement source with reason/audit semantics. |

## Must-Build Milestone Queue

1. v5.6 Effective entitlement resolver and paid access enforcement:
   - Resolve entitlement from student profile, parent binding, parent billing/profile state, manual override, rollout state, and current billing status.
   - Use it in question quota and later other plan-governed actions.

2. v5.6 Parent-to-student paid access:
   - Active parent subscription must grant intended limits to linked students.
   - Missing/inactive bindings must have deterministic fallback.

3. v5.7 Usage ledger:
   - Add durable event rows for question submission, OCR/AI generation, teacher-help request, chat, and hint usage.
   - Keep current counters compatible while adding ledger writes.

4. v5.8 Email verification lifecycle:
   - Add request/send/verify/resend/expire/fail states.
   - Stop presenting all new accounts as product-verified unless internal bypass is explicitly enabled.

5. v5.8 Login-code policy:
   - Choose one supported product policy:
     - keep password login and remove login-code expectation, or
     - implement a supported Cognito-compatible login code flow.
   - Do not add a fake code flow that cannot produce valid Cognito tokens.

6. v5.9 Customer/admin visibility:
   - Parent sees effective plan, billing state, usage summary, and email verification state.
   - Admin sees entitlement source, usage ledger summary, verification status, billing provider state, and support timestamps.

## Defer

- Native iOS/Android app implementation.
- Live APNS/FCM provider activation.
- Rich curriculum editor frontend implementation.
- Live warehouse/BI deployment.
- External support provider/CRM activation.

## External Prerequisites

- Final live Stripe/TWINT charging still depends on provider credentials, production webhook registration, TWINT approval, finance acceptance, and rollout approval.
- If login-code is implemented through Cognito custom auth, infra/Cognito trigger work may be required.

## Implementation Order

1. v5.6 Effective Entitlements And Paid Access Enforcement.
2. v5.7 Usage Ledger And Quota Reconciliation.
3. v5.8 Email Verification And Login Code Policy.
4. v5.9 Parent Admin Operations Visibility.
