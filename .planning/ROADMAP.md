# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05.
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05.
- [x] **v1.9 Recovery Resume And Support Evidence Packages** - Shipped 2026-06-05.
- [x] **v2.0 Controlled Report Editing MVP** - Shipped 2026-06-05.
- [x] **v2.1 Report Artifact Versioning And Safe Edit Preview** - Shipped 2026-06-06.
- [x] **v2.2 Report Artifact Rollback And Safe Fixture Verification** - Shipped 2026-06-06.
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07.
- [x] **v2.6 Audit Retention And Immutable Evidence Readiness** - Shipped 2026-06-07.
- [x] **v2.7 Immutable Audit Storage And Legal Hold Foundation** - Shipped 2026-06-07.
- [x] **v2.8 CDK-Managed Immutable Evidence Storage Deployment** - Shipped 2026-06-07.
- [x] **v2.9 Retention Governance And Legal Hold Operations** - Complete local-only 2026-06-07; production verification closed by v3.0.
- [x] **v3.0 STOA Docs Gap Closeout And Account Intake Hardening** - Shipped 2026-06-08.
- [x] **v3.1 Teacher Reply Quality And SLA Operations** - Shipped 2026-06-08.
- [x] **v3.2 Content Moderation And Internal Operations** - Shipped 2026-06-08.
- [x] **v3.3 Subscription Operations MVP** - Completed local release gate 2026-06-08.
- [x] **v3.4 Learning Expansion Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.5 Realtime And Teacher Assistance Foundation** - Completed local release gate 2026-06-08.

## Current Milestone

**v3.6 Full WebSocket Realtime Notifications** - Active.

Goal: turn the v3.5 notification foundation into full authenticated WebSocket realtime delivery for core learning and operations events.

## Phases

| Phase | Name | Status | Requirement |
|-------|------|--------|-------------|
| 112 | Full WebSocket Transport Contract And Infra Readiness | Complete | WS-01 |
| 113 | Backend WebSocket Connection And Event Delivery | Planned | WS-02 |
| 114 | Realtime Notification Client And UX | Planned | UI-21 |
| 115 | v3.6 Functional Release Gate And Realtime Audit | Planned | VERIFY-19 |

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 112 | v3.6 | 1/1 | Complete | 2026-06-09 |
| 113 | v3.6 | 0/1 | Planned | - |
| 114 | v3.6 | 0/1 | Planned | - |
| 115 | v3.6 | 0/1 | Planned | - |

## Phase Details

### Phase 112: Full WebSocket Transport Contract And Infra Readiness

**Goal:** Define the WebSocket transport contract, authenticated connection lifecycle, authorization model, fallback behavior, and infrastructure/CDK readiness before backend and frontend implementation.

**Requirement:** WS-01
**Plans:** 1/1 plans complete

**Success Criteria**:
1. Contract defines connect, authenticate, subscribe, heartbeat, reconnect, disconnect, and stale connection cleanup behavior.
2. Contract defines event envelopes for existing notification events and per-role channel/target authorization.
3. Contract defines supported realtime event categories for teacher, moderation, subscription, learning profile, and system notice workflows.
4. Fallback behavior to polling/notification center is explicit when WebSocket transport is unavailable.
5. Infrastructure readiness compares API Gateway WebSocket, Lambda/API shape, DynamoDB connection records, and required CDK changes.

### Phase 113: Backend WebSocket Connection And Event Delivery

**Goal:** Implement authenticated backend WebSocket connection storage, subscription authorization, event fanout, delivery recording, disconnect cleanup, and stale connection cleanup.

**Requirement:** WS-02
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Backend stores active connection records with user id, role, subscribed channels, heartbeat/update timestamps, and expiry.
2. Connection and subscription requests are authenticated through the existing Cognito/JWT model or an explicitly approved equivalent.
3. Existing notification events publish to active authorized WebSocket connections and record delivery attempts/results.
4. Disconnect and stale connection cleanup keep connection state bounded and fallback-safe.
5. Focused tests cover lifecycle, authorization, fanout, stale cleanup, and persistent notification fallback behavior.

### Phase 114: Realtime Notification Client And UX

**Goal:** Add frontend realtime notification client behavior across role shells while preserving the existing notification center and polling fallback.

**Requirement:** UI-21
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Frontend establishes an authenticated WebSocket session after login when realtime transport is enabled.
2. Client handles reconnect, heartbeat, offline/unavailable state, and fallback to existing notification list polling.
3. Student, parent, tutor, and admin shells show realtime notification count/list updates for supported events.
4. Tutor workflows receive teacher-session events without page refresh where supported.
5. Targeted browser verification proves realtime and fallback UX with local or safe test fixtures.

### Phase 115: Functional Release Gate And Realtime Audit

**Goal:** Close v3.6 with focused functional evidence, infrastructure/deploy evidence where needed, and updated Phase 2 gap tracking.

**Requirement:** VERIFY-19
**Plans:** 0/1 plans complete

**Success Criteria**:
1. Backend and frontend quality gates relevant to WebSocket delivery pass.
2. CDK/diff/deploy evidence is recorded if infrastructure changes are required.
3. Gap audit marks full WebSocket realtime notifications active or closed and records residual push/email/native notification scope.
4. Final audit lists remaining Phase 2 product expansions including Stripe/TWINT, curriculum rollout, richer AI teacher tools, mobile/multilingual polish, and support integrations.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| WS-01 | Phase 112 | Complete |
| WS-02 | Phase 113 | Planned |
| UI-21 | Phase 114 | Planned |
| VERIFY-19 | Phase 115 | Planned |

---
*Last updated: 2026-06-08 after planning v3.6*
