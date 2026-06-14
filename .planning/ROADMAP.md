# Roadmap: v4.9 Production Notification And Native Delivery Rollout

**Status:** Active planning
**Created:** 2026-06-13
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Move notification delivery from local WebSocket/backend readiness into production-deliverable capability: live WebSocket/API Gateway readiness, provider-backed email and push delivery, frontend/native notification UX handoff, native token registration, and live smoke evidence.

## Execution Bias

Build notification delivery functionality directly. Keep verification focused on delivery behavior, preferences, provider configuration, fallback behavior, and rollout evidence. Do not spend this milestone on broad unrelated security/compliance testing during internal development.

## Phases

- [x] **Phase 166: Production Notification Rollout Contract And Ownership** - Define backend/frontend/native/infrastructure/provider ownership, live WebSocket expectations, email/push provider modes, live smoke boundaries, and rollout gates. (completed 2026-06-14)
- [x] **Phase 167: Live WebSocket API Gateway Deployment Readiness** - Add or document CDK/runtime readiness for live WebSocket routes, configured delivery status, fanout fallback, stale cleanup, and admin status. (completed 2026-06-14)
- [ ] **Phase 168: Provider-Backed Email Digest And Push Delivery** - Add provider-backed digest and push delivery behavior with preference gating, token readiness, redacted result evidence, and provider failure handling.
- [ ] **Phase 169: Frontend And Native Notification UX Handoff** - Define frontend/native API, WebSocket endpoint, token registration, notification center, preference UI, offline/reconnect, and fallback contracts.
- [ ] **Phase 170: v4.9 Production Notification Release Gate And Live Smoke** - Verify notification rollout behavior, docs, release evidence, live smoke status, and next milestone recommendation.

## Phase Details

### Phase 166: Production Notification Rollout Contract And Ownership

**Goal**: Define the production notification rollout contract before deployment/provider/native work expands.
**Depends on**: v3.6 local WebSocket notification scope, v4.2 production notification readiness, v4.8 closeout, and `stoa_docs` remaining-feature audit
**Requirements**: PRODNOTIF-01
**Success Criteria** (what must be TRUE):

  1. Backend, frontend, native, infrastructure, and provider ownership boundaries are documented.
  2. Live WebSocket/API Gateway route expectations, auth/subscription behavior, fallback behavior, and deployment prerequisites are documented.
  3. Email digest and push provider modes, credential/configuration states, preference behavior, and failure states are documented.
  4. In-scope notification event categories, rollout gates, observability evidence, rollback behavior, and live smoke boundaries are explicit.
  5. Phase 167 through Phase 170 implementation targets are concrete.

**Plans**: 1/1 plans complete

Plans:

- [x] 166-01: Define production notification rollout contract and ownership.

### Phase 167: Live WebSocket API Gateway Deployment Readiness

**Goal**: Prepare live WebSocket delivery readiness beyond local functional behavior.
**Depends on**: Phase 166
**Requirements**: PRODNOTIF-02
**Success Criteria** (what must be TRUE):

  1. WebSocket route/runtime/CDK readiness or implementation handoff is concrete.
  2. Delivery status distinguishes local-only, configured, deployed, provider-blocked, and live-ready states.
  3. Durable event fallback remains intact when live fanout fails.
  4. Admin/operator status exposes endpoint/configuration blockers and recent delivery attempt evidence without secrets.

**Plans**: 1/1 plans complete

Plans:

- [x] 167-01: Implement live WebSocket deployment readiness and status.

### Phase 168: Provider-Backed Email Digest And Push Delivery

**Goal**: Add configured-provider digest and push delivery behavior.
**Depends on**: Phase 167
**Requirements**: PRODNOTIF-03
**Success Criteria** (what must be TRUE):

  1. Email digest send path supports provider configuration, recipient selection, template metadata, and send/refusal/failure evidence.
  2. Push delivery path supports provider configuration, native token readiness, token lifecycle state, preference gating, and send/refusal/failure evidence.
  3. Notification preferences and category/channel rules are honored for every delivery decision.
  4. Provider responses are redacted and useful for operator diagnostics.

**Plans**: 0/1 plans complete

Plans:

- [ ] 168-01: Implement provider-backed email digest and push delivery.

### Phase 169: Frontend And Native Notification UX Handoff

**Goal**: Define the frontend/native integration contract for live notification delivery.
**Depends on**: Phase 168
**Requirements**: PRODNOTIF-04
**Success Criteria** (what must be TRUE):

  1. API routes, WebSocket endpoint discovery, token registration, preference UI, notification center refresh, and fallback behavior are documented.
  2. Student, parent, tutor, and admin live notification UX expectations are documented.
  3. Native push token registration contract includes platform, token reference/hash, lifecycle state, last seen timestamp, and revocation behavior.
  4. Cross-workspace follow-up points for `/Users/zhdeng/stoa-frontend` and future native apps are explicit.

**Plans**: 0/1 plans complete

Plans:

- [ ] 169-01: Define frontend/native notification UX and token registration handoff.

### Phase 170: v4.9 Production Notification Release Gate And Live Smoke

**Goal**: Close v4.9 with focused verification, rollout evidence, and updated remaining-feature planning.
**Depends on**: Phase 169
**Requirements**: VERIFY-32
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
  2. Live WebSocket readiness, provider-backed email/push delivery, token registration, preferences, and handoff docs are verified.
  3. Release evidence records rollout state: local-only, configured, provider-ready, live-smoked, blocked, or deferred.
  4. Docs and feature-gap audit reflect completed v4.9 scope and next milestone recommendation.

**Plans**: 0/1 plans complete

Plans:

- [ ] 170-01: Verify v4.9 production notification release gate and live smoke.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 166 Production Notification Rollout Contract And Ownership | v4.9 | 1/1 | Complete    | 2026-06-14 |
| 167 Live WebSocket API Gateway Deployment Readiness | v4.9 | 1/1 | Complete    | 2026-06-14 |
| 168 Provider-Backed Email Digest And Push Delivery | v4.9 | 0/1 | Planned | - |
| 169 Frontend And Native Notification UX Handoff | v4.9 | 0/1 | Planned | - |
| 170 v4.9 Production Notification Release Gate And Live Smoke | v4.9 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PRODNOTIF-01 | Phase 166 | Complete |
| PRODNOTIF-02 | Phase 167 | Complete |
| PRODNOTIF-03 | Phase 168 | Planned |
| PRODNOTIF-04 | Phase 169 | Planned |
| VERIFY-32 | Phase 170 | Planned |

---
*Last updated: 2026-06-13 after selecting v4.9 production notification and native delivery rollout.*
