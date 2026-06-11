# Requirements: v4.1 Mobile And Multilingual Polish Foundation

**Milestone:** v4.1
**Status:** Planned
**Created:** 2026-06-11

## Goal

Prepare STOA for mobile-friendly and multilingual product polish through backend contracts, durable locale preferences, language-safe response metadata, and clear release evidence. This backend repository should provide the API and planning foundation while explicitly tracking frontend/native UI work as deferred unless a UI workspace is added.

## Requirements

### MOBILE-01 Mobile-Ready Backend Contract And Gap Audit

Implementers have a concrete contract for mobile-critical student, parent, tutor, and admin flows before backend route polish begins.

Acceptance criteria:

- Contract identifies mobile-critical flows for student practice/assignments/progress, parent child overview/reports/progress, tutor queue/detail workflows, and plausible admin operations.
- Contract audits route payloads for mobile pain points: unbounded lists, oversized nested data, inconsistent errors, unclear loading/retry semantics, and missing compact summaries.
- Contract states that backend behavior must not branch on browser or device user-agent sniffing.
- Contract separates backend API readiness from deferred frontend/native responsive layout, touch target, focus, and visual localization work.
- Gap audit is updated so v4.1 planning no longer carries stale v4.0 wording.

### I18N-01 Durable Locale Preference Foundation

Backend supports durable user locale preferences and deterministic fallback behavior.

Acceptance criteria:

- Authenticated users can read their effective locale through an existing or new profile/preferences response.
- Authorized users can update supported locale preferences, initially covering English and German contracts unless phase planning refines the allowlist.
- Locale preference is stored durably on backend profile/user data, not only in JWT/session state.
- Locale normalization and fallback are shared across routes rather than reimplemented per router.
- Focused tests cover supported locale, missing locale, unsupported or malformed locale behavior, persistence, and backwards compatibility for existing users.

### I18N-02 Language-Safe Role Route Metadata

Role-critical responses expose language/locale metadata where useful while preserving canonical API values.

Acceptance criteria:

- Selected student, parent, tutor, and admin responses include effective locale or language metadata where content display depends on language.
- Canonical IDs, enum values, status codes, timestamps, permissions, and storage keys remain stable across locale preferences.
- Translatable display labels, if introduced, are separate from canonical state fields.
- Educational/user-generated/generated content is not automatically rewritten by v4.1; language metadata and frontend formatting responsibilities are documented.
- Tests prove authorization and canonical route behavior remain unchanged when locale preferences differ.

### VERIFY-24 v4.1 Release Gate And Deferred UI Evidence

v4.1 closes with verification evidence and an honest record of completed backend work versus deferred frontend/native UI implementation.

Acceptance criteria:

- Focused backend tests and relevant static checks pass or documented pre-existing failures are isolated.
- Requirements, roadmap, feature gap audit, and release notes reflect completed backend locale/mobile contract work.
- Final audit lists remaining frontend/native mobile and visual localization tasks that this backend repo cannot complete alone.
- Release evidence includes source research references for responsive design, locale formatting, language metadata, directionality, and accessibility concerns.

## Future Requirements

- Full responsive frontend implementation with mobile viewport/browser verification.
- Native mobile application surfaces.
- Full translation management and translator workflow.
- Machine translation or translation memory integration.
- RTL visual layout implementation and verification.
- Localized AI tutoring/content generation beyond explicit language metadata.
- Production notification delivery, live payment rollout, support integrations, rich content authoring, and deeper analytics.

## Out of Scope

- Server-side browser or device sniffing.
- Automatic translation of tutor notes, student free text, generated explanations, reports, or other educational content.
- Replacing canonical API values with localized labels.
- Claiming frontend mobile completion from backend-only work.
- New translation provider, localization database, or infrastructure service unless later phase evidence proves it necessary.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILE-01 | Phase 132 | Complete |
| I18N-01 | Phase 133 | Planned |
| I18N-02 | Phase 134 | Planned |
| VERIFY-24 | Phase 135 | Planned |
