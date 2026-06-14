# Phase 171 Native Mobile And Localization Governance Contract

**Milestone:** v5.0 Native Mobile And Full Localization Governance
**Requirement:** MOBILELOC-01
**Status:** Accepted for implementation by later phases
**Date:** 2026-06-14

## Scope

v5.0 moves STOA beyond the v4.1 backend locale foundation, the v4.3 selected responsive frontend rollout, and the v4.9 notification/native handoff. This phase defines the operating contract for the rest of the milestone: mobile app/API readiness, native notification token and offline-state handoff, translation management, broad copy QA, locale coverage, and client release evidence.

This contract does not require a full native app binary in `stoa-backend`. Native shell implementation, app-store release, platform permission UX, secure device storage, and final production client rollout remain future native/mobile workspace responsibilities unless a dedicated workspace is approved.

## Upstream Foundation

| Source | Relevant shipped foundation | v5.0 implication |
|--------|-----------------------------|------------------|
| v4.1 Phase 132 | Backend/mobile contract, durable `en`/`de` locale policy, canonical API stability rules | Phase 172 and Phase 174 must preserve canonical route/status values while documenting mobile/localized display behavior separately. |
| v4.1 Phase 133/134 | Locale preference APIs and language-safe route metadata | Mobile clients should read locale from `/auth/me` and update it through the backend preference route rather than storing only local UI state. |
| v4.3 Phase 140 | Frontend workspace contract for `/Users/zhdeng/stoa-frontend` | Phase 172 must name frontend reuse points and native integration points instead of inventing a second web client contract. |
| v4.3 Phase 141/142 | Selected responsive shell/page polish and English/German language preference UI | Phase 174 must broaden copy QA and coverage beyond the selected core-flow rollout. |
| v4.9 Phase 169 | Notification center, preferences, digest, push token, WebSocket, and native handoff | Phase 173 must refine token/offline/deep-link behavior for native/mobile clients using durable backend state as the source of truth. |
| `STOA_DOCS_FEATURE_GAP_AUDIT.md` | Native apps and full localization governance remain active v5.0 gaps | Phase 175 must update the queue with rollout state and next milestone recommendation. |

## Ownership Boundaries

| Area | Owner | v5.0 Responsibility | Out of Scope For This Backend Milestone |
|------|-------|---------------------|----------------------------------------|
| Backend APIs | `stoa-backend` | Stable mobile-critical route inventory, locale preference contract, notification token lifecycle records, canonical value stability, focused backend checks when behavior is touched | Device UI, app-store packaging, native secure storage, push-provider mobile SDK wiring |
| Frontend web/PWA | `/Users/zhdeng/stoa-frontend` | Reusable app shell patterns, existing i18n resources, responsive behavior evidence, language preference UI, no-demo-fallback client states | Full native app binary, platform push permission prompts |
| Native apps | Future native workspace | Native shell, secure token capture, token registration/revocation calls, offline cache policy, deep-link/tap routing, app-store release evidence | Backend route redesign without Phase 172 contract evidence |
| Localization | Product/content owner plus implementation owner | Translation source of truth, key lifecycle, review states, copy ownership, English/German coverage, missing-key handling, broad copy QA | Machine translation automation as the source of truth, marketing campaign localization |
| Content and curriculum | Product/content owner | Locale-aware educational copy review, language-tagged content boundaries, curriculum/AI teacher copy QA | Automatic translation of user-generated or tutor-reviewed educational content without explicit review |
| Release | Product/engineering owner | Rollout state classification, client handoff package, residual blockers, next milestone selection | Live customer-facing activation without explicit approval gates |

## Mobile-Critical User Flows

Phase 172 must inventory these as route contracts with method, auth role, response shape, loading/empty/error state, offline/read-through expectation, cache expectation, and current readiness state.

### Student

- Auth/session: login, refresh, logout, `/auth/me`, locale preference refresh.
- Learning dashboard: student profile, summary, learning profile, topic progress, recommendations, assignments.
- Question workflow: submit image/text question, OCR correction history, AI answer, teacher takeover state, feedback.
- Curriculum and practice: catalog, lesson detail, exercise bank, practice progress, reviewed assignments.
- Notifications: durable center, read/archive, preferences, realtime refresh, push eligibility, offline refresh.

### Parent

- Child overview: `/parents/me/children` and compact child cards.
- Child detail: summary, history, report, learning profile, assignment/progress signals.
- Billing/subscription: current plan/status, provider-managed state, checkout/refund readiness states.
- Notifications: reports, subscription changes, child learning updates, digest/push preferences.

### Tutor/Teacher

- Queue and request detail: help requests, takeover, reply, resolve, notes, SLA fields.
- AI teacher tools: summary drafts, focus suggestions, explanation drafts, exercise drafts.
- Assignments and curriculum signals: reviewed assignment flows and curriculum context.
- Notifications: queue refresh, student reply events, assignment updates, offline/manual refresh.

### Admin

- Operational surfaces: moderation, report operations, billing operations, support handoff, notification delivery status, curriculum authoring/analytics.
- Mobile stance: admin mobile is supported for readable bounded states, but dense operations may remain desktop-first where explicitly documented.
- Privacy: admin mobile views must preserve metadata-only boundaries and avoid raw private artifacts, raw provider secrets, raw push tokens, or hidden demo fallback.

## Localization Governance

### Supported Locales

- Current product locale pair: `en` and `de`.
- `de` remains a supported default/fallback path for current STOA behavior.
- Additional locales and RTL are readiness/deferred scope unless Phase 174 explicitly promotes concrete implementation tasks.

### Canonical API Rule

The backend must keep canonical values locale-neutral:

- route paths and HTTP semantics
- role names, permission checks, and ownership rules
- IDs, storage keys, object references, and report artifact keys
- status codes, enum values, lifecycle states, billing states, moderation states, assignment states, notification states
- ISO timestamps and machine-readable numeric values

Localized labels may be added only as separate display fields or client translation keys. Tests should prove canonical values remain stable when locale changes.

### Translation Source Of Truth

Phase 174 must define one catalog workflow for product UI copy:

- key naming convention by role/surface/component/action/state
- owner for each namespace or surface
- lifecycle states: draft, reviewed, approved, deprecated
- review expectations for English and German
- missing-key fallback behavior and evidence
- coverage reporting for critical routes and surfaces

Educational and user-generated content stays language-tagged and reviewed rather than automatically translated by default. This includes tutor notes, student answers, AI drafts, parent reports, curriculum content, and conversation messages.

## Native Notification And Offline Handoff

Durable backend notification state is authoritative. WebSocket, email digest, and push are delivery accelerators, not the source of truth.

Phase 173 must define:

- Push token registration fields: platform, device/install ID, raw token handling, provider token reference, token reference/hash, lifecycle status, last seen timestamp, revocation timestamp.
- Token lifecycle triggers: first permission grant, token refresh, logout, account switch, permission withdrawal, explicit notification disablement, uninstall signal when available.
- Permission states: not requested, granted, denied, provisional/limited where platform-specific, provider not configured, provider disabled, opted out.
- Notification UX states: live, polling fallback, reconnecting, offline, unread, read, archived, digest-eligible, push-eligible, provider-refused, send-failed.
- Deep-link/tap routing: `eventId`, `eventType`, `targetType`, `targetId`, authenticated role, stale target handling, and safe fallback destination.
- Offline/read-through behavior for notification center, learning history, reports, assignments, billing, and support status.

Native clients must not persist raw push tokens outside platform secure storage and must not display raw tokens in UI or logs.

## Mobile API Readiness Contract

Phase 172 must produce a client handoff table with these columns:

| Field | Meaning |
|-------|---------|
| Surface | Auth, profile, student, parent, tutor, admin, notifications, billing, support, curriculum |
| Route | HTTP method and path |
| Auth role | Required authenticated role and ownership boundary |
| Response shape | Mobile-relevant fields and compact display affordances |
| States | Loading, empty, error, offline, stale, unauthorized |
| Cache/offline policy | Read-through cache, refetch trigger, manual refresh, no-cache |
| Current readiness | Ready, backend change needed, frontend/native change needed, deferred |
| Verification | Test, static contract check, doc-only handoff, or manual evidence |

Critical flows must not mask backend/API failures with demo fallback. Parent, billing, support, notification, and locale preference flows must show explicit unavailable/error states.

## Release Evidence And Rollout States

Phase 175 must classify v5.0 with one or more rollout states:

- `contract-ready`: v5.0 contracts and handoff docs are complete.
- `frontend-ready`: frontend/PWA implementation and English/German coverage are verified for selected surfaces.
- `native-ready`: native workspace has implemented shell, token, offline, locale, and deep-link requirements.
- `blocked`: required workspace, provider, content owner, credential, deployment, or release prerequisite is absent.
- `deferred`: backend/client contract is complete but native app release or external activation remains future scope.

Required release evidence:

- mobile API readiness inventory
- native token/offline/deep-link handoff
- localization governance and copy QA evidence
- focused backend/frontend checks or documented pre-existing failures
- remaining-feature queue update
- next milestone recommendation

## Phase Handoff

Phase 172 should define mobile API readiness and client handoff. It should inspect current route contracts and produce an actionable client inventory.

Phase 173 should define native notification token and offline state handoff. It should build on the v4.9 notification handoff and specify native permission, token, reconnect, offline, and deep-link behavior.

Phase 174 should define localization governance, translation QA, and locale coverage. It should audit English/German critical-flow coverage and turn gaps into concrete implementation tasks.

Phase 175 should verify the milestone, record rollout state, update feature-gap docs, and recommend the next milestone.
