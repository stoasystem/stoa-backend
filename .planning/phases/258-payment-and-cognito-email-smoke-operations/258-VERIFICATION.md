# Phase 258 Verification

## Commands

```bash
.venv/bin/python -m pytest tests/test_external_activation_smoke.py tests/test_subscription_operations.py tests/test_auth_account_lifecycle.py -q
```

Result: `61 passed in 4.62s`

```bash
.venv/bin/python -m ruff check src/stoa/services/external_activation_service.py src/stoa/routers/admin.py tests/test_external_activation_smoke.py
```

Result: `All checks passed!`

## Evidence

- Blocked payment and missing Cognito config return `overallState=blocked`.
- Live-ready payment with configured Cognito local policy still returns read-only overall state because live email delivery evidence is absent.
- Payment live mutation is represented separately from overall provider release readiness.
- The new smoke endpoint is admin-only.
- Responses exclude secrets, raw provider payloads, and login codes.
