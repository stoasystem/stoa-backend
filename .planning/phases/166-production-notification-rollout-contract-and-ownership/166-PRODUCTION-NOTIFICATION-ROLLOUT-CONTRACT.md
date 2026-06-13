# Phase 166 Production Notification Rollout Contract

## Scope

v4.9 promotes notification delivery from local/backend readiness to production-deliverable behavior. The milestone should wire or document live WebSocket/API Gateway readiness, provider-backed email digest and push delivery, frontend/native notification handoff, token registration, and release evidence.

## Ownership Boundaries

| Area | Owner | v4.9 Responsibility |
|------|-------|---------------------|
| Backend notification APIs | `stoa-backend` | Preferences, digest selection, delivery status, provider decisions, token registration API, delivery evidence |
| WebSocket runtime/infrastructure | `stoa-backend` plus CDK/deploy owner | Live route/runtime configuration, connect/disconnect/message handlers, endpoint exposure, stale cleanup |
| Frontend notification UX | `/Users/zhdeng/stoa-frontend` | Endpoint discovery, WebSocket client wiring, notification center state, preference UI, fallback UX |
| Native apps | Future native workspace | Push token registration, native notification permission UX, token revocation |
| Providers | Approved email/push provider accounts | Credentials, sender/domain setup, push app/platform setup, provider smoke |

## Rollout States

- `local_only`: local WebSocket/backend behavior exists, but no live deployment/provider configuration is available.
- `configured`: runtime/provider configuration is present but live smoke has not run.
- `provider_ready`: provider and backend readiness checks pass with no real user send.
- `live_smoked`: approved read-only or bounded smoke confirms live endpoint/provider behavior.
- `blocked`: required infrastructure, provider, template, token, or frontend/native prerequisite is missing.
- `deferred`: implementation is complete but live activation remains externally gated.

## Live WebSocket Contract

Required behavior:

- Authenticated connect/disconnect routes or equivalent API Gateway WebSocket integration.
- Subscription enforcement compatible with existing channel rules.
- Durable notification event persistence before or alongside realtime fanout.
- Delivery attempt metadata for success, no active connection, provider/runtime failure, and fallback.
- Stale connection cleanup visibility.
- Admin status that reports endpoint mode, configured route set, recent attempts, stale cleanup state, and blockers without secrets.

## Email Digest Contract

Required behavior:

- Provider mode: `disabled`, `configured`, `provider_ready`, `failed`.
- Digest recipient selection based on unread/eligible events, role, locale, and durable preferences.
- Template metadata and scheduling/manual trigger readiness.
- Send/refusal/failure evidence with provider result redacted.
- No provider-backed sends unless provider configuration and rollout approval are explicit.

## Push Delivery Contract

Required behavior:

- Native token registration API or documented handoff with platform, token reference/hash, lifecycle status, last seen timestamp, and revocation behavior.
- Provider mode: `disabled`, `configured`, `provider_ready`, `failed`.
- Preference-gated push decisions per event category/channel.
- Send/refusal/failure evidence with provider result redacted.
- Missing token and opted-out states treated as expected non-error outcomes.

## Frontend/Native Handoff

The integration handoff must define:

- API routes for notification list/read/archive, preferences, digest preview/status, delivery status, and token registration.
- WebSocket endpoint discovery and reconnect/offline behavior.
- Notification center refresh behavior after realtime events.
- Student, parent, tutor, and admin UX expectations.
- Native permission/token lifecycle and revocation expectations.
- No hidden demo fallback for user-critical notification state.

## Implementation Handoff

Phase 167 should implement or document live WebSocket/API Gateway readiness and admin delivery status.

Phase 168 should implement provider-backed email digest and push delivery behavior with preference gating and redacted evidence.

Phase 169 should define frontend/native UX and token-registration handoff.

Phase 170 should verify v4.9, record rollout state, and update the remaining-feature queue.
