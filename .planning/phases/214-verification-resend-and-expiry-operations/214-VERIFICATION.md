---
status: passed
---

# Phase 214 Verification

## Evidence

- `POST /auth/email-verification/resend` delegates to Cognito `resend_confirmation_code`.
- Resend cooldown returns `already_requested` without a provider call.
- Provider resend metadata is returned only as bounded `CodeDeliveryDetails`.
- `POST /auth/email-verification/confirm` delegates to Cognito `confirm_sign_up` and updates local state to `verified`.
- Expired confirmation codes update local state to `expired_verification`.
- `GET /admin/account-verification/{user_id}` returns bounded support state.

## Commands

- `.venv/bin/pytest tests/test_auth_account_lifecycle.py -q` — passed, 15 tests.
- `.venv/bin/pytest tests/test_auth_account_lifecycle.py tests/test_questions.py tests/test_subscription_operations.py tests/test_usage_ledger.py -q` — passed, 61 tests.
- `.venv/bin/ruff check src/stoa/services/account_verification_service.py src/stoa/db/repositories/user_repo.py src/stoa/routers/auth.py src/stoa/routers/admin.py tests/test_auth_account_lifecycle.py` — passed.

## Result

Phase 214 passed.
