# Phase 242 Context: Verification And Login Reality Audit

## Milestone

v5.14 Verification And Login Reliability

## Requirement

AUTHREL-01 Verification And Login Reality Audit

## Current Reality

v5.8 introduced Cognito-backed email verification and explicit login-code deferral. v5.10 added user-facing verification recovery UI and parent/admin account operations visibility. v5.14 starts by auditing those surfaces before making reliability changes.

## Files Reviewed

- Backend auth lifecycle: `src/stoa/routers/auth.py`
- Verification policy helpers: `src/stoa/services/account_verification_service.py`
- Admin verification support endpoint: `src/stoa/routers/admin.py`
- Parent/admin operations support state: `src/stoa/services/account_operations_service.py`
- Backend verification tests: `tests/test_auth_account_lifecycle.py`
- Frontend auth API: `/Users/zhdeng/stoa-frontend/src/services/auth/authApi.ts`
- Frontend verification panel: `/Users/zhdeng/stoa-frontend/src/components/auth/EmailVerificationPanel.tsx`
- Frontend auth E2E: `/Users/zhdeng/stoa-frontend/tests/e2e/auth.spec.ts`

## Constraints

- Live Cognito/email smoke remains externally gated by deployed Cognito clients, email delivery, and approved environment credentials.
- Frontend repository is outside the backend workspace write root; frontend implementation requires explicit patch/apply handling when Phase 245 begins.
- Support surfaces must not expose raw verification codes, Cognito secrets, access tokens, or refresh tokens.
