# Phase 261 Verification

## Commands

```bash
.venv/bin/python -m pytest tests/test_external_activation_smoke.py tests/test_subscription_operations.py tests/test_auth_account_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_report_flow.py tests/test_release_evidence.py tests/test_core_smoke.py -q
```

Result: `106 passed in 5.06s`

```bash
.venv/bin/python -m ruff check src/stoa/services/external_activation_service.py src/stoa/routers/admin.py tests/test_external_activation_smoke.py tests/test_subscription_operations.py tests/test_auth_account_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_report_flow.py tests/test_release_evidence.py tests/test_core_smoke.py
```

Result: `All checks passed!`

## Gate Evidence

- All v5.17 external activation smoke endpoints are admin-only.
- Blocked/read-only states are deterministic and support-safe.
- Provider credentials and raw payloads are redacted or omitted.
- Production mutation remains disabled by default.
- Release evidence validator and no-mutation helper are part of the production readiness contract.
