# Phase 171 Native Mobile And Localization Governance Contract

## Scope

v5.0 moves STOA from selected mobile/localization foundations into client-ready native/mobile and localization governance. The milestone should define and verify mobile API readiness, native notification/offline handoff, translation management, broad copy QA, locale coverage, and client release evidence.

## Ownership Boundaries

| Area | Owner | v5.0 Responsibility |
|------|-------|---------------------|
| Backend APIs | `stoa-backend` | Stable mobile-critical API contracts, locale preferences, notification token records, canonical value stability |
| Frontend web/PWA | `/Users/zhdeng/stoa-frontend` | Responsive mobile UX, locale UI, copy coverage, notification UX handoff |
| Native apps | Future native workspace | Native shell, push permission UX, token registration, offline cache, app-store release |
| Localization | Product/content owner plus implementation owner | Translation source of truth, review workflow, coverage reporting, copy QA |
| Release | Product/engineering owner | Contract-ready/frontend-ready/native-ready evidence and deferred scope tracking |

## Mobile-Critical Flows

- Auth/session: login, refresh, logout, current user, locale preference.
- Student: learning dashboard, question submission, AI answer, teacher takeover state, curriculum/progress, assignments, notifications.
- Parent: children list, child summary/history/report, billing/subscription status, notifications.
- Tutor/teacher: queue, takeover, reply, AI teacher tools, assignments, notifications.
- Admin: moderation, report operations, billing/support/notification operations, release evidence surfaces.

## Localization Governance

Required policy:

- Supported locales start with `en` and `de`.
- Canonical API enum/status values remain stable and are not localized at the API contract layer.
- Display copy uses translation keys with owner, status, locale, and review metadata.
- Missing keys should fall back predictably and produce coverage evidence.
- Copy QA covers critical student, parent, tutor, admin, billing, support, notification, curriculum, and AI teacher tool surfaces.
- RTL and additional locales are readiness/deferred scope unless selected later.

## Native Notification And Offline Handoff

Native/mobile handoff must cover:

- Push token registration with platform, token reference/hash, lifecycle state, last seen timestamp, and revocation.
- Permission denied, token missing, provider disabled, opted out, and send failed states.
- Notification center live/fallback behavior, unread/read/archive, digest/push preferences, reconnect/offline behavior.
- Offline/read-through expectations for learning history, reports, assignments, billing, support status, and notifications.

## Mobile API Readiness

Mobile API handoff should document:

- Route path, method, auth role, response shape, loading/empty/error states, offline behavior, and cache expectations.
- Critical route ownership and whether current backend behavior is ready, needs a backend change, or is client-only.
- No hidden demo fallback for parent-critical, billing, support, and notification flows.

## Rollout States

- `contract-ready`: v5.0 contracts and handoff docs are complete.
- `frontend-ready`: responsive web/PWA implementation and coverage are ready.
- `native-ready`: native workspace has implemented shell, token, offline, and locale requirements.
- `blocked`: required workspace/provider/content/release prerequisite is absent.
- `deferred`: backend/client contract is complete but native app release remains future scope.

## Implementation Handoff

Phase 172 should define mobile API readiness and client handoff.

Phase 173 should define native notification token and offline state handoff.

Phase 174 should define localization governance, translation QA, and locale coverage.

Phase 175 should verify v5.0, record rollout state, and update the remaining-feature queue.
