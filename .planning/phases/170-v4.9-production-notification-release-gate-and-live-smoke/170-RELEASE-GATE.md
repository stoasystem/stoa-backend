# v4.9 Production Notification Release Gate

## Result

v4.9 backend release gate passed.

Overall rollout state: `deferred`.

## Verification

- Full backend tests: `./.venv/bin/pytest -q` -> 411 passed.
- Static check: `./.venv/bin/ruff check src tests` -> passed.
- Whitespace check: `git diff --check` -> passed.

## Scope Completed

### Phase 166

Production notification rollout contract and ownership boundaries are documented across backend, frontend, native, infrastructure, and providers.

### Phase 167

Backend live WebSocket readiness is observable through runtime settings and admin delivery status:

- `local_only`, `configured`, `deployed`, `provider_blocked`, and `live_ready` modes.
- Redacted endpoint host.
- Route/deploy/smoke flags.
- Stale cleanup and connection counts.
- Recent redacted WebSocket delivery attempt evidence.

### Phase 168

Provider-backed email digest and push delivery are implemented behind explicit provider gates:

- Email digest preview remains read-only.
- Manual digest send path records redacted event-level send/refusal/failure evidence.
- Push token registration stores token hashes and provider references, not raw native tokens in responses.
- Push delivery records missing-token, success, and provider-failure evidence without breaking durable event creation.
- Admin delivery status exposes email and push provider readiness.

### Phase 169

Frontend/native notification UX handoff is documented:

- Notification center/list/read/archive.
- Preferences.
- Digest preview/send.
- Push token registration/revocation.
- WebSocket endpoint discovery and reconnect/offline behavior.
- Role UX for student, parent, tutor/teacher, and admin.
- `/Users/zhdeng/stoa-frontend` and future native app follow-up points.
- No hidden demo fallback constraints.

## Live Smoke Status

No live smoke was run.

Live WebSocket/API Gateway smoke remains deferred until deployment owner configures:

- `WEBSOCKET_API_ENDPOINT`
- `WEBSOCKET_LIVE_ROUTES_CONFIGURED`
- `WEBSOCKET_LIVE_DEPLOYED`
- `WEBSOCKET_LIVE_SMOKE_PASSED`
- `WEBSOCKET_STALE_CLEANUP_ENABLED`

Email/push provider live smoke remains deferred until provider owners configure approved credentials, templates, sender/domain state, endpoint/reference semantics, and explicit send enablement.

## External Activation Prerequisites

- Live API Gateway WebSocket deployment and route integration.
- Approved email provider and sender/domain/template setup.
- Approved push provider and native token/reference semantics.
- Frontend implementation in `/Users/zhdeng/stoa-frontend`.
- Native app token capture, secure storage, registration, and revocation.
- Explicit rollout approval for real user notification sends.

## Rollback

Backend changes are gated by configuration:

- WebSocket remains `local_only` without endpoint/deploy/smoke settings.
- Email sends remain refused unless provider and send gates are enabled.
- Push sends remain refused unless provider, endpoint, and send gates are enabled.
- Durable notification list/read/archive behavior remains the fallback.

## Next Milestone Recommendation

Recommended next milestone: native mobile and full localization governance.

Reason: v4.9 completed backend notification rollout readiness and frontend/native handoff. The remaining highest-value product gap is client-side/native execution and localization governance unless final live payment or support provider activation prerequisites become available first.
