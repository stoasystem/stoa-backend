# Phase 114 Summary: Realtime Notification Client And UX

Status: complete
Completed: 2026-06-09

## Implementation

- Added feature-flagged realtime notification frontend configuration in `stoa-frontend`.
- Added a browser WebSocket notification hook that authenticates with the configured WebSocket URL, sends subscription and heartbeat messages, handles reconnect/offline/fallback states, and keeps polling active outside the live state.
- Added realtime notification parsing and React Query cache merge helpers with `eventId` dedupe.
- Updated the shared notification center to show compact `Live`, `Connecting`, `Reconnecting`, `Polling`, or `Offline` transport status while preserving the existing list/read/archive UX.
- Extended notification types for realtime delivery metadata and `system_notice`.
- Added Playwright coverage for polling fallback and tutor realtime teacher-session event delivery without page refresh.

## Frontend Commit

- `stoa-frontend`: `79c6628 feat: add realtime notification client`

## Verification

- `npm run lint` - passed.
- `npm run build` - passed with the existing Vite large-chunk warning.
- `npx playwright test tests/e2e/realtime-notifications.spec.ts -g "polling fallback"` - passed.
- `VITE_ENABLE_REALTIME_NOTIFICATIONS=true VITE_WEBSOCKET_BASE_URL=ws://127.0.0.1:65534/notifications npx playwright test tests/e2e/realtime-notifications.spec.ts -g "teacher session"` - passed.

## Notes

- Realtime is disabled by default until `VITE_ENABLE_REALTIME_NOTIFICATIONS=true` and `VITE_WEBSOCKET_BASE_URL` are configured.
- Browser WebSocket auth uses query parameters because browser WebSocket APIs cannot set arbitrary authorization headers.
- Durable persisted notifications remain canonical; realtime delivery only updates the user-facing cache immediately.
