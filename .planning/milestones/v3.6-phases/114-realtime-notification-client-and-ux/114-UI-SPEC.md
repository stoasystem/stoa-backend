# Phase 114 UI Spec: Realtime Notification UX

## Surface

Use the existing notification bell popover in `NotificationCenter`. Do not introduce a new page, hero, dashboard card, or marketing-style explanation.

## Interaction States

- Disabled: realtime is off by env flag or no WebSocket URL is configured; polling remains active.
- Connecting: authenticated connection is being opened.
- Live: WebSocket is open and heartbeat is active.
- Reconnecting: connection dropped and retry timer is active.
- Fallback: browser is offline or repeated transport failure occurred; polling remains active.

## Visual Treatment

- Add one compact status row in the popover header using existing badge/button primitives and lucide icons.
- Keep the unread count badge prominent; realtime status is secondary.
- Use short operational copy:
  - `Live`
  - `Connecting`
  - `Reconnecting`
  - `Polling`
  - `Offline`
- Avoid long instructional text and avoid changing notification card layout beyond preserving text fit.

## Data Behavior

- Inbound realtime events prepend to the existing notification list cache.
- Existing events with the same `eventId` are replaced by the incoming event.
- Admin cache receives admin-role realtime events; standard list receives events visible to the current user.
- Mutations keep their existing invalidation behavior.

## Verification

- Browser fixture proves an enabled WebSocket can add a notification without page refresh.
- Browser fixture proves missing endpoint/fallback does not break the notification center.
- Existing role-shell tests continue to see notification center and operational notifications.
