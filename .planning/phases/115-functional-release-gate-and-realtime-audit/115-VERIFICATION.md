---
status: passed
verified_at: 2026-06-09T13:01:25+02:00
---

# Phase 115 Verification

## Backend Commands

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_notifications.py tests/test_websocket_notifications.py
.venv/bin/ruff check src/stoa/services/notification_service.py src/stoa/services/websocket_service.py src/stoa/db/repositories/notification_repo.py src/stoa/db/repositories/websocket_repo.py tests/test_notifications.py tests/test_websocket_notifications.py
PYTHONPATH=src .venv/bin/pytest
```

## Frontend Commands

```bash
npm run lint
npm run build
npx playwright test tests/e2e/realtime-notifications.spec.ts -g "polling fallback"
VITE_ENABLE_REALTIME_NOTIFICATIONS=true VITE_WEBSOCKET_BASE_URL=ws://127.0.0.1:65534/notifications npx playwright test tests/e2e/realtime-notifications.spec.ts -g "teacher session"
```

## Results

- Backend focused pytest: `10 passed in 0.61s`.
- Backend focused Ruff: all checks passed.
- Backend full pytest: `302 passed in 5.15s`.
- Frontend lint: passed.
- Frontend build: passed with existing Vite large-chunk warning.
- Frontend fallback Playwright: 1 passed.
- Frontend realtime fixture Playwright: 1 passed.

## Infrastructure Verification

No CDK/SAM/serverless stack files were found in `stoa-backend` for WebSocket API Gateway provisioning. Production WebSocket endpoint deployment and live smoke remain rollout prerequisites.
