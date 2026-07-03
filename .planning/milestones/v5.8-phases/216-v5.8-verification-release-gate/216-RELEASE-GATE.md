# v5.8 Release Gate: Email Verification And Login Code Policy

**Date:** 2026-07-03
**Release state:** `policy-deferred`

## Completed Scope

- Email verification state contract and public response fields.
- Cognito `sign_up` registration with pending verification state.
- Cognito `confirm_sign_up` verification confirmation.
- Cognito `resend_confirmation_code` resend operation with cooldown/idempotency behavior.
- Expired verification state handling.
- Bounded admin verification support visibility.
- Explicit deferred login-code/passwordless policy with no token minting.
- Focused auth lifecycle tests and adjacent entitlement/usage regression tests.

## Evidence

| Check | Result |
|-------|--------|
| `tests/test_auth_account_lifecycle.py` | Passed, 15 tests |
| Auth + entitlement + usage focused suite | Passed, 61 tests |
| Targeted Ruff | Passed |
| Phase verification files | Passed for phases 212-216 |

## Residual Scope

- Production deploy/live Cognito smoke is not run in this local release gate.
- Login-code/passwordless remains deferred until Cognito custom auth triggers and replay/rate-limit storage are designed.
- Full parent/admin operations visibility remains v5.9 scope.
- Native/mobile verification UX remains future client scope.

## Handoff To v5.9

v5.9 can use:

- `email_verification_status`
- `email_verification_required`
- `account_activation_status`
- resend timestamps/counts
- `GET /admin/account-verification/{user_id}`

to build broader parent/admin operations visibility.
