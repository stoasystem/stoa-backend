# Phase 243 Context: Backend Verification Resend Confirm Reliability

## Milestone

v5.14 Verification And Login Reliability

## Requirement

VERIFY-01 Email Verification Resend Confirm Reliability

## Starting Point

Phase 242 confirmed that backend verification is already centered on Cognito sign-up confirmation and local bounded verification fields. Phase 243 tightens edge-case behavior without changing the canonical auth model.

## Files Touched

- `src/stoa/routers/auth.py`
- `tests/test_auth_account_lifecycle.py`

## Reliability Gaps Addressed

- Local already-verified profiles should make confirm idempotent and avoid unnecessary Cognito calls.
- Cognito "already confirmed" responses should repair stale local pending state instead of returning a confusing invalid-code response.
- Wrong-code, expired-code, rate-limited, and disabled-account cases should return support-safe structured errors.
- Login and resend should not turn disabled Cognito accounts into generic provider 500s.
