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
- [x] **v3.6 Full WebSocket Realtime Notifications** - Completed local release gate 2026-06-09.
- [x] **v3.7 AI Teacher Tools And Exercise Generation** - Completed local release gate 2026-06-09.
- [x] **v3.8 Full Curriculum Rollout** - Completed local release gate 2026-06-09.
- [x] **v3.9 Payment Provider Integration MVP** - Completed local release gate 2026-06-09.
- [x] **v4.0 Adaptive Learning Memory And Assignment** - Completed local backend release gate 2026-06-10.
- [x] **v4.1 Mobile And Multilingual Polish Foundation** - Completed local backend release gate 2026-06-11.

## v4.2 Production Notification Delivery Readiness

**v4.2 Production Notification Delivery Readiness** - Active planning.

Goal: promote local realtime notification foundations toward production-deliverable notification capability through production WebSocket delivery contracts, delivery operations, notification preferences, email digest readiness, and focused release evidence.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [x] **Phase 136: Production Notification Infrastructure Contract** - Define production WebSocket route/integration expectations, event/channel mapping, delivery state model, and backend versus infrastructure ownership. (completed 2026-06-11)
- [x] **Phase 137: WebSocket Delivery Operations And Preference APIs** - Add durable notification preference APIs and backend delivery decision/status behavior for realtime and fallback channels. (completed 2026-06-11)
- [ ] **Phase 138: Email Digest And Push Preference Readiness** - Add digest-ready selection/preview contracts and push-ready preference metadata without requiring live provider credentials.
- [ ] **Phase 139: v4.2 Functional Release Gate And Notification Delivery Audit** - Verify focused backend behavior, update docs, capture available deploy/build evidence, and record deferred notification surfaces.

## Phase Details

### Phase 136: Production Notification Infrastructure Contract

**Goal**: Define the production notification delivery contract, route/integration expectations, event/channel mapping, and release boundaries before code changes.
**Depends on**: v4.1 closeout and `stoa_docs` feature gap audit
**Requirements**: NOTIFYDEL-01
**Success Criteria** (what must be TRUE):

  1. Production WebSocket endpoint, API Gateway route expectations, environment variables, and fallback behavior are documented.
  2. Existing notification event types are mapped to in-app realtime, polling fallback, digest readiness, and push-ready preference channels.
  3. Delivery state fields needed for internal rollout and operator debugging are defined.
  4. Backend, CDK, frontend, and native ownership boundaries are explicit.

**Plans**: 0/1 plans complete

Plans:

- [x] 136-01: Define production notification delivery contract.

### Phase 137: WebSocket Delivery Operations And Preference APIs

**Goal**: Add durable notification preferences and backend delivery-decision/status behavior for production-oriented internal rollout.
**Depends on**: Phase 136
**Requirements**: NOTIFYDEL-02
**Success Criteria** (what must be TRUE):

  1. Users can read and update supported notification category/channel preferences.
  2. Existing in-product notification behavior remains enabled by default for existing users.
  3. Delivery helpers honor preferences when deciding realtime, in-app only, digest-ready, or push-ready handling.
  4. Bounded delivery health/status signals are available for admin/operator inspection.

**Plans**: 0/1 plans complete

Plans:

- [x] 137-01: Implement notification preferences and delivery operations.

### Phase 138: Email Digest And Push Preference Readiness

**Goal**: Prepare email digest and push preference capability without depending on production provider credentials during internal development.
**Depends on**: Phase 137
**Requirements**: NOTIFYDEL-03
**Success Criteria** (what must be TRUE):

  1. Backend can select or preview digest-ready notifications by recipient, category, and time window.
  2. Digest payload shape is metadata-safe and stable for future email templates.
  3. Push/native preference flags are stored and surfaced while provider delivery remains optional.
  4. No-provider fallback behavior is explicit and tested.

**Plans**: 0/1 plans complete

Plans:

- [ ] 138-01: Implement digest and push preference readiness.

### Phase 139: v4.2 Functional Release Gate And Notification Delivery Audit

**Goal**: Close v4.2 with focused functional verification and updated `stoa_docs` remaining-feature planning.
**Depends on**: Phase 138
**Requirements**: VERIFY-25
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant checks pass or isolate documented pre-existing failures.
  2. Requirements, roadmap, state, feature gap audit, and remaining-feature queue reflect completed v4.2 work.
  3. Available build/deploy/CDK/API/browser evidence is captured, or production verification deferral is explicit.
  4. v4.3 recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans complete

Plans:

- [ ] 139-01: Verify v4.2 and update release documentation.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 136 Production Notification Infrastructure Contract | v4.2 | 1/1 | Complete   | 2026-06-11 |
| 137 WebSocket Delivery Operations And Preference APIs | v4.2 | 1/1 | Complete   | 2026-06-11 |
| 138 Email Digest And Push Preference Readiness | v4.2 | 0/1 | Planned | - |
| 139 v4.2 Functional Release Gate And Notification Delivery Audit | v4.2 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIFYDEL-01 | Phase 136 | Complete |
| NOTIFYDEL-02 | Phase 137 | Complete |
| NOTIFYDEL-03 | Phase 138 | Planned |
| VERIFY-25 | Phase 139 | Planned |

---
*Last updated: 2026-06-11 after selecting v4.2 production notification delivery readiness*
