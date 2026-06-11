# Phase 132 Mobile And Multilingual Backend Contract

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Requirement:** MOBILE-01
**Status:** Accepted for implementation by later phases
**Date:** 2026-06-11

## Scope

This contract defines what the backend must provide so STOA clients can become mobile-friendly and multilingual without unstable assumptions. It does not claim completed responsive frontend layouts, native mobile screens, touch target fixes, focus behavior, or visual localization.

## Mobile-Critical Flow Audit

| Role | Flow | Current backend surface | v4.1 contract implication |
|------|------|-------------------------|---------------------------|
| Student | Profile and onboarding context | `GET/PATCH /students/me/profile`, `GET /auth/me` | Locale preference should be readable and updatable without changing identity or authorization. |
| Student | Practice, questions, and conversations | `/practice/*`, `/questions/*`, `/conversations/*` | Keep lists bounded/paginated where available, preserve stable IDs/statuses, and avoid locale-specific canonical values. |
| Student | Memory, recommendations, assignments | `/adaptive/students/me/memory`, `/adaptive/students/me/assignments`, assignment transitions | Responses should be compact enough for mobile cards and include locale/language metadata where display text depends on language. |
| Parent | Children overview | `GET /parents/me/children` | Child summaries should remain compact and should not expose sibling/private data while adding locale metadata. |
| Parent | Child summary, history, reports, progress | `/parents/me/children/{id}/summary`, `/history`, `/report`, `/learning-profile`, `/adaptive/parents/me/children/{id}/progress` | Preserve authorization checks and canonical report/status values; frontend owns responsive presentation. |
| Tutor | Queue/detail/status/notes | `/tutors/me/help-requests`, detail, patch, notes | Lists should stay bounded and status values should remain canonical even if display labels are localized later. |
| Tutor/Admin | AI tools and drafts | `/tutors/ai-tools/*`, `/admin/*` | Do not automatically translate generated or reviewed content; tag language where needed. |
| Admin | Operational lists and reports | `/admin/users`, `/admin/stats`, report operations, billing/moderation/evidence routes | Mobile access is plausible but not a primary visual target in this backend; contracts should stay bounded, metadata-only where privacy matters, and canonical. |

## Backend Mobile Readiness Rules

1. Do not branch behavior on browser user-agent or inferred device class.
2. Prefer explicit list/detail contracts, pagination, limits, and compact summaries over large unbounded payloads.
3. Keep error responses stable enough for mobile clients to render short retry states.
4. Preserve existing privacy boundaries when creating compact response variants.
5. Keep timestamps machine-readable; clients own locale-sensitive formatting unless a route explicitly adds separate display text.

## Supported Locale Policy

Initial v4.1 supported locales:

- `en` - English
- `de` - German

Default behavior:

- If a user has a durable locale preference, use it as the effective locale.
- If no durable preference exists, default to `de` for backwards compatibility with the current registration default.
- Unsupported or malformed locale update inputs should be rejected with a validation error in Phase 133, not silently stored.
- Optional `Accept-Language` negotiation may be added later as an advisory default, but it is not required for v4.1.

Storage contract:

- Persist profile preference durably on `USER#{user_id}` / `PROFILE` records.
- Continue reading legacy `language` / `preferredLanguage` fields for compatibility.
- Phase 133 may introduce canonical snake_case `preferred_locale` while keeping camelCase API fields for existing frontend clients.

## Language-Safe API Rules

Canonical values must not change by locale:

- IDs
- route paths
- status codes and enum values
- role names and permission checks
- ISO timestamps
- DynamoDB keys and S3/report artifact keys
- billing, moderation, assignment, report, and recovery state machines

Display values may be added later only as separate fields, for example:

- `effectiveLocale`
- `contentLanguage`
- `displayLabel`
- `localizedLabel`

Educational and user-generated content is language-tagged, not automatically translated, in v4.1:

- tutor notes
- student answers
- AI draft explanations
- parent reports
- conversation messages
- curriculum exercise content

## Backend Versus Frontend Ownership

Backend owns:

- durable locale preference persistence
- locale normalization/fallback
- API metadata and canonical-value stability
- bounded/mobile-friendly response contracts
- route tests and release evidence

Frontend/native clients own:

- responsive layout
- mobile viewport behavior
- touch target sizing
- focus and keyboard behavior
- truncation/overflow handling
- localized visual copy
- use of platform/browser locale formatting APIs
- RTL visual verification when future languages require it

## Phase Handoff

Phase 133 should implement the durable locale preference API foundation using this contract.

Phase 134 should apply route metadata and contract tests to selected student, parent, tutor, and admin flows using this contract.

Phase 135 should verify that backend evidence is complete and that deferred frontend/native mobile and visual localization scope is explicit.
