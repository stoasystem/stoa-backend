# Phase 245 Verification

## Backend Commands

```bash
.venv/bin/pytest tests/test_auth_account_lifecycle.py tests/test_subscription_operations.py -k "account_operations or account_verification or email_verification or login_code or disabled or resend"
.venv/bin/ruff check src/stoa/services/account_verification_service.py src/stoa/routers/admin.py tests/test_auth_account_lifecycle.py tests/test_subscription_operations.py
```

## Backend Results

- `16 passed, 40 deselected in 0.93s`
- `All checks passed!`

## Frontend Commands

```bash
npm run build
```

## Frontend Results

- TypeScript and Vite production build passed.
- Vite emitted the existing large chunk warning.

## External Verification

Live Cognito/email smoke was not run in Phase 245. It remains a Phase 246 release-gate item and is externally blocked without approved credentials, configured delivery, and inbox access.
