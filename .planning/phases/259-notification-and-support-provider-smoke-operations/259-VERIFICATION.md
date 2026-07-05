# Phase 259 Verification

## Commands

```bash
.venv/bin/python -m pytest tests/test_external_activation_smoke.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_report_flow.py -q
```

Result: `35 passed in 1.05s`

```bash
.venv/bin/python -m ruff check src/stoa/services/external_activation_service.py src/stoa/routers/admin.py tests/test_external_activation_smoke.py
```

Result: `All checks passed!`

## Evidence

- Missing notification/support provider prerequisites return `overallState=blocked`.
- Configured providers with send flags disabled return `read_only_verifiable`.
- Fully enabled provider flags return `overallState=live_ready` and `safeToMutate=true`.
- Endpoint is admin-only.
- Responses do not include provider API keys, raw push tokens, raw provider payloads, customer messages, or provider ticket payloads.
