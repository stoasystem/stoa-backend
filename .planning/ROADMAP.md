# Roadmap: v5.0 Native Mobile And Full Localization Governance

**Status:** Active planning
**Created:** 2026-06-14
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Move STOA beyond selected responsive frontend and backend locale foundations into native/mobile rollout readiness and full localization governance: mobile app/API handoff, native notification token/offline behavior, translation management, broad copy QA, locale coverage, and client release evidence.

## Execution Bias

Build mobile/localization readiness directly. Keep verification focused on route contracts, client handoff, localization correctness, token/offline behavior, and release evidence. Do not spend this milestone on broad unrelated security/compliance testing during internal development.

## Phases

- [x] **Phase 171: Native Mobile And Localization Governance Contract** - Define backend/frontend/native/localization ownership, mobile-critical flows, supported locales, translation governance, push/offline handoff, and release evidence.
- [x] **Phase 172: Mobile App API Readiness And Client Handoff** - Document and stabilize mobile-critical API contracts, client state behavior, app shell expectations, and frontend/native integration points.
- [ ] **Phase 173: Native Notification Token And Offline State Handoff** - Define native push token registration, notification UX, offline/read-through behavior, permission states, and mobile fallback contracts.
- [ ] **Phase 174: Localization Governance Translation QA And Locale Coverage** - Define translation catalog workflow, coverage reporting, copy QA, missing-key behavior, RTL/future-locale readiness, and critical-flow locale coverage.
- [ ] **Phase 175: v5.0 Native Mobile Localization Release Gate And Handoff** - Verify v5.0 docs/contracts/evidence, record rollout state, and select the next feature milestone.

## Phase Details

### Phase 171: Native Mobile And Localization Governance Contract

**Goal**: Define the v5.0 mobile/localization contract before implementation expands into client/native work.
**Depends on**: v4.1 mobile/multilingual backend foundation, v4.3 selected frontend localization rollout, v4.9 notification handoff, and `stoa_docs` remaining-feature audit
**Requirements**: MOBILELOC-01
**Success Criteria** (what must be TRUE):

  1. Backend, frontend, native, localization, content, and release ownership boundaries are documented.
  2. Mobile-critical user flows for student, parent, tutor, and admin roles are identified.
  3. Supported locales, fallback policy, translation source of truth, key naming, copy ownership, and review workflow are defined.
  4. Native push/offline/deep-link handoff expectations reuse v4.9 notification readiness.
  5. Phase 172 through Phase 175 implementation targets are concrete.

**Plans**: 1/1 plans complete

Plans:

- [x] 171-01: Define native mobile and localization governance contract.

### Phase 172: Mobile App API Readiness And Client Handoff

**Goal**: Prepare mobile/native clients to consume stable backend/API and frontend contracts for core flows.
**Depends on**: Phase 171
**Requirements**: MOBILELOC-02
**Success Criteria** (what must be TRUE):

  1. Mobile-critical route contracts are documented for auth/session, profile/locale, student learning, parent reports, tutor tools, notifications, billing, and support.
  2. Loading, empty, error, offline, and no-demo-fallback behavior is defined for mobile consumption.
  3. `/Users/zhdeng/stoa-frontend` reuse points and future native integration points are explicit.
  4. App shell expectations cover navigation, role switching, session refresh, and locale refresh.

**Plans**: 1/1 plans complete

Plans:

- [x] 172-01: Define mobile API readiness and client handoff.

### Phase 173: Native Notification Token And Offline State Handoff

**Goal**: Make native/mobile notification and offline behavior implementable by clients.
**Depends on**: Phase 172
**Requirements**: MOBILELOC-03
**Success Criteria** (what must be TRUE):

  1. Native push token registration handoff covers platform, token reference/hash, lifecycle state, last seen timestamp, revocation, and preferences.
  2. Notification UX covers live, fallback, unread/read/archive, digest/push preferences, reconnect, and permission-denied states.
  3. Offline/read-through states are documented for notification center, learning history, reports, assignments, billing, and support.
  4. Existing backend/frontend support versus client/native follow-up work is explicit.

**Plans**: 0/1 plans complete

Plans:

- [ ] 173-01: Define native notification token and offline state handoff.

### Phase 174: Localization Governance Translation QA And Locale Coverage

**Goal**: Turn localization into a governed product workflow with clear coverage and QA.
**Depends on**: Phase 173
**Requirements**: MOBILELOC-04
**Success Criteria** (what must be TRUE):

  1. Translation catalog ownership, key lifecycle, review states, missing-key behavior, fallback behavior, and coverage reporting are defined.
  2. English/German critical-flow coverage is audited and gaps become implementation tasks.
  3. Broad copy QA covers student, parent, tutor, admin, billing, notification, support, curriculum, and AI teacher tool surfaces.
  4. RTL and future-locale readiness are scoped with implemented versus deferred work.

**Plans**: 0/1 plans complete

Plans:

- [ ] 174-01: Define localization governance, translation QA, and locale coverage.

### Phase 175: v5.0 Native Mobile Localization Release Gate And Handoff

**Goal**: Close v5.0 with focused verification, handoff evidence, and updated remaining-feature planning.
**Depends on**: Phase 174
**Requirements**: VERIFY-33
**Success Criteria** (what must be TRUE):

  1. Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
  2. Mobile API readiness, native notification/offline handoff, localization governance, and translation QA are verified.
  3. Release evidence records rollout state: contract-ready, frontend-ready, native-ready, blocked, or deferred.
  4. Docs and feature-gap audit reflect completed v5.0 scope and next milestone recommendation.

**Plans**: 0/1 plans complete

Plans:

- [ ] 175-01: Verify v5.0 native mobile localization release gate and handoff.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 171 Native Mobile And Localization Governance Contract | v5.0 | 1/1 | Complete | 2026-06-14 |
| 172 Mobile App API Readiness And Client Handoff | v5.0 | 1/1 | Complete | 2026-06-14 |
| 173 Native Notification Token And Offline State Handoff | v5.0 | 0/1 | Planned | - |
| 174 Localization Governance Translation QA And Locale Coverage | v5.0 | 0/1 | Planned | - |
| 175 v5.0 Native Mobile Localization Release Gate And Handoff | v5.0 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILELOC-01 | Phase 171 | Complete |
| MOBILELOC-02 | Phase 172 | Complete |
| MOBILELOC-03 | Phase 173 | Planned |
| MOBILELOC-04 | Phase 174 | Planned |
| VERIFY-33 | Phase 175 | Planned |

---
*Last updated: 2026-06-14 after completing Phase 172 mobile API readiness and client handoff.*
