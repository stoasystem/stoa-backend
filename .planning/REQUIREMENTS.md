# Requirements: v5.0 Native Mobile And Full Localization Governance

**Milestone:** v5.0
**Status:** Active planning
**Created:** 2026-06-14

## Goal

Move beyond selected responsive frontend and backend locale foundations into a concrete native/mobile rollout and full localization governance plan. v5.0 focuses on mobile app/API readiness, native notification token and offline-state handoff, translation management, broad copy QA, locale coverage, and release evidence for client implementation.

This is an internal development milestone. Prioritize functional mobile/localization build readiness and operator workflows. Keep checks focused on route contracts, localization correctness, token/offline behavior, and release handoff; avoid broad unrelated security/compliance work.

## Requirements

### MOBILELOC-01 Native Mobile And Localization Governance Contract

Implementers have a concrete v5.0 contract before client/native implementation starts.

Acceptance criteria:

- Contract identifies backend, frontend, native, localization, content, and release ownership boundaries.
- Contract defines mobile-critical user flows for student, parent, tutor, and admin roles.
- Contract defines supported locales, fallback policy, translation source of truth, key naming, copy ownership, and review workflow.
- Contract defines native push/offline/deep-link handoff expectations using v4.9 notification readiness.
- Contract defines release evidence, client handoff, and deferred native app work that remains outside this backend workspace.

### MOBILELOC-02 Mobile App API Readiness And Client Handoff

Mobile/native clients have a stable backend/API and frontend handoff for core user flows.

Acceptance criteria:

- Route contract identifies mobile-critical APIs for auth/session, profile/locale, student learning, parent children/reports, tutor queue/tools, notifications, billing, and support status.
- API response shapes are documented for mobile consumption, including loading/empty/error/offline fallback states.
- Client handoff identifies `/Users/zhdeng/stoa-frontend` reuse points and future native app integration points.
- Mobile app shell expectations cover navigation, role switching, session refresh, locale refresh, and no hidden demo fallback for critical flows.
- Tests or focused checks cover route-contract stability where backend behavior is touched.

### MOBILELOC-03 Native Notification Token And Offline State Handoff

Native/mobile notification and offline behavior has an implementable integration path.

Acceptance criteria:

- Native push token registration handoff covers platform, token reference/hash, lifecycle state, last seen timestamp, revocation, and preference mapping.
- Mobile notification UX handoff covers live, fallback, unread/read/archive, digest/push preference, reconnect, and permission-denied states.
- Offline/read-through behavior is documented for notification center, learning history, reports, assignments, billing, and support status.
- Backend/frontend handoff identifies which states are already supported and which require client/native implementation.
- Release evidence captures push-token/offline contract coverage without requiring real app-store/native release.

### MOBILELOC-04 Localization Governance Translation QA And Locale Coverage

Localization is governed as a product workflow rather than ad hoc copy changes.

Acceptance criteria:

- Translation catalog ownership, key lifecycle, review states, missing-key behavior, fallback behavior, and locale coverage reporting are defined.
- English/German coverage is audited for critical user flows and gaps are turned into implementation tasks.
- Broad copy QA workflow covers student, parent, tutor, admin, billing, notification, support, curriculum, and AI teacher tool surfaces.
- RTL and future-locale readiness are explicitly scoped with what is implemented now versus deferred.
- Tests or focused checks cover canonical API values staying stable while localized display text changes.

### VERIFY-33 v5.0 Native Mobile Localization Release Gate And Handoff

v5.0 closes with client-ready evidence and updated remaining-feature planning.

Acceptance criteria:

- Focused backend/frontend contract checks pass or isolate documented pre-existing failures.
- Mobile API readiness, native notification/offline handoff, localization governance, translation QA, and release handoff are verified.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v5.0 work.
- Final audit records rollout state: contract-ready, frontend-ready, native-ready, blocked, or deferred.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Real native app implementation and app-store release workflow.
- Final live payment activation operations once external provider prerequisites are ready.
- Real external support provider and CRM/customer transport activation after approved provider prerequisites are ready.
- Rich curriculum editor UI and production content migration.
- Long-term adaptive sequencing, autonomous tutoring, and warehouse-backed analytics.

## Out of Scope

- Building a full native app binary inside the backend workspace.
- Broad redesign of every frontend surface.
- Marketing localization or campaign automation.
- Unapproved live push/email sends to real users.
- Final payment/support external activation.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILELOC-01 | Phase 171 | Complete |
| MOBILELOC-02 | Phase 172 | Complete |
| MOBILELOC-03 | Phase 173 | Planned |
| MOBILELOC-04 | Phase 174 | Planned |
| VERIFY-33 | Phase 175 | Planned |
