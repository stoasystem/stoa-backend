# v4.1 Research Summary

**Project:** STOA Backend
**Domain:** Mobile-ready API contracts and multilingual preference foundation
**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Researched:** 2026-06-11
**Confidence:** HIGH for backend scope and locale-preference architecture; MEDIUM for final mobile UI UAT until a frontend workspace is available.

## Executive Summary

v4.1 should be framed as a backend foundation milestone, not a full visual mobile redesign. This repository can add durable locale preference support, explicit language metadata, fallback behavior, mobile-friendly route contract checks, and updated gap documentation. It cannot honestly claim completed responsive layouts, touch target fixes, or localized visual screens without the frontend/native workspace and browser verification.

The recommended approach is reuse-first. Keep FastAPI, Pydantic, DynamoDB profile records, and existing route tests. Add a small shared locale preference layer, expose effective locale through authenticated profile/user surfaces, and preserve canonical API fields across locales. Mobile polish should focus on route payload shape, bounded responses, compact summaries where needed, and documentation for client rendering responsibilities.

## Key Findings

### Stack

No new infrastructure or translation provider is needed for the v4.1 foundation. The existing backend can support:

- Locale preference read/update APIs.
- Durable storage on user/profile records.
- Shared locale normalization and fallback.
- Role-critical response metadata.
- Mobile-sensitive route contract audits and targeted payload polish.

Frontend clients should own responsive layout and locale-sensitive formatting. MDN documents responsive design as flexible layout/media behavior rather than device-specific server behavior, and JavaScript `Intl` covers many locale-sensitive formatting needs when APIs provide stable canonical values.

### Features

The milestone should deliver:

- Mobile contract readiness audit for student, parent, tutor, and admin flows.
- Locale preference foundation for at least English and German contracts.
- Explicit language/locale metadata where content depends on language.
- Regression protection that IDs, status codes, enum values, and timestamps remain stable across locales.
- Updated planning/gap artifacts that separate backend completion from deferred frontend/native work.

Optional follow-ons include `Accept-Language` defaulting, compact mobile summary variants for heavy routes, and small localized display-label maps. Full translation systems, RTL UI verification, and native mobile work should be deferred.

### Architecture

Add a small locale preference service/helper and repository support rather than route-local logic. Store `preferred_locale` on durable profile records. Expose effective locale through authenticated profile responses and apply metadata patterns to selected role-critical routes.

Canonical data should remain locale-neutral:

- IDs stay IDs.
- Status codes stay codes.
- Timestamps stay machine-readable.
- Display labels, if introduced, stay separate from state.

Mobile readiness should be expressed as contract behavior: pagination, bounded responses, compact summaries where justified, and consistent errors. Backend should not branch on browser/device user agents.

### Pitfalls

The most important risks are:

- Overstating mobile UI completion from backend-only changes.
- Storing locale only in temporary tokens.
- Translating canonical API values.
- Creating inconsistent route-specific fallback behavior.
- Adding automatic translation of student, tutor, or generated content.
- Ignoring future language/direction metadata even if v4.1 starts with English/German.
- Leaving old v4.0/v1.6 planning artifacts in place.

## Recommended MVP Scope

Include:

- v4.1 requirements and roadmap specific to mobile/i18n foundation.
- Mobile and multilingual contract spec/gap audit.
- Durable profile locale preference support.
- Shared locale normalization/fallback behavior.
- Role-critical API metadata and regression tests.
- Documentation and release-gate evidence for what is done versus deferred.

Exclude:

- Full frontend responsive implementation.
- Native app work.
- Machine translation provider integration.
- Translation management UI.
- RTL visual verification.
- Automatic rewriting of educational/user-generated content.

## Recommended Roadmap Shape

1. **Mobile And Multilingual Contract Foundation**
   - Define backend/client boundaries, supported locales, mobile UAT criteria, and gap audit updates.

2. **Locale Preference APIs**
   - Implement durable locale preference storage, profile exposure, normalization, fallback, and tests.

3. **Role Route Contract Polish**
   - Apply language metadata and mobile-friendly response checks to selected student/parent/tutor/admin flows.

4. **Release Gate And Documentation**
   - Verify regression coverage, update docs/gap audit, and record deferred frontend/native scope.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Backend scope | HIGH | Current repo is clearly backend-only and can implement profile preferences and API contracts. |
| Locale architecture | HIGH | Durable profile preference plus shared normalization is straightforward and low-risk. |
| Mobile contract work | HIGH | Payload and contract audits are appropriate backend work. |
| Full mobile UI polish | LOW in this repo | Requires frontend/native workspace and visual/browser verification. |
| Final supported-locale policy | MEDIUM | English/German are natural initial targets, but product confirmation may refine the allowlist. |

## Sources

- MDN Responsive Design: https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design
- MDN Intl: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- W3C Declaring Language in HTML: https://www.w3.org/International/questions/qa-html-language-declarations
- W3C Structural Markup And Right-To-Left Text: https://www.w3.org/International/questions/qa-html-dir
