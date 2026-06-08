# Full WebSocket Realtime Notification Contract: v3.6

## Connection Lifecycle

- `connect`: client opens WebSocket session.
- `authenticate`: client proves identity with existing auth token or approved equivalent handshake.
- `subscribe`: client subscribes to allowed role/target channels.
- `heartbeat`: client/server keep connection fresh.
- `event`: server sends notification envelope.
- `ack`: client can acknowledge event receipt where needed.
- `disconnect`: server removes connection record.
- `stale_cleanup`: backend removes expired connection records.

## Event Envelope

Minimum fields:

- `event_id`
- `event_type`
- `recipient_id`
- `recipient_role`
- `target_type`
- `target_id`
- `title`
- `summary`
- `created_at`
- `delivery_id`
- `delivery_attempt`
- `metadata`

## Realtime Event Types

- `teacher_requested`
- `teacher_takeover`
- `teacher_reply`
- `moderation_case_update`
- `subscription_request_update`
- `learning_profile_update`
- `system_notice`

## Authorization Model

- Recipients can receive only events addressed to their user id or explicitly allowed role scope.
- Student/parent child-linked events must preserve existing parent/student ownership rules.
- Tutor events must be limited to visible queue/session/question contexts.
- Admin events must require admin role.

## Infrastructure Readiness

Likely CDK impact:

- API Gateway WebSocket API or equivalent managed WebSocket entrypoint.
- Lambda route handlers for connect, disconnect, default/message routes.
- DynamoDB connection records in existing table if access pattern is sufficient.
- IAM permission for backend to post to WebSocket connection management endpoint.
- Environment variables for WebSocket endpoint and feature flags.

Phase 113 should implement only after this readiness decision is confirmed against `/Users/zhdeng/stoa-infra`.

## Fallback Behavior

- Existing notification center remains canonical history.
- If WebSocket is unavailable, frontend falls back to notification list refresh/polling.
- Reconnect should not duplicate visible notifications because event ids are stable.
