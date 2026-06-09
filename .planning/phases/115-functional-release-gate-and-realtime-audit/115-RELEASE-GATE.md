# v3.6 Release Gate

**Milestone:** v3.6 Full WebSocket Realtime Notifications
**Status:** Passed for local functional release gate
**Date:** 2026-06-09

## Commit Evidence

Backend/planning commits:

- `387e956` - `docs: plan v3.6 full websocket notifications`
- `f9192d1` - `docs(112): complete websocket transport readiness`
- `10a54f2` - `feat(113-01): add websocket notification delivery backend`
- `e7d0621` - `docs(113): complete websocket backend delivery`
- `5d5811a` - `docs(114): complete realtime notification client`
- `e51f843` - `docs(115): plan v3.6 release gate`

Frontend commit:

- `79c6628` - `feat: add realtime notification client`

## Backend Verification

| Check | Result | Notes |
|-------|--------|-------|
| `PYTHONPATH=src .venv/bin/pytest tests/test_notifications.py tests/test_websocket_notifications.py` | Passed | `10 passed in 0.61s`; notification persistence, WebSocket lifecycle, authz, fanout, stale cleanup, and fallback coverage. |
| `.venv/bin/ruff check src/stoa/services/notification_service.py src/stoa/services/websocket_service.py src/stoa/db/repositories/notification_repo.py src/stoa/db/repositories/websocket_repo.py tests/test_notifications.py tests/test_websocket_notifications.py` | Passed | Focused v3.6 backend lint clean. |
| `PYTHONPATH=src .venv/bin/pytest` | Passed | `302 passed in 5.15s`; full backend regression suite. |

## Frontend Verification

| Check | Result | Notes |
|-------|--------|-------|
| `npm run lint` | Passed | `stoa-frontend` lint clean after realtime client changes. |
| `npm run build` | Passed | Existing Vite large-chunk warning only. |
| `npx playwright test tests/e2e/realtime-notifications.spec.ts -g "polling fallback"` | Passed | Proves notification center fallback state when realtime is not configured. |
| `VITE_ENABLE_REALTIME_NOTIFICATIONS=true VITE_WEBSOCKET_BASE_URL=ws://127.0.0.1:65534/notifications npx playwright test tests/e2e/realtime-notifications.spec.ts -g "teacher session"` | Passed | Browser-side WebSocket fixture proves tutor shell receives teacher-session notification without refresh. |

## Infrastructure And Deploy Evidence

| Check | Result | Notes |
|-------|--------|-------|
| CDK/SAM/serverless file scan | No stack present in `stoa-backend` | `find . -maxdepth 3` found no `cdk.json`, `template.yaml`, `serverless.yml`, or SAM config. |
| Production WebSocket endpoint | Not deployed in this phase | Backend supports `WEBSOCKET_API_ENDPOINT`; frontend supports `VITE_WEBSOCKET_BASE_URL`; live API Gateway WebSocket route wiring remains rollout work. |
| Live smoke | Not run | No production WebSocket endpoint or credentials were available in this local release gate. |

## Release Decision

v3.6 passes the local functional release gate. The backend can persist and fan out notification events to authorized WebSocket connections, and the frontend can consume realtime notification events with heartbeat, reconnect/offline handling, cache sync, and polling fallback.

Production realtime delivery is not claimed until API Gateway WebSocket/CDK route wiring is deployed and live-smoked.

## Residual Gate Notes

- Production API Gateway WebSocket route/integration/CDK deployment evidence remains required for live rollout.
- Browser WebSocket auth uses token query parameters because browsers cannot attach arbitrary authorization headers; production endpoint must be TLS-backed `wss://`.
- Push, native mobile, and email notification delivery remain future scope.
- Stripe/TWINT, full curriculum rollout, richer AI teacher tools/exercise generation, mobile/multilingual polish, and support integrations remain future Phase 2 product expansions.
