# Phase 167 Summary

## Completed

- Added runtime WebSocket rollout settings for route configuration, deployment state, live smoke state, route names, and stale cleanup enablement.
- Added `websocket_service.readiness_status()` for operator-facing readiness mode, endpoint host, route/deploy/smoke flags, connection counts, stale cleanup state, and blockers.
- Extended `GET /admin/notifications/delivery-status` with readiness mode, readiness details, aggregate WebSocket delivery attempt counts, and redacted recent delivery attempts.
- Added focused tests for local-only admin status, live-ready admin status without secrets, and all rollout modes.

## Verification

- `./.venv/bin/pytest -q tests/test_notifications.py tests/test_websocket_notifications.py` passed.
- `./.venv/bin/ruff check ...` passed for touched Python files.
- `git diff --check` passed.

## Handoff To Phase 168

Provider-backed email digest and push delivery can build on the expanded delivery status shape by adding provider modes and redacted send evidence alongside the WebSocket readiness block.
