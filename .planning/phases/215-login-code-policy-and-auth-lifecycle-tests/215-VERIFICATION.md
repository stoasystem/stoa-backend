---
status: passed
---

# Phase 215 Verification

## Evidence

- `POST /auth/login-code/request` returns `status=deferred` and `policy=deferred_cognito_custom_auth_required`.
- `POST /auth/login-code/confirm` returns the same deferred policy and never returns an access token.
- Standard verified password login still returns a Cognito access token.
- Unverified password login returns bounded `email_verification_required`.
- Existing forgot-password and reset-password tests still pass without token return.

## Commands

- `.venv/bin/pytest tests/test_auth_account_lifecycle.py -q` — passed, 15 tests.
- `.venv/bin/pytest tests/test_auth_account_lifecycle.py tests/test_questions.py tests/test_subscription_operations.py tests/test_usage_ledger.py -q` — passed, 61 tests.
- `.venv/bin/ruff check src/stoa/services/account_verification_service.py src/stoa/db/repositories/user_repo.py src/stoa/routers/auth.py src/stoa/routers/admin.py tests/test_auth_account_lifecycle.py` — passed.

## Result

Phase 215 passed.
