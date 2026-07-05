# Phase 257 Provider Activation Reality Audit

**Milestone:** v5.17 External Provider Activation Smoke And Release Operations  
**Requirement:** PROVIDER-01  
**Created:** 2026-07-05  
**Scope:** Payment, Cognito/email, notifications, support-provider handoff, and production read-only smoke.

## Outcome Taxonomy

| Outcome | Meaning | Mutation Allowed |
|---------|---------|------------------|
| `live_ready` | Provider credentials, rollout controls, endpoint wiring, and required approvals are present. | Only through explicit approved operation path. |
| `read_only_verifiable` | Current production state can be inspected without provider/customer mutation. | No. |
| `safe_fixture_verifiable` | A named non-customer fixture or explicit mutation mode can exercise behavior safely. | Only against the approved fixture/mode. |
| `locally_ready` | Local tests and redacted contracts prove behavior, but live provider prerequisites are missing. | No. |
| `blocked` | Missing credential, endpoint, approval, destination, safe fixture, or rollout enablement prevents safe activation. | No. |

## Provider Matrix

| Channel | Current Classification | Existing Surfaces | Required Activation Inputs | Phase Follow-Up |
|---------|------------------------|-------------------|----------------------------|-----------------|
| Stripe/TWINT checkout and webhook | `read_only_verifiable` / `locally_ready`; live customer charging remains `blocked` without approvals | `src/stoa/services/subscription_service.py`; `src/stoa/routers/parents.py`; `src/stoa/routers/billing.py`; `src/stoa/routers/admin.py`; `tests/test_subscription_operations.py` | `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, live standard/premium price IDs, HTTPS webhook endpoint, TWINT capability confirmation, finance acceptance, checkout rollout `enabled`, explicit live smoke approval | Phase 258 |
| Stripe refund/accounting handoff | `safe_fixture_verifiable` locally; live refund remains `blocked` without rollout and provider approval | `POST /admin/subscriptions/billing/{parent_id}/refund`; accounting export; rollout controls; refund failure redaction tests | Active billing fixture with provider charge/payment intent, refund rollout `enabled`, idempotency key, finance approval, safe fixture or explicit live mutation approval | Phase 258 |
| Cognito sign-up confirmation and email verification | `locally_ready`; live email delivery smoke remains `blocked` unless delivery/inbox is approved | `src/stoa/routers/auth.py`; `src/stoa/services/account_verification_service.py`; `tests/test_auth_account_lifecycle.py`; frontend verification UX in `/Users/zhdeng/stoa-frontend` | Cognito user pool/client IDs, app client auth flow, SES/Cognito email delivery configuration, approved disposable/test inbox, no raw code logging, resend/confirm rate-limit expectations | Phase 258 |
| Login code/passwordless | `blocked` by policy | `LOGIN_CODE_POLICY = deferred_cognito_custom_auth_required`; request/confirm endpoints return deferred policy | Cognito custom-auth design, token minting contract, abuse controls, frontend UX approval | Not v5.17 activation unless explicitly approved; keep blocked evidence |
| WebSocket realtime notifications | `read_only_verifiable`; live smoke may be `blocked` or `live_ready` depending settings | `src/stoa/services/websocket_service.py`; `tests/test_websocket_notifications.py`; admin notification readiness response | WebSocket endpoint, deployed route flags, connect/disconnect/message route names, live smoke flag, stale cleanup policy | Phase 259 |
| Notification email digest | `locally_ready` / `blocked` until provider approval and send enablement | `src/stoa/services/notification_service.py`; provider readiness helpers; notification preferences | Approved email provider, sender, template, send enablement, delivery destination/safe fixture, redacted attempt logging | Phase 259 |
| Notification push | `blocked` until provider, endpoint, tokens, and send enablement exist | Push token registration/revoke routes; `push_provider_readiness`; safe delivery attempt recording | Approved push provider, endpoint URL, API key, template, active non-customer token fixture, send enablement | Phase 259 |
| Support handoff internal queue | `safe_fixture_verifiable` / `read_only_verifiable` | `src/stoa/services/support_destination_service.py`; admin support handoff package/delivery/list/detail/SLA routes | Internal queue approval flag, destination policy, fixture package, no private report artifact exposure | Phase 259 |
| Third-party support provider and CRM/customer messaging | `blocked` until approved provider/destination/templates/credentials exist | Support destination readiness/refusal logic; third-party delivery/CRM settings in `src/stoa/config.py`; admin handoff delivery refusal paths | Approved provider, endpoint/API key, approved destination policy, approved CRM templates, send enablement, retry/sync policy | Phase 259 |
| Production deploy/read-only smoke | `read_only_verifiable`; mutation smoke `blocked` unless safe fixture exists | GitHub Actions deploy workflows; `/health`; `/admin/core-smoke`; prior release-gate docs; `tests/test_core_smoke.py` | Backend/frontend deploy run IDs, bundle hash, admin session path, API request IDs, smoke route list, no-mutation confirmation, optional safe fixture | Phase 260 |

## Current Concrete Surfaces

### Payment

- Parent checkout route: `POST /parents/me/subscription/checkout`.
- Stripe webhook route: `POST /billing/webhooks/stripe`.
- Admin readiness: `GET /admin/subscriptions/billing/provider-readiness`.
- Admin rollout controls: `GET/PATCH /admin/subscriptions/billing/rollout-controls`.
- Admin accounting export: `GET /admin/subscriptions/billing/accounting-export`.
- Direct refund operation: `POST /admin/subscriptions/billing/{parent_id}/refund`.
- Tests cover missing production config, test key rejection in production, TWINT pending/active states, provider error redaction, webhook last observed event, checkout rollback, refund rollback, direct refund success/failure, webhook signature enforcement, duplicate/stale webhook behavior, and accounting export.

### Cognito/Email

- Registration uses Cognito `sign_up` and stores pending verification state.
- Verification resend uses Cognito `resend_confirmation_code`.
- Verification confirm uses Cognito `confirm_sign_up`.
- Login refuses token return while local profile requires verification and repairs local state after Cognito auth succeeds.
- Login-code/passwordless remains explicitly deferred through `LOGIN_CODE_POLICY`.
- Tests cover register state, resend idempotency, provider delivery records, already-confirmed repairs, expired/wrong/rate-limited code normalization, disabled account behavior, support visibility, and login-code deferred policy.

### Notifications

- WebSocket readiness uses `websocket_live_routes_configured`, `websocket_live_deployed`, `websocket_live_smoke_passed`, route names, endpoint, and stale cleanup.
- Notification delivery readiness covers in-app, realtime, email digest, push, provider approval, send enablement, templates, endpoints, and token lifecycle.
- Tests cover WebSocket readiness mode transitions and delivery failure resilience.

### Support Provider Handoff

- Support handoff package generation is metadata-only and redacted.
- Support handoff delivery supports internal queue, third-party support provider, contract-defined refused destinations, delivery lifecycle records, detail, and SLA analytics.
- Third-party delivery refuses when provider is not approved or credentials are missing.
- CRM/customer messaging settings exist but remain gated by approved templates, destination policy, and rollout approval.

### Production Smoke

- Core smoke API: `GET /admin/core-smoke`.
- Core smoke service reports expected blockers for auth/account operations/billing/question/conversation/practice flows without private payloads.
- Existing release patterns record deploy run ID, Lambda state, frontend bundle, request IDs, admin identity, route list, and no-mutation confirmation.

## Missing Evidence Promoted Forward

| Gap | Owner Phase | Required Output |
|-----|-------------|-----------------|
| One payment readiness response that summarizes live credential, webhook, TWINT, finance, rollout, refund, and smoke state in the v5.17 taxonomy. | Phase 258 | Focused readiness/smoke evidence plus tests if current shape lacks any field. |
| Explicit Cognito/email live delivery smoke classification separating local verification from provider email delivery and disabled/blocked account states. | Phase 258 | Readiness/refusal evidence and support-safe smoke procedure. |
| Notification readiness evidence that combines WebSocket, email digest, push provider, token fixture, preference gating, and send enablement. | Phase 259 | Operator-visible success/refusal/failure output without raw provider payloads. |
| Support-provider readiness evidence that combines internal queue, third-party, retry/sync, CRM templates, destination approval, and refusal lifecycle. | Phase 259 | Operator-visible readiness/refusal matrix and tests/docs for missing credentials. |
| Repeatable production read-only smoke checklist across auth/account operations/billing/curriculum/notifications/support/core smoke. | Phase 260 | Browser/API smoke checklist with request IDs and no-mutation proof. |
| Final provider outcome table plus rollback/disable controls per provider. | Phase 261 | Milestone release gate evidence and next-milestone handoff. |

## Release Contract

1. Live customer-impacting operations require three things at once: provider credentials, rollout approval, and either safe fixture or explicit live activation approval.
2. Missing provider inputs close as `blocked`, not failed implementation.
3. Provider readiness endpoints and docs must redact secrets and raw provider payloads.
4. Production smoke defaults to read-only.
5. Every provider channel must expose a rollback or disable control in final release evidence, even if that control is "keep rollout disabled."
