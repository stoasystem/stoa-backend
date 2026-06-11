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
- [x] **v4.2 Production Notification Delivery Readiness** - Completed local backend release gate 2026-06-11.

## v4.3 Frontend Mobile And Visual Localization Rollout

**v4.3 Frontend Mobile And Visual Localization Rollout** - Active planning.

Goal: use the `/Users/zhdeng/stoa-frontend` workspace to implement responsive mobile UX and visible English/German localization on core student, parent, tutor, and admin flows.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [x] **Phase 140: Frontend Workspace Contract And Mobile UAT Plan** - Confirm frontend workspace structure, route/API patterns, mobile flow targets, localization approach, and browser verification commands. (completed 2026-06-11)
- [ ] **Phase 141: Responsive Student Parent Tutor Core Flow Polish** - Implement mobile-responsive layouts and interaction polish for selected student, parent, and tutor workflows.
- [ ] **Phase 142: Visual Localization And Language Preference UI** - Add English/German preference UI and localized display copy for selected core flows using backend locale APIs.
- [ ] **Phase 143: v4.3 Browser Release Gate And Localization Audit** - Verify browser/mobile evidence, update docs, and record remaining frontend/native localization scope.

## Phase Details

### Phase 140: Frontend Workspace Contract And Mobile UAT Plan

**Goal**: Confirm the frontend workspace and define mobile/localization implementation targets before UI edits.
**Depends on**: v4.2 closeout and frontend workspace availability
**Requirements**: MOBILEUI-01
**Success Criteria** (what must be TRUE):

  1. `/Users/zhdeng/stoa-frontend` framework, route structure, API client pattern, and verification commands are documented.
  2. Student, parent, tutor, and admin mobile-critical flows are selected for v4.3.
  3. Mobile UAT criteria cover narrow viewports, touch targets, navigation, overflow, loading/empty/error states, and browser back/forward behavior.
  4. Localization UAT criteria cover language preference UI, persistence, translated copy, and fallback behavior.

**Plans**: 1/1 plans complete

Plans:

- [x] 140-01: Define frontend mobile and localization execution contract.

### Phase 141: Responsive Student Parent Tutor Core Flow Polish

**Goal**: Make selected core learning workflows usable on realistic mobile viewports.
**Depends on**: Phase 140
**Requirements**: MOBILEUI-02
**Success Criteria** (what must be TRUE):

  1. Student question/practice/assignment flows fit mobile viewports without horizontal overflow or clipped primary actions.
  2. Parent child overview, progress, and report views are scannable with clear loading/empty/error states.
  3. Tutor queue/detail and AI teacher tools remain usable on mobile-width screens.
  4. Targeted browser evidence captures representative mobile behavior.

**Plans**: 0/1 plans complete

Plans:

- [ ] 141-01: Implement responsive core flow polish.

### Phase 142: Visual Localization And Language Preference UI

**Goal**: Expose supported language preference controls and localized visible UI copy.
**Depends on**: Phase 141
**Requirements**: I18NUI-01
**Success Criteria** (what must be TRUE):

  1. English/German language preference controls use the v4.1 backend locale preference API.
  2. Selected visible UI copy is translated or routed through a translation map.
  3. Locale preference persists through refresh and reflects `/auth/me` state.
  4. Canonical backend values remain stable while display labels are localized separately.

**Plans**: 0/1 plans complete

Plans:

- [ ] 142-01: Implement visual localization and language preference UI.

### Phase 143: v4.3 Browser Release Gate And Localization Audit

**Goal**: Close v4.3 with frontend build/browser evidence and updated remaining-feature planning.
**Depends on**: Phase 142
**Requirements**: VERIFY-26
**Success Criteria** (what must be TRUE):

  1. Frontend lint/build and targeted browser checks pass or isolate documented pre-existing failures.
  2. Mobile viewport evidence covers representative student, parent, tutor, and admin flows.
  3. English/German language switching and fallback behavior are verified.
  4. Feature gap audit and next milestone recommendation are updated.

**Plans**: 0/1 plans complete

Plans:

- [ ] 143-01: Verify v4.3 and update release documentation.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 140 Frontend Workspace Contract And Mobile UAT Plan | v4.3 | 1/1 | Complete   | 2026-06-11 |
| 141 Responsive Student Parent Tutor Core Flow Polish | v4.3 | 0/1 | Planned | - |
| 142 Visual Localization And Language Preference UI | v4.3 | 0/1 | Planned | - |
| 143 v4.3 Browser Release Gate And Localization Audit | v4.3 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEUI-01 | Phase 140 | Complete |
| MOBILEUI-02 | Phase 141 | Planned |
| I18NUI-01 | Phase 142 | Planned |
| VERIFY-26 | Phase 143 | Planned |

---
*Last updated: 2026-06-11 after completing Phase 140 frontend mobile/localization contract*
