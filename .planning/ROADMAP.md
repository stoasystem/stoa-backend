# Roadmap: v5.6 Native Mobile App And Offline Push Readiness

**Status:** Active planning
**Created:** 2026-06-16
**Research:** `.planning/research/STOA_DOCS_REMAINING_FEATURES.md`

## Goal

Turn the completed mobile/API, notification, assignment automation, learning operations, and teacher-dispatch readiness work into a concrete native mobile app and offline/push implementation milestone.

## Purpose

STOA now has backend and frontend foundations for assignments, parent progress, teacher help-request dispatch, notifications, and mobile/localization governance. The remaining product gap is making those workflows practical in a native mobile client.

v5.6 answers: "What should a student, parent, teacher/tutor, and operator be able to do from the mobile app, what can work offline, and how do push notifications open the right workflow?"

## Implementation Strategy

- Reuse v5.0 native/mobile contracts, v4.9 notification/native delivery readiness, v5.3 controlled assignment automation, v5.4 learning operations frontend contracts, and v5.5 dispatch metadata.
- Define app shell, auth/session, role homes, API calls, push-token lifecycle, deep-link payloads, offline read-through cache boundaries, and release gate evidence.
- Prioritize internal product development. Keep live APNS/FCM credentials, app-store publication, final live payments, and external support provider activation as separate gated work.

## Phases

- [ ] **Phase 201: Native Mobile App And Offline Push Readiness Contract** - Define app roles, first screens, API contract, push/deep-link behavior, offline boundaries, and ownership.
- [ ] **Phase 202: Native App Shell Auth And Role Navigation** - Implement or specify real-auth app shell, role homes, navigation, locale preservation, and no-demo fallback behavior.
- [ ] **Phase 203: Native Push Token Deep Link And Notification Delivery** - Implement or specify push token lifecycle, notification event mapping, deep links, preferences, and no-provider fallback.
- [ ] **Phase 204: Offline Read Through Assignment Report And Help Request UX** - Implement or specify offline read-through cache behavior for assignments, reports/progress, and teacher-dispatch flows.
- [ ] **Phase 205: v5.6 Native Mobile Offline Push Release Gate** - Verify functionality/evidence/docs, update remaining-feature queue, and recommend v5.7.

## Phase Details

### Phase 201: Native Mobile App And Offline Push Readiness Contract

**Goal**: Define the native app product contract, app/client/backend boundaries, offline/push behavior, and phase implementation targets before mobile code expands.
**Depends on**: v5.0 native/mobile contracts, v4.9 notification readiness, v5.3 assignment automation, v5.4 learning operations, v5.5 teacher dispatch.
**Requirements**: NATIVEAPP-01
**Success Criteria** (what must be TRUE):

  1. Supported roles, first screens, role homes, required API calls, and session behavior are defined.
  2. Student assignment/report, parent progress, teacher dispatched queue, and admin/operator mobile flows are mapped.
  3. Push-token lifecycle, notification event types, and deep-link targets are defined.
  4. Offline read-through cache boundaries, stale indicators, reconnect refresh, and mutation limits are explicit.
  5. Backend/frontend/native ownership and follow-up implementation targets are concrete.

**Plans**: 0/1 plans complete

Plans:

- [ ] 201-01: Define native mobile app offline and push readiness contract.

### Phase 202: Native App Shell Auth And Role Navigation

**Goal**: Implement or specify the real-auth native app shell with role-aware navigation and backend-backed first screens.
**Depends on**: Phase 201
**Requirements**: NATIVEAPP-02
**Success Criteria** (what must be TRUE):

  1. Login/session refresh/logout flow targets real auth/session contracts.
  2. Student, parent, teacher/tutor, and admin homes are mapped to backend-backed routes.
  3. Locale/language preference behavior is preserved.
  4. Parent-critical and teacher-critical flows do not silently fall back to demo data.
  5. Focused checks cover route mapping and role navigation.

**Plans**: 0/1 plans created

Plans:

- [ ] 202-01: Build or specify native app shell auth and role navigation.

### Phase 203: Native Push Token Deep Link And Notification Delivery

**Goal**: Add or specify native push-token lifecycle and actionable deep-link delivery for assignments, teacher dispatch, reports, and operator events.
**Depends on**: Phase 202
**Requirements**: NATIVEAPP-03
**Success Criteria** (what must be TRUE):

  1. Push token registration/update/delete contract is implemented or mapped.
  2. Notification events map to deep-link targets for student, parent, teacher/tutor, and admin/operator flows.
  3. Provider-gated behavior is explicit when live APNS/FCM credentials are unavailable.
  4. Read/archive/preferences remain compatible with existing notification center behavior.
  5. Focused checks cover payload shape, token lifecycle, and no-provider fallback.

**Plans**: 0/1 plans created

Plans:

- [ ] 203-01: Build or specify native push token and deep-link notification delivery.

### Phase 204: Offline Read Through Assignment Report And Help Request UX

**Goal**: Make core mobile read workflows resilient to intermittent connectivity without unsafe offline mutation.
**Depends on**: Phase 203
**Requirements**: NATIVEAPP-04
**Success Criteria** (what must be TRUE):

  1. Student assignment list/detail has offline read-through boundaries and stale indicators.
  2. Parent progress/report summary has offline read-through boundaries and stale indicators.
  3. Teacher dispatched queue/detail has offline read-through boundaries and reconnect refresh.
  4. Unsafe mutations are blocked or queued only when idempotent and explicitly supported.
  5. Focused checks cover offline hydration, stale rendering, reconnect refresh, and role-safe data boundaries.

**Plans**: 0/1 plans created

Plans:

- [ ] 204-01: Build or specify offline read-through mobile UX for assignments, reports, and help requests.

### Phase 205: v5.6 Native Mobile Offline Push Release Gate

**Goal**: Close v5.6 with implementation/contract evidence, updated docs, remaining-feature alignment, and v5.7 recommendation.
**Depends on**: Phase 204
**Requirements**: VERIFY-39
**Success Criteria** (what must be TRUE):

  1. App shell, role navigation, push/deep links, offline read-through, and docs are verified.
  2. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.6 work.
  3. Release evidence identifies backend/frontend/native commits or explicitly records contract-only scope.
  4. Final audit records rollout state and known deferred items.
  5. Next milestone recommendation is updated from the remaining feature queue.

**Plans**: 0/1 plans created

Plans:

- [ ] 205-01: Verify v5.6 native mobile offline push release gate.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 201 Native Mobile App And Offline Push Readiness Contract | v5.6 | 0/1 | Active | - |
| 202 Native App Shell Auth And Role Navigation | v5.6 | 0/1 | Planned | - |
| 203 Native Push Token Deep Link And Notification Delivery | v5.6 | 0/1 | Planned | - |
| 204 Offline Read Through Assignment Report And Help Request UX | v5.6 | 0/1 | Planned | - |
| 205 v5.6 Native Mobile Offline Push Release Gate | v5.6 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NATIVEAPP-01 | Phase 201 | Planned |
| NATIVEAPP-02 | Phase 202 | Planned |
| NATIVEAPP-03 | Phase 203 | Planned |
| NATIVEAPP-04 | Phase 204 | Planned |
| VERIFY-39 | Phase 205 | Planned |

---
*Last updated: 2026-06-16 after starting v5.6 native mobile app and offline push readiness.*
