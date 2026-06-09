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

## Readiness Decision

- Use API Gateway WebSocket as the default implementation path for v3.6 unless CDK inspection in Phase 113 proves an existing managed WebSocket entrypoint is already available.
- Keep notification persistence in the existing notification center as the source of truth; WebSocket delivery is a realtime transport overlay, not a replacement for durable notification records.
- Store connection records with enough data to authorize fanout without trusting client-supplied channel names after subscription.
- Treat missing or stale WebSocket delivery as non-destructive because users can still recover notifications through the existing list/read/archive APIs.

## Fallback Behavior

- Existing notification center remains canonical history.
- If WebSocket is unavailable, frontend falls back to notification list refresh/polling.
- Reconnect should not duplicate visible notifications because event ids are stable.

## Functional Verification Checklist

- Backend tests prove connection lifecycle, authorization, fanout, disconnect cleanup, stale cleanup, and persistent fallback behavior.
- Frontend tests prove authenticated connect, reconnect, heartbeat/offline state, notification count/list refresh, and polling fallback.
- CDK/diff evidence proves any WebSocket infrastructure is intentional, permission-scoped, and deployable without weakening existing HTTP API behavior.
- Browser smoke uses local or safe fixtures and does not require production notification mutation unless explicitly approved in the release gate.
