# Phase 172: Mobile App API Readiness And Client Handoff - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 172 turns the accepted Phase 171 governance contract into a mobile API readiness and client handoff inventory. It documents mobile-critical backend routes, expected client states, frontend/PWA reuse points in `/Users/zhdeng/stoa-frontend`, and future native app responsibilities. It should not build a native app binary or redesign frontend surfaces in this backend workspace.

</domain>

<decisions>
## Implementation Decisions

### Route Contract Scope
- Inventory all mobile-critical surfaces from Phase 171: auth/profile, student, parent, tutor, notifications, billing, support, curriculum, and admin status surfaces where mobile readability matters.
- Each route entry should include method/path, auth role, ownership boundary, key response fields, loading/empty/error/offline states, cache/refetch policy, readiness state, and verification target.
- Mark already-stable routes `ready` with evidence and avoid source-code changes unless the contract reveals a concrete gap.
- Represent frontend/native handoff as a single matrix mapping backend routes to `/Users/zhdeng/stoa-frontend` reuse points and future native responsibilities.

### Mobile Client States
- Every critical flow should define loading, empty, unavailable/error, unauthorized, stale/offline, and refreshed states.
- The no-demo-fallback rule is strict for parent, billing, support, notification, locale/session, and student learning flows.
- Offline behavior in Phase 172 is read-through cache and manual refresh/reconcile guidance; native offline storage implementation belongs to Phase 173 or a native workspace.
- Mobile errors should include product-facing state guidance plus backend contract notes: status, reason category, retry/refetch behavior, and safe fallback destination.

### Frontend And Native Handoff
- Reuse existing frontend app shell, auth store/query, language switcher, notification center, i18next resources, and route services rather than creating a parallel web contract.
- Native apps own secure device storage, platform push permission UX, local cache implementation, deep-link routing, and app-store release evidence.
- Frontend/PWA and native clients should treat backend durable state as authoritative, especially for auth/session, notification center, locale preferences, billing, support, and parent data.
- Client handoff should explicitly flag current demo-fallback usage that is not acceptable for critical mobile flows.

### Verification Boundary
- Phase 172 verification is contract/documentation verification plus focused static inspection of route and frontend client surfaces.
- No backend tests are required unless source behavior changes.
- Route-contract stability is verified by matching the handoff inventory to current FastAPI route registrations and known frontend service entry points.
- Follow-up implementation tasks should be left to Phase 173/174/175 or future client workspaces rather than expanded in this phase.

### the agent's Discretion
All remaining organization and table formatting choices are at the agent's discretion. Prefer compact, action-oriented tables over exhaustive OpenAPI duplication.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/main.py` registers auth, conversations, practice, questions, students, teachers, tutors, parents, billing, notifications, adaptive, admin, and files routers.
- `src/stoa/routers/auth.py` exposes `/auth/me` and `PATCH /auth/me/preferences/locale` with `preferredLocale` and `effectiveLocale`.
- `src/stoa/routers/notifications.py` exposes notification list, preferences, digest preview/send, push-token register/revoke, read/archive, and admin delivery-status routes.
- `/Users/zhdeng/stoa-frontend/src/services/auth/authApi.ts`, auth hooks, `LanguageSwitcher`, and `useCurrentUserQuery` already synchronize locale state with backend APIs.
- `/Users/zhdeng/stoa-frontend/src/components/notifications/NotificationCenter.tsx` and notification hooks/services already provide notification center and realtime refresh foundations.

### Established Patterns
- Backend route modules use FastAPI routers, role dependencies, Pydantic response models for many routes, and frontend-facing camelCase fields where appropriate.
- Backend mobile readiness means stable bounded API contracts, not user-agent/device sniffing.
- Existing frontend uses TanStack Query, i18next resources under `src/i18n/locales/{en,de,...}`, and `withDemoFallback` in several services.

### Integration Points
- Mobile/native handoff should point clients to `/auth/*`, `/students/*`, `/parents/me/*`, `/tutors/*`, `/practice/*`, `/adaptive/*`, `/notifications/*`, `/billing/*`, and selected `/admin/*` operational readiness routes.
- Critical no-demo-fallback attention is needed around frontend billing, notification, support, tutor, student, and learning services that still import `withDemoFallback`.
- Future native app integration should consume the same backend routes and durable state rather than a separate backend API surface.

</code_context>

<specifics>
## Specific Ideas

- Produce `172-MOBILE-API-READINESS-HANDOFF.md` as the main handoff artifact.
- Include route groups by role/surface instead of an exhaustive line-by-line OpenAPI clone.
- Include a readiness legend: `ready`, `client-work-needed`, `backend-gap`, `native-work-needed`, and `deferred`.
- Call out no-demo-fallback requirements as client release criteria for critical mobile flows.

</specifics>

<deferred>
## Deferred Ideas

- Full native offline cache implementation.
- App-store release workflow.
- New backend endpoints unless a later implementation phase proves an unavoidable gap.
- Broad frontend code changes in `/Users/zhdeng/stoa-frontend`.

</deferred>
