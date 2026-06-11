# v4.1 Stack Research: Mobile And Multilingual Polish Foundation

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Researched:** 2026-06-11
**Repository scope:** `stoa-backend` FastAPI/Lambda backend and planning artifacts. Frontend or native UI work is out of this workspace unless added later.

## Current Stack Fit

The existing backend stack is sufficient for the v4.1 foundation work:

- FastAPI routes and Pydantic models for explicit mobile/i18n response contracts.
- DynamoDB single-table user/profile records for durable locale preferences.
- Existing auth/user context helpers for applying profile preferences consistently across student, parent, tutor, and admin flows.
- Existing route-level tests for contract and authorization coverage.
- Existing planning/codebase documentation for tracking frontend-deferred gaps.

No new AWS service, database, queue, or translation provider is required for the first v4.1 slice. The milestone should establish preferences, metadata, fallbacks, and mobile-friendly response boundaries before any full translation system.

## Mobile Stack Implications

Mobile polish is mostly a frontend concern, but this backend can remove friction by providing stable, compact, predictable contracts:

- Avoid browser or device sniffing in backend logic.
- Keep mobile support based on explicit API shape, pagination, summary fields, and client-owned responsive layout.
- Prefer compact summaries and paginated/detail endpoints over large nested payloads in mobile-critical flows.
- Preserve stable IDs, status codes, timestamps, and enum values independent of display language.
- Document the frontend gap clearly so this repo does not falsely claim completed mobile UI implementation.

External guidance supports this direction: responsive web design should adapt to screen sizes with flexible layouts and media queries rather than server-side browser-specific behavior, and mobile users can face bandwidth, battery, and input constraints.

## Multilingual Stack Implications

Use explicit locale and language metadata rather than implicit translation:

- Store `preferred_locale` and optional fallback fields on durable user/profile records.
- Accept locale changes through authenticated profile/preferences APIs, not only JWT/session claims.
- Use BCP 47 style language tags such as `en` and `de` for external API contracts.
- Return machine-stable values separately from display labels.
- Let frontend clients use platform/browser internationalization APIs for formatting dates, numbers, lists, plural categories, and relative time where possible.
- Do not translate free-form tutor/student/AI-generated content automatically in the foundation phase.

W3C guidance treats language declaration as document/content metadata, and directionality as structural markup. Even if v4.1 starts with English/German left-to-right support, contracts should avoid blocking later per-field language tags or `dir` metadata.

## Recommended Stack Additions

Required:

- Pydantic request/response models for locale preference reads/writes.
- Repository helpers for storing locale preference on profile/user items.
- Shared locale normalization and fallback helper, kept small and dependency-free unless an existing dependency already provides the needed behavior.
- Test fixtures for `en`, `de`, unsupported locale fallback, missing locale fallback, and unchanged canonical IDs/statuses.

Optional, only if needed during phase planning:

- A tiny dependency-free parser for simple `Accept-Language` negotiation.
- Per-response `language` or `locale` metadata for selected educational content.
- Response summary models for mobile-sensitive routes if existing payloads are too heavy.

Avoid for v4.1 foundation:

- Server-side browser/device sniffing.
- Machine translation provider integration.
- New persistence services or a separate localization database.
- Localized enum/status values as API truth.
- RTL UI implementation claims without a frontend workspace and visual verification.

## Source Notes

- MDN Responsive Design: https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design
- MDN Intl: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl
- W3C Language Declarations: https://www.w3.org/International/questions/qa-html-language-declarations
- W3C Directionality: https://www.w3.org/International/questions/qa-html-dir
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
