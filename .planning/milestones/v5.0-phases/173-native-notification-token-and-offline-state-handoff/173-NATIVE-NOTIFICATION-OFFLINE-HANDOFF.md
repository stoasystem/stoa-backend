# Phase 173 Native Notification Token And Offline State Handoff

**Milestone:** v5.0 Native Mobile And Full Localization Governance
**Requirement:** MOBILELOC-03
**Status:** Accepted for implementation by later phases
**Date:** 2026-06-14

## Scope

This handoff defines how future native apps and mobile/PWA clients should integrate STOA notifications, push tokens, preferences, reconnect behavior, offline/read-through states, and deep-link routing.

Durable backend notification state is authoritative. WebSocket, email digest, and push are delivery accelerators and must reconcile back to `GET /notifications`.

## Backend Contract

| Capability | Route or service | Current support | Client responsibility |
|------------|------------------|-----------------|-----------------------|
| Notification list | `GET /notifications?status=&limit=` | Supported with durable event state and default archived exclusion | Render loading, empty, unread/read/archive, unavailable, stale/offline |
| Read/archive | `POST /notifications/{eventId}/read`, `POST /notifications/{eventId}/archive` | Supported with ownership/visibility checks | Mutate only online; rollback/refetch on failure |
| Preferences | `GET/PATCH /notifications/preferences` | Supported for categories and `in_app`, `realtime`, `email_digest`, `push` channels | Render only backend-returned categories/channels; preserve unspecified channel values |
| Digest preview/send | `GET /notifications/digest-preview`, `POST /notifications/digest-send` | Supported with provider-disabled/refusal states | Surface provider-disabled/no-items/missing-email states |
| Push token register | `POST /notifications/push-tokens` | Supported for `ios`, `android`, `web`, raw token or provider reference, device ID hash | Capture token securely and submit after permission grant |
| Push token revoke | `DELETE /notifications/push-tokens/{tokenReference}` | Supported; marks token `revoked` | Call on logout, account switch, permission withdrawal, explicit disablement |
| Delivery status | `GET /admin/notifications/delivery-status` | Supported for operator/admin readiness | Admin-only readiness surface; do not expose secrets or raw tokens |

## Push Token Registration

Native request:

```json
{
  "platform": "ios",
  "token": "raw-platform-token-if-available",
  "providerTokenReference": "provider-reference-if-issued",
  "deviceId": "stable-installation-id"
}
```

Backend response:

```json
{
  "tokenReference": "push-...",
  "platform": "ios",
  "status": "active",
  "tokenHashPrefix": "...",
  "hasProviderReference": true,
  "createdAt": "2026-06-14T00:00:00+00:00",
  "lastSeenAt": "2026-06-14T00:00:00+00:00",
  "revokedAt": null
}
```

Rules:

- Supported platforms are `ios`, `android`, and `web`.
- Native clients should prefer provider token references when available.
- Raw push tokens must be stored only in platform secure storage and should never be displayed or logged.
- `deviceId` should be a stable install/device identifier when platform policy permits; backend stores only a hash.
- Re-registering the same token should refresh active token evidence and `lastSeenAt`.
- The backend returns `tokenReference`; clients should store it for revocation.

## Token Lifecycle Triggers

| Trigger | Required client action | Expected backend state |
|---------|------------------------|------------------------|
| Permission first granted | Register token | `active`, `lastSeenAt` set |
| Token refresh from APNS/FCM/web push | Register new token/reference | New or updated active token |
| App foreground after long gap | Re-register or refresh token if platform indicates change | `lastSeenAt` refreshed |
| Logout | Revoke token reference before clearing session when possible | `revoked`, `revokedAt` set |
| Account switch | Revoke old account token, register under new account | Old token revoked; new account active |
| Permission withdrawal | Revoke token reference and set local permission state denied | `revoked` |
| Explicit push preference off | Patch preferences and optionally revoke if product policy says device opt-out means token removal | `push=false`; token may remain active unless revoked |
| Uninstall signal | Revoke if platform/provider emits a signal | `revoked` when signal available |

## Permission And Provider States

Clients should distinguish:

- `not_requested`: no platform permission prompt shown.
- `granted`: platform permission available and token can be registered.
- `denied`: permission denied; show settings guidance, do not repeatedly prompt.
- `provisional` or `limited`: platform-specific quiet/limited permission; treat as enabled with constrained UX.
- `provider_disabled`: backend/provider configuration is missing or send gate is off.
- `preference_off`: user disabled push preference for the category.
- `missing_token`: permission or token capture is absent.
- `send_failed`: provider path attempted and failed; show retry only when product policy allows.

## Notification UX States

| State | Client behavior |
|-------|-----------------|
| `live` | WebSocket/realtime refresh is connected; realtime events update cache and trigger durable refetch. |
| `reconnecting` | Show quiet status, keep durable list visible, refetch after reconnect. |
| `fallback` | Poll/refetch durable list; notification center remains usable. |
| `offline` | Show stale cached list if available; disable read/archive mutations or require explicit retry later. |
| `empty` | Authenticated and authorized, no visible events. |
| `unavailable` | Backend/provider unavailable; show retry/manual refresh, do not substitute demo events. |
| `permission-denied` | Push-specific state; durable in-app notification center remains available. |
| `provider-disabled` | Push/digest send unavailable; durable in-app and realtime/polling may still work. |

## Deep-Link And Tap Routing

Push payload and realtime envelopes should carry:

- `eventId`
- `eventType`
- `targetType`
- `targetId`
- authenticated `recipientRole` where available

Routing policy:

- Open the authenticated app shell first, then route by target.
- If unauthenticated, preserve the pending route and require login.
- If the target is stale, unauthorized, or deleted, open notification center with an unavailable-target message.
- Parent child/report links must re-check ownership through backend routes.
- Admin/operator links must never expose raw private artifacts, provider secrets, raw push tokens, or internal error payloads.

Suggested mapping:

| Target type | Destination |
|-------------|-------------|
| `question` | Student question detail or tutor request detail depending on role. |
| `assignment` | Student assignment detail or tutor/admin assignment management. |
| `weekly_report` / `report` | Parent child report route after ownership check. |
| `subscription_request` | Parent billing status or admin subscription request detail. |
| `moderation_case` | Admin moderation case detail. |
| `notification` / unknown | Notification center fallback. |

## Offline/Read-Through Behavior

| Surface | Offline behavior |
|---------|------------------|
| Notification center | Show stale cached list, disable read/archive until online, refetch on reconnect. |
| Learning history | Show last cached history with stale label; refetch on app foreground/reconnect. |
| Reports | Show last cached report metadata/content if already loaded; missing/pending/failed states must come from backend when online. |
| Assignments | Show cached assignment list/detail; do not queue start/complete/skip unless a future native workspace defines conflict handling. |
| Billing | Read-only cached status; checkout/refund/payment operations require online provider/backend state. |
| Support/admin status | Read-only cached queue/status; retry/sync/message mutations require online backend state. |

## Existing Support Versus Follow-Up

| Area | Backend | Frontend/PWA | Native follow-up |
|------|---------|--------------|------------------|
| Durable notification center | Supported | Supported visually, but current API uses demo fallback | Use same list/read/archive routes |
| Realtime refresh | Supported backend readiness and frontend hook | Existing hook supports live/reconnecting/fallback/offline | Native may use WebSocket or platform-specific foreground refresh |
| Preferences | Supported | Needs richer channel/category UI and no-demo-fallback release check | Native settings screen and permission synchronization |
| Digest | Supported backend preview/send states | Needs UI expansion for digest states | Optional native settings surface |
| Push token lifecycle | Supported backend register/revoke/hash/provider readiness | No full token client yet | Implement platform token capture and lifecycle triggers |
| Deep links | Payload fields available | Needs route mapping hardening | Implement tap routing and stale target fallback |
| Offline cache | Backend is source of truth | Query cache/fallback exists in places | Native local cache and foreground reconciliation |

## Release Gate Notes

Phase 175 should verify contract coverage without requiring live app-store release or live push sends. A v5.0 release can be `contract-ready` or `frontend-ready` while native push remains `deferred` if no native workspace/provider activation exists.
