# Phase 169 Context: Frontend And Native Notification UX Handoff

## Starting Point

Phases 167 and 168 added backend readiness/status for live WebSocket rollout, provider-backed email digest delivery, push token registration/revocation, and push delivery evidence. The remaining Phase 169 work is to define the frontend/native integration contract so `/Users/zhdeng/stoa-frontend` and future native clients can wire the UX without hidden fallback behavior.

## Backend Surfaces

- `GET /notifications`
- `POST /notifications/{eventId}/read`
- `POST /notifications/{eventId}/archive`
- `GET /notifications/preferences`
- `PATCH /notifications/preferences`
- `GET /notifications/digest-preview`
- `POST /notifications/digest-send`
- `POST /notifications/push-tokens`
- `DELETE /notifications/push-tokens/{tokenReference}`
- `GET /admin/notifications`
- `GET /admin/notifications/delivery-status`

## Requirement

`PRODNOTIF-04` requires a frontend/native handoff that documents:

- API routes and WebSocket endpoint discovery.
- Token registration contract.
- Preference UI behavior.
- Notification center refresh behavior.
- Fallback states.
- Student, parent, tutor, and admin live notification UX expectations.
- Native push token lifecycle fields.
- Cross-workspace follow-up points for `/Users/zhdeng/stoa-frontend` and future native apps.
- No hidden demo fallback for user-critical notification flows.

## Decisions

- Frontend should use durable notification list/read/archive as the source of truth.
- WebSocket events should trigger refresh/sync, not replace durable state.
- Native push tokens should be registered after platform permission and revoked on logout, uninstall signal, or permission withdrawal.
- Provider-disabled and live-unavailable states should be visible as degraded states, not masked by demo data.
