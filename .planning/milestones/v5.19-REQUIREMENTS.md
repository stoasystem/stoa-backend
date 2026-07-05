# Requirements: v5.19 Native Mobile Push And Offline Client Implementation

**Milestone:** v5.19
**Status:** Approved
**Created:** 2026-07-06
**Prior milestone:** v5.18 Warehouse BI Observability And Product Analytics Activation

## Purpose

Deliver a real native mobile implementation path for STOA after backend/web readiness, provider-state evidence, and BI observability are in place. v5.19 should prove authenticated student and parent mobile journeys, native push registration, notification deep links, bounded offline/read-through behavior, localization QA, and internal release evidence without claiming public app-store launch.

## Requirements

### MOBILEAPP-01 Native Stack And App Shell

Acceptance criteria:

- Native stack decision is documented around Expo SDK 57, React Native 0.86, React 19.2, TypeScript, Expo Router, EAS Build, Amplify Auth, Expo Notifications, SecureStore, and bounded offline persistence.
- Native app shell supports role-aware student/parent routing, authenticated route guards, loading/error states, and mobile-safe navigation.
- Environment configuration covers API base URL, Cognito identifiers, notification project/provider identifiers, release channel/build profile, and no-demo-fallback behavior.
- App shell consumes real backend contracts and does not add hidden demo data, mock account states, or parallel entitlement/notification models.

### MOBILEAPP-02 Auth Session And Account State

Acceptance criteria:

- Registration, sign-in, email verification, resend-code, session restore, token refresh, and sign-out flows are implemented with Cognito-compatible Amplify Auth behavior.
- Native storage avoids web localStorage token persistence and uses SecureStore only within documented small-secret/session-adjacent boundaries.
- Mobile account-state surfaces distinguish verification, expired session, entitlement, billing, child binding, quota, provider-blocked, unauthorized, and forbidden states with support-safe messages.
- Sign-out or user switch clears persisted query/offline data, session-adjacent metadata, and revokes push token registration when possible.

### MOBILEAPP-03 Student Core Mobile Journeys

Acceptance criteria:

- Student mobile dashboard loads real backend account, curriculum/progress, quota, notification, and practice summary state.
- Student practice/question flows cover curriculum read, lesson/challenge entry, question submission, quota/paid-access state, teacher-help state, and backend error mapping.
- Student notifications and learning-history summaries are reachable from mobile navigation and from authenticated deep links.
- Student mobile UI is verified for common phone sizes, loading/empty/error states, and English/Chinese text fit.

### MOBILEAPP-04 Parent Core Mobile Journeys

Acceptance criteria:

- Parent mobile dashboard loads real backend subscription/account-operation, child summary, notification, and support-safe state.
- Parent child detail flows cover child summary, history, report, billing/subscription state, and account operation explanations.
- Parent blocked/pending/provider-failure states avoid generic `Forbidden`/`Unauthorized` copy when backend has a more specific support-safe explanation.
- Parent mobile UI is verified for common phone sizes, loading/empty/error states, and English/Chinese text fit.

### MOBILEAPP-05 Native Push And Notification Deep Links

Acceptance criteria:

- Mobile app requests notification permission at an intentional product moment and records denied, unavailable, and provider-blocked states clearly.
- Push token registration and revocation call the existing backend notification APIs with provider/device metadata and no raw token leakage in support-facing output.
- Foreground/background notification handling supports notification list refresh, read/archive actions, and authenticated deep links into student or parent surfaces.
- Deep-link route targets are validated after session restore, role checks, and account-state checks; notification payloads are not trusted as authorization.

### MOBILEAPP-06 Offline Read-Through And Privacy Boundaries

Acceptance criteria:

- Offline/read-through cache is limited to approved read-only summary surfaces with documented TTL, stale-state UI, and refresh behavior.
- Quota-consuming actions, billing/account operations, teacher-help mutations, and question submission remain online-only unless a later quota-safe mutation design is approved.
- Cached data excludes raw prompts, answers, tutoring transcripts, generated report artifacts, provider payloads, billing payloads, Cognito token material, secrets, and private object keys.
- Cache clearing is tested for sign-out, user switch, and account-state changes.

### VERIFY-53 Native Mobile Release Gate

Acceptance criteria:

- Mobile tests, screenshots, internal build evidence, provider/app-store prerequisites, and known limitations are recorded.
- Release evidence covers auth/session, student journeys, parent journeys, push registration/deep links, offline/read-through behavior, localization/text-fit, and no-demo-fallback behavior.
- Roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
- Remaining live-provider, app-store, native credential, and production rollout blockers are explicit.

## Out of Scope

- Public App Store or Play Store launch without separate release approval.
- Native payments, in-app purchases, or app-store commerce policy work unless explicitly scoped.
- Full offline mutation for quota-consuming, billing, account-operation, teacher-help, or question-submission flows.
- Admin/tutor native workflows beyond smoke/support evidence.
- Parallel mobile-only entitlement, billing, quota, support, or notification models.
- Raw learning-content analytics, prompt/answer caches, report artifact caches, Cognito token dumps, provider payload dumps, or billing payload dumps.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEAPP-01 | Phase 267 | Complete |
| MOBILEAPP-02 | Phase 268 | Complete |
| MOBILEAPP-03 | Phase 269 | Planned |
| MOBILEAPP-04 | Phase 269 | Planned |
| MOBILEAPP-05 | Phase 270 | Planned |
| MOBILEAPP-06 | Phase 270 | Planned |
| VERIFY-53 | Phase 271 | Planned |
