# Phase 257: Provider Activation Reality Audit And Release Contract - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

This phase defines the v5.17 provider activation release contract from current backend/frontend reality. It maps payment, Cognito/email, notification, support-provider, and production read-only smoke readiness surfaces to concrete code, configuration, tests, docs, credentials, rollout controls, safe fixtures, approval gates, and missing readiness/refusal evidence. It does not run live customer-impacting provider mutation.

</domain>

<decisions>
## Implementation Decisions

### Provider Classification
- Classify each provider channel as one of: `live_ready`, `read_only_verifiable`, `safe_fixture_verifiable`, `locally_ready`, or `blocked`.
- Treat missing credentials, missing approved destinations, missing registered webhooks, missing finance acceptance, or missing rollout approval as first-class blocked states, not test failures.
- Keep phase output support-safe: no raw provider payloads, Cognito token material, verification codes, private learning content, report artifact keys, or secrets.
- Use existing readiness surfaces first, then identify gaps for Phase 258 through Phase 260 instead of adding broad implementation in this audit phase.

### Evidence Boundary
- Evidence should point to specific settings, routes, services, tests, and docs so later phases can close gaps without rediscovery.
- Readiness evidence must include required credentials, rollout flags, production endpoints, safe fixtures, and approval gates per provider.
- Provider failure evidence must be deterministic and redacted; errors such as Stripe or support-provider exceptions must not leak secret-like values.
- Production smoke evidence must explicitly state whether it was live, read-only, safe-fixture, locally ready, or blocked.

### Safe Smoke Strategy
- Default production smoke mode is read-only unless an approved safe fixture and explicit mutation mode exist.
- Payment smoke can inspect provider readiness and rollout controls, but live charge/refund/customer-impacting checkout remains blocked unless explicit approval is present.
- Cognito/email smoke can verify account lifecycle/readiness state; live email delivery must be separated from local confirmation behavior and must report provider blockers.
- Notification/support smoke must refuse customer-impacting sends unless approved credentials, destination policy, templates, and rollout mode exist.

### Gap Routing
- Payment and Cognito/email gaps route to Phase 258.
- Notification and support provider gaps route to Phase 259.
- Deploy evidence, admin session path, browser smoke URLs, request IDs, and no-mutation boundaries route to Phase 260.
- Cross-provider rollback/disable controls and final activation outcome taxonomy route to Phase 261.

### the agent's Discretion
- Use the codebase's existing readiness naming where it is already established, but normalize final release evidence to the v5.17 outcome taxonomy.
- Prefer documentation plus focused tests for this audit phase; only add runtime code if it is required to make missing evidence observable.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Payment readiness and rollout controls exist around `src/stoa/services/subscription_service.py`, admin billing routes, and `tests/test_subscription_operations.py`, including provider readiness, TWINT capability, webhook observed event, refund control, and rollout rollback coverage.
- Cognito/email verification behavior exists in `src/stoa/routers/auth.py`, `src/stoa/services/account_verification_service.py`, account operations aggregation, and related auth/account lifecycle tests.
- Notification readiness foundations exist in `src/stoa/services/notification_service.py`, `src/stoa/services/websocket_service.py`, `src/stoa/config.py`, and `tests/test_websocket_notifications.py`.
- Support-provider readiness foundations exist in support destination/handoff/provider services and v4.5/v4.8 milestone evidence, with internal queue and third-party/CRM rollout settings in `src/stoa/config.py`.
- Production smoke precedent exists in `src/stoa/services/core_smoke_service.py`, report artifact smoke tests, release evidence docs, deployment workflow evidence, and prior milestone browser/API smoke records.

### Established Patterns
- Admin readiness APIs return redacted, support-safe status instead of raw provider payloads.
- Rollout controls and static settings are used to distinguish provider configuration from approved live enablement.
- Tests assert refusal/blocker states and secret redaction rather than requiring real external credentials.
- GSD release gates record exact commands, request IDs, route names, and blocked prerequisite tables when live providers are unavailable.

### Integration Points
- `src/stoa/config.py` contains relevant flags: Cognito IDs, WebSocket live status, notification provider approvals/send enablement, Stripe/TWINT keys and rollout flags, support third-party/CRM approvals and endpoints.
- Admin billing/account operations endpoints are the likely surfaces for payment and verification readiness evidence.
- Notification/admin notification endpoints and WebSocket readiness services are the likely surfaces for notification evidence.
- Support handoff/provider services are the likely surfaces for support provider evidence.
- `.planning/MILESTONES.md`, `.planning/NEXT-MILESTONES.md`, `.planning/REQUIREMENTS.md`, and final phase artifacts should carry the v5.17 blocked/live/safe-fixture taxonomy forward.

</code_context>

<specifics>
## Specific Ideas

- Produce a provider activation reality audit artifact in Phase 257 that is concrete enough for Phase 258-260 implementation planning.
- Keep all external activation operations fail-closed until production credentials, approved destinations, safe fixtures, and rollout approvals are explicit.
- Use v5.16 evidence as the baseline: local product readiness is complete, while external activation remains the primary uncertainty.

</specifics>

<deferred>
## Deferred Ideas

- Live Stripe/TWINT customer charging and live refunds are deferred until explicit provider credentials, finance acceptance, webhook registration, and rollout enablement exist.
- Live notification push/email and support CRM/customer messaging writes are deferred until approved providers, destinations, templates, credentials, and rollout approvals exist.
- Warehouse/BI/APM activation is deferred to v5.18.
- Native/mobile implementation is deferred to v5.19.

</deferred>
