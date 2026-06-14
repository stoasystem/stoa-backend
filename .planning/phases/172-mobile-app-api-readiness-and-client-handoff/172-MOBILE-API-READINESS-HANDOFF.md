# Phase 172 Mobile API Readiness And Client Handoff

**Milestone:** v5.0 Native Mobile And Full Localization Governance
**Requirement:** MOBILELOC-02
**Status:** Accepted for implementation by later phases
**Date:** 2026-06-14

## Scope

This handoff defines how mobile/PWA and future native clients should consume the existing STOA backend API for core flows. The backend already exposes the required route families; Phase 172 documents readiness, client states, cache/offline expectations, and where frontend/native implementation must continue.

## Readiness Legend

| Status | Meaning |
|--------|---------|
| `ready` | Backend route exists and can be consumed by mobile clients with current contract. |
| `client-work-needed` | Backend route exists; frontend/PWA or native client needs state handling, layout, or integration work. |
| `native-work-needed` | Backend route exists; platform-specific native implementation is required. |
| `backend-gap` | Backend behavior needs a future change before clients can rely on it. |
| `deferred` | Useful capability, but outside v5.0 backend/client handoff scope. |

## Route Contract Inventory

| Surface | Routes | Auth/ownership | Mobile state contract | Readiness | Verification target |
|---------|--------|----------------|-----------------------|-----------|---------------------|
| Auth/session | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | Authenticated user; role resolved from Cognito/profile | loading, invalid credentials, expired session, unauthorized, refreshed user, role mismatch | `ready` | Route registration and `auth.py` response models |
| Locale preference | `PATCH /auth/me/preferences/locale`, `GET /auth/me` | Authenticated user updates only own profile preference | saving, unsupported locale validation, saved, failed, stale local language until refetch | `ready` | `preferredLocale` / `effectiveLocale` in `auth.py`; frontend `authApi.ts` and locale hook |
| Student profile/summary | `GET/PATCH /students/me/profile`, `GET /students/{student_id}/summary`, `GET /students/{student_id}/learning-profile`, `GET /students/{student_id}/questions` | Student self routes; role/ownership checks must be preserved for ID routes | loading, empty history, unauthorized, unavailable, stale/offline read-through | `ready` with client checks | `students.py`, student frontend services |
| Questions and teacher help | `POST /questions`, `GET /questions/{id}`, `POST /questions/{id}/request-teacher`, `POST /questions/{id}/feedback` | Student owns question; teacher escalation state is backend-authored | submitting, OCR/AI pending, answered, teacher requested, failed, offline cannot submit | `ready` | `questions.py`; no hidden fallback for submissions |
| Conversations | `GET/POST /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/messages`, `POST /conversations/{id}/messages/stream` | Authenticated conversation owner | list loading/empty, message sending, buffered stream fallback, offline read-only cache | `client-work-needed` | `conversations.py`; API Gateway buffering note |
| Practice/curriculum | `/practice/subjects`, `/practice/overview`, `/practice/curriculum/*`, lesson/challenge/progress routes | Authenticated user; progress writes tied to current student | catalog loading, empty curriculum, lesson unavailable, progress stale/offline, answer submit failure | `ready` with client checks | `practice.py`; frontend practice services |
| Adaptive learning/assignments | `/adaptive/students/me/*`, `/adaptive/students/{id}/*`, `/adaptive/assignments/*`, `/adaptive/parents/me/children/{id}/progress` | Student self, tutor/admin assignment management, parent child ownership | recommendation empty, assignment not started/in progress/complete/skipped, stale progress | `ready` | `adaptive.py`; route ownership and state labels |
| Parent child/report flows | `/parents/me/children`, `/parents/me/children/{child_id}/summary`, `/history`, `/report`, `/reports/{week}`, `/learning-profile` | Parent ownership must be verified before child data reads | loading, no children, missing report, pending report, failed report, unauthorized child, offline read-through | `ready`; strict no demo fallback | `parents.py`; frontend parent services already moved to real routes |
| Parent billing | `/parents/me/subscription`, `/subscription/billing`, `/subscription/checkout`, `/subscription/requests` | Authenticated parent owns billing/subscription view | loading, trial/manual/provider state, checkout unavailable, provider disabled, stale/offline read-only | `client-work-needed` | `parents.py`; frontend billing service still uses demo fallback |
| Tutor queue/tools | `/tutors/me/help-requests`, detail/update/notes, `/tutors/ai-tools/*`, `/teachers/*` legacy takeover/reply | Tutor/teacher role; request lifecycle authorization | queue loading/empty, stale filters, takeover/reply failure, draft lifecycle states, offline read-only | `client-work-needed` | `tutors.py`, `teachers.py`; frontend tutor services still use demo fallback |
| Notifications | `/notifications`, `/preferences`, `/digest-preview`, `/digest-send`, `/push-tokens`, read/archive | Authenticated user; durable notification state is authoritative | loading, empty, unread/read/archive, provider disabled, permission denied, reconnecting, offline fallback | `client-work-needed`; `native-work-needed` for push capture | `notifications.py`; Phase 173 owns deeper handoff |
| Admin operations | `/admin/users`, `/admin/stats`, moderation, curriculum, billing, report/support, notification delivery status | Admin role; metadata-only privacy boundaries | loading, empty, filters, unavailable, mutation refused, provider blocked, no raw secrets/tokens | `client-work-needed`; dense surfaces desktop-first unless documented | `admin.py`, admin frontend services |
| Support status | `/admin/reports/support-handoff-*` plus provider/status views | Admin/operator role; customer-facing native status is future scope | queue loading, delivery status, retry eligibility, provider blocked, offline read-only | `client-work-needed` for admin; customer support status deferred | `admin.py`; Phase 175 release evidence |

## Client State Rules

Every mobile-critical flow should define these states:

- `loading`: initial request or refetch in progress.
- `empty`: authenticated and authorized, but no records exist.
- `unavailable`: backend/provider/config dependency unavailable; show retry/manual fallback where useful.
- `unauthorized`: session or ownership failure; do not show stale private data.
- `stale/offline`: read-through cached data may be shown with clear stale indicator; mutations are disabled or queued only by explicit native policy.
- `refreshed`: successful refetch reconciles cache and clears stale indicators.

Critical flows must not hide backend failures with demo fallback:

- parent child/report/progress flows
- billing/subscription flows
- support/operations handoff states
- notification center/preferences/digest/push states
- auth/session/locale preference flows
- student learning and assignment flows

## Frontend/PWA Reuse Points

| Area | Existing frontend anchor | Handoff |
|------|--------------------------|---------|
| App shell and navigation | `src/layouts/AppLayout.tsx`, route config, mobile bottom navigation | Reuse for PWA/mobile web; native shell should mirror role-critical destinations without duplicating backend assumptions. |
| Auth/session | `src/services/auth/authApi.ts`, auth store/hooks, `AuthBootstrap` | Keep `/auth/me` as refresh source; locale changes should refetch/sync user state. |
| Localization | `src/i18n`, `LanguageSwitcher`, `useUpdateLocalePreferenceMutation`, `useCurrentUserQuery` | Phase 174 should govern catalog coverage and missing-key handling. |
| Notifications | `NotificationCenter`, notification hooks/services, realtime notification service | Phase 173 should add native token/offline/deep-link rules; frontend should remove demo fallback for critical notification states. |
| Parent/student/tutor pages | Existing services/pages under `src/pages` and `src/services` | Preserve explicit loading/error/empty states; remove hidden demo fallback from critical mobile paths before release. |
| Billing/support/admin | Existing services import `withDemoFallback` in several places | Treat fallback as a release blocker for critical mobile/client-ready flows unless explicitly demo-only. |

## Future Native Responsibilities

Native apps own:

- secure token storage and refresh-token handling according to platform policy
- platform push permission request timing and status display
- raw push token capture from APNS/FCM and registration with backend
- local cache implementation for read-through offline behavior
- deep-link/tap routing from notification payloads to authenticated screens
- app-store release evidence, crash/log privacy, and platform accessibility checks

Native apps should not introduce a separate backend API surface unless a later phase records a concrete backend gap.

## Follow-Up Targets

- Phase 173: specify native notification token, permission, reconnect, offline, and deep-link behavior in detail.
- Phase 174: audit translation catalog and English/German coverage for critical mobile surfaces.
- Phase 175: verify no-demo-fallback and contract coverage evidence; classify final rollout state.
- Future frontend/native work: remove hidden demo fallback from critical mobile flows and implement native offline/cache behavior.
