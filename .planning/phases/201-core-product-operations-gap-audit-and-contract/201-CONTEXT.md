# Phase 201 Context: Core Product Operations Gap Audit And Contract

## Milestone

v5.6 Effective Entitlements And Paid Access Enforcement

## Why This Phase Exists

The previous native app and broad core-operations plans assumed the core product backend was ready enough to wrap in a mobile client. User testing identified that this is not yet true.

Known incomplete or suspect areas:

- Paid functionality and entitlement activation.
- Backend usage records for user consumption.
- Login verification code behavior.
- Email verification behavior.
- Billing/usage/verification details needed for support and admin operations.

These are more important than native app work because they affect every real user flow.

On 2026-07-03 this work was promoted from a single broad v5.6 phase list into separate feature milestones. Phase 201 now acts as the audit and split decision that starts v5.6 and defines v5.7 through v5.9.

## Function Purpose

Define the missing operational product details so STOA can reliably answer:

- Is this user paid, trialing, pending, expired, canceled, or manually overridden?
- What usage did this user/student consume, and against which entitlement?
- Has this account verified email, and how can verification be resent or completed?
- What is the supported login verification-code policy?
- What can a parent/customer and admin see without inspecting raw database records?

## Implementation Strategy

Phase 201 is a contract/audit phase:

- Read current auth, subscription, billing, quota, and admin implementation.
- Define must-build product gaps.
- Define paid entitlement, usage ledger, email verification, login-code policy, and operations visibility models.
- Promote each major final-polish capability into its own milestone when the scope is product-complete rather than phase-sized.
- Define v5.6 internal phases 202 through 206 for effective entitlement delivery.
- Define v5.7, v5.8, and v5.9 as follow-up feature milestones for usage ledger, email/login verification, and parent/admin operations visibility.

## Code Context

Likely relevant backend areas:

- `src/stoa/routers/auth.py`
- `src/stoa/routers/billing.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/admin.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/repositories/user_repository.py`
- `src/stoa/repositories/question_repository.py`
- `tests/test_auth_account_lifecycle.py`
- `tests/test_subscription_operations.py`
- `tests/test_questions.py`

## Planning Boundary

Phase 201 does not implement native apps. Native iOS/Android planning is deferred until the v5.6-v5.9 final-polish product operations are reliable.
