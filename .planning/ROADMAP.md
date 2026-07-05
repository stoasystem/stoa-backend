# Roadmap: v5.17 External Provider Activation Smoke And Release Operations

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.16 End-To-End Product Readiness And Release Evidence

## Goal

Convert the external activation blockers identified by v5.16 into approved, bounded release operations: live/provider readiness checks, controlled smoke paths, rollout controls, refusal evidence when credentials are missing, and production-safe release runbooks for payment, Cognito/email, notifications, support provider handoff, and production deploy/read-only verification.

## Why This Is The Next Milestone

v5.16 proved the local product is ready across auth, billing, entitlement, usage/quota, curriculum, teacher help, and support views. The remaining gaps are no longer primarily internal feature gaps:

- Live Stripe/TWINT charging and webhook activation still require approved credentials, registered endpoints, finance acceptance, and explicit rollout enablement.
- Cognito/email delivery needs production-safe smoke evidence rather than only local confirmation behavior.
- Notification delivery has durable preferences, provider-gated email/push, WebSocket readiness, and admin delivery status, but live provider activation remains gated.
- Support provider handoff has internal/provider adapter readiness and retry/sync behavior, but real external writes require approved provider credentials and destination policy.
- Production deploy/live smoke remains separate from local product readiness.

The next milestone should therefore focus on release operations and provider activation boundaries, not new product features.

## Product Purpose

- Operators can tell which provider channels are live-ready, blocked, or deliberately disabled.
- Release evidence can prove safe production-readiness without exposing secrets or raw provider payloads.
- Approved live smoke paths exist for payment, email/auth, notifications, support handoff, and deploy/read-only verification.
- If credentials are unavailable, the app returns explicit refusal/readiness evidence instead of ambiguous partial activation.

## Implementation Strategy

- Start with a provider activation reality audit across settings, admin readiness APIs, frontend surfaces, tests, and deployment docs.
- Treat every live mutation path as opt-in and controlled by explicit rollout flags.
- Prefer read-only readiness and approved safe-fixture smoke before live customer-impacting mutation.
- Use existing provider readiness APIs where available; add only missing readiness/refusal evidence needed for release operations.
- Keep secrets redacted and provider payloads bounded.
- If live credentials are unavailable, close the milestone with refusal evidence and operational runbooks rather than pretending activation happened.

## Phases

- [x] **Phase 257: Provider Activation Reality Audit And Release Contract** - Map live-provider readiness surfaces, settings, credentials, rollout flags, existing tests, and missing evidence. (completed 2026-07-05)
- [x] **Phase 258: Payment And Cognito Email Smoke Operations** - Define and verify approved live/readiness smoke paths for Stripe/TWINT and Cognito/email delivery, with blocked states when credentials are unavailable. (completed 2026-07-05)
- [ ] **Phase 259: Notification And Support Provider Smoke Operations** - Define and verify provider-gated notification and support handoff smoke/readiness paths, retry/refusal evidence, and operator status visibility.
- [ ] **Phase 260: Production Deploy Readiness And Read-Only Browser Smoke** - Consolidate backend/frontend deploy evidence, release runbook, admin session path, read-only browser smoke, and no-mutation boundaries.
- [ ] **Phase 261: v5.17 External Provider Release Gate** - Close with provider activation evidence, blocked-prerequisite table, rollback controls, and next milestone decision.

## Phase Details

### Phase 257: Provider Activation Reality Audit And Release Contract

**Goal**: Define exact provider activation scope from current code and current blockers.
**Requirements**: PROVIDER-01
**Success Criteria**:

1. Payment, Cognito/email, notification, support provider, and deploy/read-only smoke readiness surfaces are mapped to code/docs/tests.
2. Required credentials, rollout flags, safe fixtures, and approval gates are listed per provider.
3. Missing readiness/refusal evidence is identified before implementation.
4. v5.17 distinguishes live activation, read-only readiness, safe-fixture smoke, and blocked states.

### Phase 258: Payment And Cognito Email Smoke Operations

**Goal**: Make payment and account-entry provider readiness operationally verifiable.
**Requirements**: PROVIDER-02
**Success Criteria**:

1. Stripe/TWINT readiness reports live credential, webhook, TWINT, finance, rollout, refund, and smoke status in redacted form.
2. Payment smoke paths are read-only or safe-fixture bounded unless live rollout is explicitly approved.
3. Cognito/email smoke distinguishes verified local auth behavior, email-delivery readiness, and blocked production delivery prerequisites.
4. Tests or documented smoke outputs prove blocked states fail closed.

### Phase 259: Notification And Support Provider Smoke Operations

**Goal**: Make notification and support-provider activation status visible and bounded.
**Requirements**: PROVIDER-03
**Success Criteria**:

1. Notification readiness covers WebSocket, email digest, push provider, token registration, preferences, provider refusal, and delivery-status evidence.
2. Support-provider readiness covers internal queue, third-party delivery, retry, provider sync, CRM messaging, templates, and destination approval.
3. Smoke paths avoid customer-impacting sends unless approved credentials and fixtures exist.
4. Operator views expose success/refusal/failure evidence without raw provider payloads.

### Phase 260: Production Deploy Readiness And Read-Only Browser Smoke

**Goal**: Make production verification repeatable without unsafe mutation.
**Requirements**: RELEASEOPS-01
**Success Criteria**:

1. Backend and frontend deploy evidence requirements are documented.
2. Admin session path, browser smoke URLs, API request IDs, and no-mutation boundaries are listed.
3. Read-only smoke covers auth, account operations, billing readiness, curriculum/admin readiness, notifications/support readiness, and core smoke output.
4. Production mutation is refused unless an approved safe fixture and explicit mutation mode are present.

### Phase 261: v5.17 External Provider Release Gate

**Goal**: Close v5.17 with an honest provider activation state.
**Requirements**: VERIFY-51
**Success Criteria**:

1. Focused backend/frontend checks pass for readiness/refusal surfaces touched by v5.17.
2. Provider activation evidence is recorded as live-passed, read-only-passed, safe-fixture-passed, or blocked with exact prerequisite.
3. Rollback/disable controls are documented for each provider.
4. Docs, roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.

## Future Milestone Directions

- **v5.18 Warehouse BI Observability And Product Analytics Activation**: activate operational analytics, aggregate exports, dashboards, and APM/alerting after provider readiness is explicit.
- **v5.19 Native Mobile Push And Offline Client Implementation**: implement native/mobile client and push/offline behavior after web release operations are stable.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 257 Provider Activation Reality Audit And Release Contract | v5.17 | 1/1 | Complete | 2026-07-05 |
| 258 Payment And Cognito Email Smoke Operations | v5.17 | 1/1 | Complete | 2026-07-05 |
| 259 Notification And Support Provider Smoke Operations | v5.17 | 0/1 | Planned | - |
| 260 Production Deploy Readiness And Read-Only Browser Smoke | v5.17 | 0/1 | Planned | - |
| 261 v5.17 External Provider Release Gate | v5.17 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROVIDER-01 | Phase 257 | Complete |
| PROVIDER-02 | Phase 258 | Complete |
| PROVIDER-03 | Phase 259 | Planned |
| RELEASEOPS-01 | Phase 260 | Planned |
| VERIFY-51 | Phase 261 | Planned |
