# Phase 114 Context: Realtime Notification Client And UX

## Decision Summary

User delegated implementation decisions. Build a conservative, feature-flagged WebSocket client in `stoa-frontend` that augments the existing notification center and React Query caches. The existing polling query remains the fallback and the primary persisted source of truth.

## Current Frontend State

- `NotificationCenter` is shared through `AppLayout`, so student, parent, tutor, and admin shells already have a common notification entry point.
- Notification data flows through `useNotificationsQuery`, `useAdminNotificationsQuery`, `notificationApi`, and `notificationQueryKeys`.
- Demo fallback returns mock notification events when the API is unavailable.
- Auth token is stored in `useAuthStore` and `localStorage` under `stoa_access_token`.
- Browser WebSocket connections cannot set arbitrary Authorization headers, so the authenticated client will pass the access token as a query parameter to the configured WebSocket URL.

## Scope

- Add frontend env flags for realtime notification enablement and WebSocket base URL.
- Add a browser-safe realtime notification client/hook with authenticated connect, heartbeat, reconnect, offline handling, and fallback status.
- Merge inbound notification events into React Query caches with event-id dedupe.
- Keep the notification center compact and consistent with the existing operational UI, adding only subtle realtime/fallback status.
- Add targeted Playwright coverage with a local WebSocket fixture.

## Out Of Scope

- Native push notifications.
- Email/SMS notification delivery.
- Production API Gateway route wiring beyond consuming a configured WebSocket URL.
- Replacing the persisted notification list as the source of truth.

## Risk Notes

- The WebSocket endpoint is not always configured locally or in demo mode, so disabled/fallback states must be explicit.
- Query-param token transport should only be used over TLS-backed `wss://` outside local development.
- Incoming events may be duplicated across role/user channels; cache merge must dedupe by `eventId`.
