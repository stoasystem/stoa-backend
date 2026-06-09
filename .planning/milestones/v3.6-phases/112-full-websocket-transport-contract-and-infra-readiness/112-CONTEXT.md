# Phase 112 Context: Full WebSocket Transport Contract And Infra Readiness

**Milestone:** v3.6 Full WebSocket Realtime Notifications
**Requirement:** WS-01
**Status:** Planned

## Why This Phase Exists

`stoa_docs` Phase 2 explicitly calls for WebSocket realtime notifications to replace polling. v3.5 created durable notification events and UI foundations. Phase 112 defines full WebSocket transport before backend/CDK/frontend implementation.

## Product Scope

- Authenticated WebSocket connection lifecycle.
- Role/recipient/channel authorization.
- Event fanout for existing notification events.
- Fallback to notification center/polling when realtime transport is unavailable.
- Infrastructure readiness and CDK impact.

## Completion Criteria

Phase 112 completes when the transport contract, event envelope, authorization model, fallback behavior, CDK readiness, and functional verification checklist are written and internally consistent.
