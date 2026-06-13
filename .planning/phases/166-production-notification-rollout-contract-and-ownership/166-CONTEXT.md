# Phase 166 Context: Production Notification Rollout Contract And Ownership

## Why This Phase Exists

STOA already has local functional realtime notifications and backend production-readiness pieces, but the remaining `stoa_docs` notification gap is production rollout: live WebSocket/API Gateway deployment, provider-backed email/push delivery, frontend/native notification visuals, native push token registration, and live smoke evidence.

v4.9 starts with a contract phase so backend, frontend, native, infrastructure, and provider work can proceed without mixing ownership or treating local-only readiness as production delivery.

## Current Foundation

- v3.6 completed local WebSocket realtime notifications with connection records, subscriptions, fanout, delivery attempt metadata, frontend WebSocket client behavior, reconnect/offline states, notification center sync, and polling fallback.
- v4.2 completed backend production notification readiness with production WebSocket contracts, durable preferences, preference-aware delivery decisions, admin delivery status, digest preview readiness, and push-ready preference metadata.
- `src/stoa/services/notification_service.py`, `src/stoa/services/websocket_service.py`, `src/stoa/routers/notifications.py`, `src/stoa/db/repositories/notification_repo.py`, and `src/stoa/db/repositories/websocket_repo.py` contain the current backend notification surface.
- `tests/test_notifications.py` and `tests/test_websocket_notifications.py` cover existing backend notification behavior.
- `stoa_docs` remaining-feature queue now recommends production notification and native delivery rollout.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 167 through Phase 170 implement and what remains externally blocked. It should not perform real provider-backed sends to users.

## Key Files To Inspect

- `src/stoa/services/notification_service.py`
- `src/stoa/services/websocket_service.py`
- `src/stoa/routers/notifications.py`
- `src/stoa/db/repositories/notification_repo.py`
- `src/stoa/db/repositories/websocket_repo.py`
- `tests/test_notifications.py`
- `tests/test_websocket_notifications.py`
- `.planning/phases/112-websocket-lifecycle-auth-and-fallback-contract/`
- `.planning/phases/113-backend-websocket-connection-and-fanout/`
- `.planning/phases/114-frontend-realtime-notification-client/`
- `.planning/phases/115-v3-6-realtime-notification-release-gate/`
- `.planning/phases/136-production-notification-infrastructure-contract/`
- `.planning/phases/137-websocket-delivery-operations-and-preference-apis/`
- `.planning/phases/138-email-digest-and-push-preference-readiness/`
- `.planning/phases/139-v4.2-functional-release-gate-and-notification-delivery-audit/`

## Constraints

- Live WebSocket and provider-backed push/email delivery may require infrastructure and credentials not present in local development.
- Durable notification list/read/archive behavior must remain the fallback when realtime/provider delivery is unavailable.
- Delivery preferences and event category/channel rules must stay explicit.
- Frontend/native token registration and UX work may require `/Users/zhdeng/stoa-frontend` or future native app workspaces.
- Verification should focus on functional rollout behavior and non-mutating live smoke boundaries.
