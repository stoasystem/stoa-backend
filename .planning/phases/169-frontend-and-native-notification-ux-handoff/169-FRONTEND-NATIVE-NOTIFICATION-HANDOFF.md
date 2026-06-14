# Frontend And Native Notification UX Handoff

## Scope

This handoff defines how `/Users/zhdeng/stoa-frontend` and future native apps should integrate live notifications, durable notification state, email digest controls, and push token registration from `stoa-backend`.

Durable backend notification state is authoritative. WebSocket and push delivery are delivery accelerators, not the source of truth.

## API Contract

### Notification Center

`GET /notifications?status={created|read|archived}&limit=50`

Use this as the notification center source of truth. Default list excludes archived notifications. The UI should show unread/created first based on `createdAt` ordering from the backend.

Expected item fields:

- `eventId`
- `recipientId`
- `recipientRole`
- `eventType`
- `targetType`
- `targetId`
- `title`
- `summary`
- `status`
- `createdAt`
- `readAt`
- `archivedAt`
- `metadata`
- `deliveryCategory`
- `deliveryChannels`

Mutations:

- `POST /notifications/{eventId}/read`
- `POST /notifications/{eventId}/archive`

The frontend should optimistically update only after a 200 response or rollback on failure. Unauthorized/404 responses should remove stale local optimistic state after a refetch.

### Preferences

`GET /notifications/preferences`

`PATCH /notifications/preferences`

Request body:

```json
{
  "preferences": {
    "teacher_responses": {
      "in_app": true,
      "realtime": true,
      "email_digest": false,
      "push": false
    }
  }
}
```

Supported categories come from `supportedCategories`; supported channels come from `supportedChannels`. The UI must render only backend-returned categories/channels and should preserve unspecified channel values when patching one toggle.

Preference UX:

- `in_app`: durable notification center storage. Disabling can archive new events automatically.
- `realtime`: WebSocket delivery attempt. Disabling should not hide durable notification history.
- `email_digest`: digest selection and manual/provider sends.
- `push`: native/provider push delivery. Requires a registered active push token.

### Email Digest

`GET /notifications/digest-preview?category=&since=&until=&limit=25`

Preview is read-only. It returns currently visible unread digest-eligible notifications based on durable preferences.

`POST /notifications/digest-send`

Request body:

```json
{
  "category": "teacher_responses",
  "since": "2026-06-14T00:00:00+00:00",
  "until": "2026-06-14T23:59:59+00:00",
  "limit": 25
}
```

Response statuses to surface:

- `sent`: provider accepted the fixture/live send.
- `refused_no_digest_items`: nothing eligible under current filters/preferences.
- `refused_missing_recipient_email`: authenticated user context has no email.
- `refused_provider_not_ready`: provider config/approval is missing.
- `refused_provider_send_disabled`: provider exists but send gate is disabled.
- `failed`: provider path failed; show retry affordance only if product policy allows.

### Push Token Registration

`POST /notifications/push-tokens`

Request body:

```json
{
  "platform": "ios",
  "token": "raw-native-token-if-available",
  "providerTokenReference": "provider-token-reference-if-issued",
  "deviceId": "stable-installation-or-device-id"
}
```

Response fields:

- `tokenReference`
- `platform`
- `status`
- `tokenHashPrefix`
- `hasProviderReference`
- `createdAt`
- `lastSeenAt`
- `revokedAt`

Native clients should prefer provider token references when the push provider issues one. Raw native tokens may be submitted for hashing, but frontend/native code must not persist them outside platform secure storage.

`DELETE /notifications/push-tokens/{tokenReference}`

Call on logout, permission withdrawal, account switch, uninstall signal when available, or explicit notification disablement.

## WebSocket Contract

Endpoint discovery is deployment-owned:

- Web frontend should read the live WebSocket URL from deployment config such as `VITE_STOA_WEBSOCKET_URL`.
- Admin/operator verification should compare that configured URL against `GET /admin/notifications/delivery-status`.
- Until a public endpoint-discovery route exists, user-facing clients must not infer WebSocket endpoint URLs from admin APIs.

Connection lifecycle:

- Connect after authentication is available.
- Register/refresh using the deployed API Gateway WebSocket route contract.
- Subscribe only to authorized channels:
  - `user:{sub}`
  - `role:{role}`
  - role aliases for teacher/tutor as supported by backend WebSocket authorization.
- Reconnect with exponential backoff.
- On reconnect, immediately refetch `GET /notifications` and preferences.
- Treat each WebSocket event as a refresh trigger and reconcile with durable list state.

Offline/fallback:

- If WebSocket is unavailable, continue polling/refetching durable notifications.
- Show a quiet degraded-state indicator only where useful; do not block notification center access.
- Do not create client-only fake notifications for user-critical state.

## Role UX Expectations

Student:

- Notification center highlights teacher replies, teacher takeover, assignment updates, learning profile updates, and weekly report availability.
- Realtime events should refresh active question/report views when target IDs match the current page.
- Push permission should be requested only after the user reaches a relevant notification setting or onboarding step.

Parent:

- Notification center highlights subscription updates, weekly reports, learning profile changes, and child-related admin operations when exposed.
- Email digest controls should make clear that digest sends are preference-gated and may be provider-disabled.
- Push settings should show token registration state per device when native apps exist.

Tutor/Teacher:

- Notification center highlights teacher requests, student replies, assignment updates, and operational queue events.
- Live events should refresh queue/list views without losing current filters.
- Offline fallback must keep manual refresh available.

Admin:

- Admin notifications list remains an operations feed.
- Admin delivery status should show WebSocket mode, email provider readiness, push provider readiness, recent fanout evidence, and blockers.
- Admin UI must not expose raw endpoint query strings, provider API keys, raw push tokens, or raw provider failure text.

## Frontend Follow-Up: `/Users/zhdeng/stoa-frontend`

Add or update:

- Notification API client methods for list, read, archive, preferences, digest preview, digest send, push token register, and push token revoke.
- WebSocket client configuration from deployment env.
- Notification center reconciliation that treats realtime events as refresh triggers.
- Preference UI toggles for `in_app`, `realtime`, `email_digest`, and `push`.
- Digest preview/send UI with provider-disabled and no-items states.
- Admin delivery status panel for WebSocket/email/push readiness and blockers.
- No hidden demo fallback for notification list, preference state, digest state, or provider readiness.

## Native App Follow-Up

Future native apps must implement:

- Platform permission UX for iOS/Android/web push.
- Secure token capture from platform push APIs.
- Token registration with `platform`, raw token or provider token reference, and device ID.
- Token refresh handling by re-registering the token.
- Token revocation on logout, account switch, permission withdrawal, and uninstall signal when available.
- Local notification tap routing by `eventId`, `eventType`, `targetType`, and `targetId`.

## Release Gates

Frontend/native work is ready when:

- Durable notification center works without WebSocket or push.
- Realtime refresh works when a live endpoint is configured.
- Digest preview and digest send states match backend status.
- Push token registration/revocation works without raw token display.
- Role-specific notification targets route to real backend-backed pages.
- Demo data is never used to mask unavailable user-critical notification state.
