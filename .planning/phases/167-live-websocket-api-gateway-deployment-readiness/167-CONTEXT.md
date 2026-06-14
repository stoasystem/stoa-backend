# Phase 167 Context: Live WebSocket API Gateway Deployment Readiness

## Starting Point

Phase 166 defined the rollout contract for v4.9 production notifications. The backend already has local WebSocket connection management, durable notification event storage, realtime fanout, stale cleanup, and an admin notification delivery status endpoint.

Current code surfaces:

- `src/stoa/services/websocket_service.py` registers, refreshes, subscribes, disconnects, cleans stale connections, and fans notification events out to API Gateway Management API when an endpoint is configured.
- `src/stoa/services/notification_service.py` persists notification events before realtime fanout and already keeps durable fallback behavior if fanout fails.
- `src/stoa/routers/notifications.py` exposes `GET /admin/notifications/delivery-status`.
- `src/stoa/config.py` has `websocket_api_endpoint` and `websocket_connection_ttl_seconds`, but no deployment-readiness state.

## Requirement

`PRODNOTIF-02` requires live WebSocket/API Gateway readiness beyond local functional behavior:

- CDK/infrastructure readiness or documented handoff for routes, handlers, runtime config, and environment variables.
- Delivery status distinguishes `local_only`, `configured`, `deployed`, `provider_blocked`, and `live_ready`.
- Durable fallback remains intact when live fanout fails.
- Admin/operator status exposes endpoint/configuration blockers, recent attempts, stale cleanup state, and no secrets.
- Focused checks cover configured/unconfigured state, fanout fallback, stale cleanup, and admin status shape.

## Decisions

- Use runtime readiness flags instead of pretending CDK deployment has happened from code alone.
- Keep the existing durable-first notification flow unchanged.
- Add readiness details to the existing admin delivery-status endpoint rather than creating a second operator endpoint.
- Redact connection IDs from admin recent-attempt summaries and expose counts/statuses instead.
- Report endpoint host only, never query strings or credentials.

## External Handoff

The deploy owner must set these environment-backed settings when the live API Gateway WebSocket stack is wired:

- `WEBSOCKET_API_ENDPOINT`: API Gateway Management API endpoint.
- `WEBSOCKET_LIVE_ROUTES_CONFIGURED`: true once `$connect`, `$disconnect`, and message/subscribe routes are integrated.
- `WEBSOCKET_LIVE_DEPLOYED`: true once the live stack has been deployed to the target environment.
- `WEBSOCKET_LIVE_SMOKE_PASSED`: true only after an approved live smoke succeeds.
- `WEBSOCKET_STALE_CLEANUP_ENABLED`: true when scheduled cleanup is active.
