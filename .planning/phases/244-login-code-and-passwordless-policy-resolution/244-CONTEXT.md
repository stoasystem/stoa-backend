# Phase 244 Context: Login Code And Passwordless Policy Resolution

## Milestone

v5.14 Verification And Login Reliability

## Requirement

LOGIN-01 Canonical Login Code And Passwordless Policy

## Current Reality

The product login form is email/password only. Email verification uses a one-time confirmation code, but that is not a passwordless login code and does not mint tokens. Backend `/auth/login-code/*` endpoints exist only as explicit deferred policy responses.

## Evidence Reviewed

- Backend login-code policy: `src/stoa/routers/auth.py`
- Backend policy constant: `src/stoa/services/account_verification_service.py`
- Backend contract tests: `tests/test_auth_account_lifecycle.py`
- Frontend login form: `/Users/zhdeng/stoa-frontend/src/components/auth/LoginForm.tsx`
- Frontend search: no `login-code`, `passwordless`, magic-link, or login-code API usage under `/Users/zhdeng/stoa-frontend/src` or `/Users/zhdeng/stoa-frontend/tests`.

## Decision

Email/password plus verified email remains the canonical product login path. Passwordless/login-code remains deferred until real Cognito custom auth triggers, secure challenge handling, frontend UX, and release gates are implemented end to end.
