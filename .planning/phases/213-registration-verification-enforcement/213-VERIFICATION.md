---
status: passed
---

# Phase 213 Verification

## Evidence

- `POST /auth/register` now uses Cognito `sign_up`, stores `pending_verification`, and returns no access token.
- `POST /auth/login` refuses token return while backend profile state requires email verification.
- `AuthResponse` and `UserOut` expose `emailVerificationStatus`, `emailVerificationRequired`, and `accountActivationStatus`.
- Parent/student matching registration creates `active_pending_verification` bindings for unverified parties.
- Role client selection and tutor/teacher alias behavior remain in the existing helper path.

## Commands

- `.venv/bin/pytest tests/test_auth_account_lifecycle.py -q` — passed, 15 tests.
- `.venv/bin/pytest tests/test_auth_account_lifecycle.py tests/test_questions.py tests/test_subscription_operations.py tests/test_usage_ledger.py -q` — passed, 61 tests.
- `.venv/bin/ruff check src/stoa/services/account_verification_service.py src/stoa/db/repositories/user_repo.py src/stoa/routers/auth.py src/stoa/routers/admin.py tests/test_auth_account_lifecycle.py` — passed.

## Result

Phase 213 passed.
