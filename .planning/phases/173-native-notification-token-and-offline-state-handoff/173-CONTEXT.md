# Phase 173: Native Notification Token And Offline State Handoff - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 173 makes native/mobile notification and offline behavior implementable by clients. It refines the v4.9 frontend/native notification handoff and Phase 172 mobile API inventory into token lifecycle, permission state, reconnect, offline/read-through, and deep-link rules. It does not implement platform push SDK code or native offline storage inside this backend repository.

</domain>

<decisions>
## Implementation Decisions

### Source Of Truth
- Durable backend notification state remains authoritative for list, read, archive, preferences, digest, and push delivery evidence.
- WebSocket, push, and digest are delivery accelerators; clients must refetch/reconcile durable state after realtime events, reconnects, and offline recovery.
- Native clients should use backend `eventId`, `eventType`, `targetType`, and `targetId` for routing instead of inventing client-only notification IDs.
- Offline behavior is read-through and reconcile-on-refresh, not automatic client-only notification creation.

### Token Lifecycle
- Native token registration must cover platform, device/install ID, raw token or provider token reference, returned token reference/hash prefix, lifecycle state, `lastSeenAt`, and revocation.
- Raw push tokens must stay in platform secure storage and must not be displayed or logged.
- Token refresh should re-register the token; logout, account switch, permission withdrawal, explicit disablement, and uninstall signal should revoke when possible.
- Preference `push=false`, provider disabled, or permission denied should be visible as explainable states.

### Offline And Reconnect
- Notification center should work with polling/refetch fallback when WebSocket is absent.
- Reconnect should invalidate notification queries and reconcile durable state.
- Offline states for learning history, reports, assignments, billing, and support are read-only/stale unless a future native workspace explicitly implements queued mutations.
- Mutations such as read/archive, assignment transitions, billing checkout/refunds, and support retries should not be silently queued without product approval.

### Existing Versus Follow-Up
- Backend already supports notification list/read/archive, preferences, digest preview/send, push token register/revoke, provider readiness, and redacted delivery attempts.
- Frontend/PWA already has notification center and realtime status foundations but still uses demo fallback in notification APIs.
- Future native apps own permission UX, secure token capture, local cache, deep-link routing, and app-store release evidence.
- Phase 175 should verify release evidence rather than requiring real live push sends.

### the agent's Discretion
All wording and table layout choices are at the agent's discretion. Keep the artifact precise enough for a native/mobile implementer to build from it.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/routers/notifications.py` exposes list, preferences, digest preview/send, push token register/revoke, read/archive, and admin delivery-status routes.
- `src/stoa/services/notification_service.py` defines `PUSH_TOKEN_PLATFORMS`, `PUSH_TOKEN_STATUSES`, `PREFERENCE_CHANNELS`, `register_push_token`, `revoke_push_token`, `attempt_push_delivery`, `push_provider_readiness`, and response shaping.
- `src/stoa/db/repositories/notification_repo.py` persists push tokens under `notification_push_token` entities and can list active tokens.
- `/Users/zhdeng/stoa-frontend/src/hooks/notifications/useRealtimeNotifications.ts` already handles connecting, reconnecting, fallback polling, and offline status.
- `/Users/zhdeng/stoa-frontend/src/components/notifications/NotificationCenter.tsx` already exposes live/fallback/offline labels and read/archive controls.

### Established Patterns
- Backend stores redacted token evidence: token hash, token reference, provider reference, device ID hash, and redacted delivery attempts.
- Notification preferences are category/channel maps with `in_app`, `realtime`, `email_digest`, and `push`.
- Frontend notification cache uses TanStack Query invalidation/reconciliation on realtime events and fallback polling.

### Integration Points
- Future native apps should call `POST /notifications/push-tokens` after permission/token capture and `DELETE /notifications/push-tokens/{tokenReference}` on revocation events.
- Notification tap routing should target authenticated screens based on `targetType` and `targetId`.
- Phase 175 release evidence should record that real provider sends and app-store/native implementation remain gated unless external prerequisites exist.

</code_context>

<specifics>
## Specific Ideas

- Produce `173-NATIVE-NOTIFICATION-OFFLINE-HANDOFF.md`.
- Include permission states, token lifecycle triggers, offline/read-through rules, and deep-link routing.
- Distinguish backend-supported, frontend-supported, native-required, and deferred work.
- Call out notification API demo fallback as a client release blocker for notification-critical flows.

</specifics>

<deferred>
## Deferred Ideas

- Real APNS/FCM SDK implementation.
- App-store release.
- Live provider push sends to real users.
- Offline queued mutations for billing/support/assignment workflows.

</deferred>
