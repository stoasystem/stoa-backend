# Requirements: v3.6 Full WebSocket Realtime Notifications

**Milestone:** v3.6
**Status:** Active
**Created:** 2026-06-08

## Goal

Turn the v3.5 in-product notification foundation into full WebSocket realtime notifications for core learning and operations workflows. This milestone focuses on functional realtime delivery: connection lifecycle, authenticated subscriptions, backend event fanout, frontend realtime client behavior, and graceful fallback to the existing notification center.

## Requirements

### WS-01 Full WebSocket Transport Contract And Infra Readiness

Implementers have a precise WebSocket transport contract, connection model, authorization model, and infrastructure readiness decision before backend changes.

Acceptance criteria:

- Contract defines WebSocket connection lifecycle: connect, authenticate, subscribe, heartbeat, reconnect, disconnect, and stale connection cleanup.
- Contract defines event envelope for existing notification events and per-role channel/target authorization.
- Contract defines supported realtime event categories: teacher request/takeover/reply, moderation updates, subscription updates, learning profile updates, and system notices.
- Contract defines fallback behavior to polling/notification center when WebSocket is unavailable.
- Infrastructure readiness compares API Gateway WebSocket, existing Lambda/API shape, DynamoDB connection records, and CDK changes required for v3.6.

### WS-02 Backend WebSocket Connection And Event Delivery

Backend supports authenticated WebSocket connections and realtime delivery from existing notification events.

Acceptance criteria:

- Backend stores active connection records with user id, role, subscribed channels, heartbeat/update timestamps, and expiry.
- Backend authenticates connection/subscription requests using the existing Cognito/JWT model or an approved equivalent path.
- Backend publishes selected notification events to active authorized WebSocket connections and records delivery attempts/results.
- Backend supports disconnect cleanup and stale connection cleanup.
- Focused tests cover connection lifecycle, authorization, event fanout, stale cleanup, and fallback-safe event persistence.

### UI-21 Realtime Notification Client And UX

Frontend consumes WebSocket notifications while preserving existing notification center fallback.

Acceptance criteria:

- Frontend establishes an authenticated WebSocket session after login where enabled.
- Frontend handles reconnect, heartbeat, offline/unavailable state, and fallback to existing notification list polling.
- Student/parent/tutor/admin shells show realtime notification count/list updates for supported events.
- Tutor workflows receive teacher-session events without page refresh where supported.
- Targeted browser verification confirms realtime/fallback UX for local or safe test fixtures.

### VERIFY-19 v3.6 Functional Release Gate And Realtime Audit

v3.6 closes with functional evidence and updated Phase 2 gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to WebSocket delivery pass.
- CDK/diff/deploy evidence is recorded if infrastructure changes are required.
- Gap audit marks full WebSocket realtime notifications as active/closed and records residual push/email/native notification scope.
- Final audit lists remaining Phase 2 product expansions: Stripe/TWINT, full curriculum rollout, richer AI teacher tools/exercise generation, mobile/multilingual polish, and support integrations.

## Future Requirements

- Push notifications and native mobile notification delivery.
- Email notification digests.
- Stripe/TWINT payment-provider integration.
- Automatic exercise generation and richer AI teacher tools.
- Full multi-subject curriculum content and exercises.
- Mobile responsive polish and full multilingual rollout.

## Out of Scope

- Native mobile push notifications.
- Email notification digests.
- Production charging/payment-provider work.
- Automatic exercise generation.
- Broad security/compliance program beyond required WebSocket auth/authorization and functional correctness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| WS-01 | Phase 112 | Complete |
| WS-02 | Phase 113 | Complete |
| UI-21 | Phase 114 | Complete |
| VERIFY-19 | Phase 115 | Planned |
