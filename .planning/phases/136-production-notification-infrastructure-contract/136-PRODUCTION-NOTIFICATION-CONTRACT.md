# Phase 136 Production Notification Delivery Contract

**Status:** Drafted for v4.2 planning
**Updated:** 2026-06-11
**Requirement:** NOTIFYDEL-01

## Production Delivery Goal

STOA should deliver user-facing notifications through a production-capable model:

- Store notification events durably for in-product history.
- Deliver eligible events over WebSocket when the recipient has an active authorized connection.
- Preserve polling fallback for offline clients and clients without WebSocket support.
- Prepare email digest and push/native preference metadata without requiring production provider rollout during internal development.
- Expose enough delivery state for internal operators to understand whether realtime delivery was attempted, skipped, failed, or deferred.

## Production WebSocket Contract

Expected endpoint shape:

- Production WebSocket base URL is configured outside client code through environment configuration.
- Connection auth must resolve the same user and role model used by existing REST auth.
- Connection identity should record user id, role, optional session/client metadata, and last-seen timestamp.
- Subscription scope must remain role/user bounded; broad cross-user channels are not part of v4.2.
- Disconnect and stale cleanup behavior must remove or ignore inactive connection records.

Expected route/integration surface:

- `$connect`: authenticate and persist connection metadata.
- `$disconnect`: mark or remove connection metadata.
- `subscribe` or equivalent route: record client subscription intent where existing local behavior requires it.
- `heartbeat` or equivalent route: update last-seen metadata.
- Backend fanout path: attempt delivery through the configured WebSocket management endpoint when a notification event is created.

Required configuration:

- WebSocket API endpoint or management endpoint.
- Connection table/repository configuration.
- Feature flag or environment switch for production realtime delivery.
- Fallback behavior when endpoint/configuration is absent.

## Channel Mapping

| Event Source | In-App History | Realtime WebSocket | Email Digest Ready | Push Ready |
|--------------|----------------|--------------------|--------------------|------------|
| Student question answered | Yes | Yes | Yes | Preference flag only |
| Teacher/tutor takeover update | Yes | Yes | Yes | Preference flag only |
| Assignment/recommendation update | Yes | Yes | Yes | Preference flag only |
| Parent report/report operation update | Yes | Yes | Yes | Preference flag only |
| Admin operational notification | Yes | Yes for admins | Optional | No by default |

## Preference Categories

Phase 137 should support durable preferences with conservative defaults:

- `learning_updates`
- `teacher_responses`
- `assignments`
- `weekly_reports`
- `admin_operations`

Initial channel flags:

- `in_app`: default enabled.
- `realtime`: default enabled when production realtime is configured.
- `email_digest`: default disabled or digest-only opt-in until email template/provider policy is finalized.
- `push`: stored as a preference flag, delivery deferred until native provider rollout.

## Delivery State Fields

Future implementation should keep delivery metadata bounded and operator-readable:

- `notificationId`
- `recipientUserId`
- `eventType`
- `category`
- `channel`
- `decision`: `attempted`, `skipped_preference`, `skipped_unconfigured`, `deferred_digest`, `failed`, `delivered`
- `attemptedAt`
- `deliveredAt`
- `failureReason`
- `requestId` or `correlationId` when available
- `connectionCount` or equivalent aggregate count, not raw connection secrets

## Ownership Boundaries

Backend repository:

- Preference APIs.
- Delivery decision helpers.
- Digest selection/preview contracts.
- Delivery metadata/status APIs.
- Focused tests around preference and delivery logic.

CDK/infrastructure surface:

- Production API Gateway WebSocket API and routes.
- WebSocket management endpoint configuration.
- Lambda permissions for WebSocket management callbacks.
- Deployment evidence and live endpoint smoke when promoted.

Frontend/native surfaces:

- Visual notification settings UI.
- Mobile viewport polish.
- Native push token registration and provider integration.
- Translated/localized notification preference copy.

## Safety Boundary

v4.2 may build feature functionality with local/test-mode verification. It should not send broad production customer email/push/realtime traffic without explicit approval and approved provider configuration.
