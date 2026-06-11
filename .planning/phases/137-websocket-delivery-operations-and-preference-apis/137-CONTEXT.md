# Phase 137 Context: WebSocket Delivery Operations And Preference APIs

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** Autonomous single-pass discuss

## Phase Boundary

Phase 137 implements durable notification preferences and delivery-decision/status behavior for internal production-oriented rollout. It follows the Phase 136 contract and does not perform production notification sends.

## Existing Code Context

- `notification_service.create_event` stores durable events and fans out through `websocket_service`.
- `websocket_service.fanout_notification_event` already records bounded delivery attempt metadata in notification event metadata.
- `notifications.router` exposes user list/read/archive routes.
- `notifications.admin_router` exposes bounded admin list routes.
- Tests use monkeypatched in-memory notification and WebSocket repositories.

## Decisions

- Store preferences in a new `notification_preference` item family keyed by user id.
- Use the Phase 136 category/channel model: `learning_updates`, `teacher_responses`, `assignments`, `weekly_reports`, `admin_operations` and `in_app`, `realtime`, `email_digest`, `push`.
- Preserve default in-product notifications and realtime attempts for existing users.
- Record delivery decisions as metadata on notification events.
- Expose admin delivery status as aggregate counts only, not raw connection secrets.
