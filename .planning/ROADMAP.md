# Roadmap: v5.19 Native Mobile Push And Offline Client Implementation

**Status:** Active
**Created:** 2026-07-06
**Prior milestone:** v5.18 Warehouse BI Observability And Product Analytics Activation

## Goal

Implement a native mobile client path for STOA that proves authenticated student and parent journeys, Cognito-compatible session handling, native push registration/deep links, bounded offline/read-through behavior, localization QA, and internal release evidence.

## Why This Follows v5.18

v5.16 proved local product readiness, v5.17 separated external-provider readiness from product regressions, and v5.18 added aggregate observability and release evidence. v5.19 can now build a mobile client without hiding account, provider, billing, quota, or notification states behind generic forbidden/unauthorized screens.

## Product Purpose

- Students and parents can use the core STOA experience on mobile against real backend APIs.
- Mobile push and notification deep links are backed by existing notification contracts.
- Offline behavior is useful but bounded, read-only, and privacy-safe.
- Internal build/test evidence makes native readiness explicit without claiming app-store launch.

## Implementation Strategy

- Create the native client inside this repository as `mobile/` so the implementation is versioned with backend release evidence.
- Use Expo SDK 57, React Native 0.86, React 19.2, TypeScript, Expo Router, Amplify Auth, Expo Notifications, SecureStore, TanStack Query, and bounded local persistence contracts.
- Keep API access behind a single authenticated client and reuse existing backend route contracts.
- Preserve support-safe account-state messaging and no-demo-fallback behavior.
- Keep offline scope read-only and avoid caching sensitive learning, provider, billing, or token material.
- Close with static tests, evidence docs, and explicit blockers for live native credentials, EAS, and app-store launch.

## Phases

- [ ] **Phase 267: Native Mobile Stack And App Shell Contract** - Scaffold the native mobile workspace, app shell, navigation boundaries, environment contract, and no-demo-fallback policy.
- [ ] **Phase 268: Auth Session And Account State** - Implement Cognito-compatible auth/session wrappers, secure-storage boundaries, account-state mapping, and sign-out cleanup contracts.
- [ ] **Phase 269: Student And Parent Core Mobile Journeys** - Implement mobile data adapters and screen contracts for student and parent core journeys against real backend endpoints.
- [ ] **Phase 270: Native Push Deep Links And Offline Read-Through** - Implement notification token registration/revocation, deep-link routing, offline/read-through cache policy, and privacy guards.
- [ ] **Phase 271: v5.19 Native Mobile Release Gate** - Add tests/evidence, verify release boundaries, update docs/state/snapshots, and record remaining native-provider/app-store blockers.

## Phase Details

### Phase 267: Native Mobile Stack And App Shell Contract

**Goal**: Establish the native mobile client workspace, shell, routes, configuration model, and release-safe implementation contract.
**Requirements**: MOBILEAPP-01
**Success Criteria**:

1. `mobile/` contains an Expo SDK 57 TypeScript project scaffold with package, config, route shell, and app providers.
2. Mobile navigation defines student, parent, auth, notification, and blocked-state route boundaries.
3. Environment/config contract names API, Cognito, notification, build profile, and no-demo-fallback settings.
4. Stack decision and local build limitations are documented as release evidence.

### Phase 268: Auth Session And Account State

**Goal**: Implement native auth/session and account-state contracts that match STOA backend policy.
**Requirements**: MOBILEAPP-02
**Success Criteria**:

1. Auth service wraps Amplify session restore, token access, refresh-sensitive API calls, sign-in/register/verification/resend/sign-out, and typed auth errors.
2. Native storage policy avoids web localStorage token persistence and documents SecureStore boundaries.
3. Account-state mapper distinguishes verification, entitlement, billing, child-binding, quota, provider-blocked, unauthorized, and forbidden states.
4. Sign-out cleanup covers cached data and push-token revocation hooks.

### Phase 269: Student And Parent Core Mobile Journeys

**Goal**: Implement mobile adapters and screen contracts for core student and parent journeys.
**Requirements**: MOBILEAPP-03, MOBILEAPP-04
**Success Criteria**:

1. Student dashboard/practice/question/teacher-help/notification/history adapters use real backend endpoints and typed support-safe errors.
2. Parent dashboard/child summary/history/report/account-operations/billing adapters use real backend endpoints and typed support-safe errors.
3. Mobile screens expose loading, empty, blocked, stale, and error states without hidden demo data.
4. English/Chinese copy fixtures and viewport notes cover common text-fit risks.

### Phase 270: Native Push Deep Links And Offline Read-Through

**Goal**: Add push registration/deep-link contracts and bounded offline/read-through caching.
**Requirements**: MOBILEAPP-05, MOBILEAPP-06
**Success Criteria**:

1. Notification service models permission state, Expo token acquisition, backend push-token registration/revocation, foreground/background response handling, and read/archive actions.
2. Deep-link route mapping validates route targets after auth/role/account-state checks.
3. Offline cache contract limits persistence to approved read-only summaries with TTL, stale labels, and sign-out/user-switch clearing.
4. Privacy guards reject sensitive cache categories and quota/billing/question/teacher-help offline mutation by default.

### Phase 271: v5.19 Native Mobile Release Gate

**Goal**: Close v5.19 with verifiable native mobile evidence and explicit remaining blockers.
**Requirements**: VERIFY-53
**Success Criteria**:

1. Focused tests pass for mobile config, route contracts, auth/account-state mapping, push/deep-link contracts, and offline privacy policy.
2. Release evidence records internal build commands, local limitations, screenshots/placeholders, provider credentials needed, app-store prerequisites, and no-demo-fallback status.
3. Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
4. Remaining live-provider, native credential, EAS, app-store, and production rollout blockers are explicit.

## Future Milestone Directions

- **v5.20 Native Build Distribution And Device QA**: connect EAS credentials, produce device builds, run physical-device push smoke, and prepare store assets if release approval exists.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 267 Native Mobile Stack And App Shell Contract | v5.19 | 0/0 | Not Started | — |
| 268 Auth Session And Account State | v5.19 | 0/0 | Not Started | — |
| 269 Student And Parent Core Mobile Journeys | v5.19 | 0/0 | Not Started | — |
| 270 Native Push Deep Links And Offline Read-Through | v5.19 | 0/0 | Not Started | — |
| 271 v5.19 Native Mobile Release Gate | v5.19 | 0/0 | Not Started | — |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEAPP-01 | Phase 267 | Planned |
| MOBILEAPP-02 | Phase 268 | Planned |
| MOBILEAPP-03 | Phase 269 | Planned |
| MOBILEAPP-04 | Phase 269 | Planned |
| MOBILEAPP-05 | Phase 270 | Planned |
| MOBILEAPP-06 | Phase 270 | Planned |
| VERIFY-53 | Phase 271 | Planned |
