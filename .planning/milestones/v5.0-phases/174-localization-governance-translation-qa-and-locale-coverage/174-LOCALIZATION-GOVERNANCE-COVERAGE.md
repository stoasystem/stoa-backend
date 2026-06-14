# Phase 174 Localization Governance Translation QA And Locale Coverage

**Milestone:** v5.0 Native Mobile And Full Localization Governance
**Requirement:** MOBILELOC-04
**Status:** Accepted for implementation by later phases
**Date:** 2026-06-14

## Scope

This artifact defines how STOA governs localization beyond ad hoc copy changes. It covers active locale support, translation catalog ownership, key lifecycle, review states, missing-key/fallback behavior, coverage reporting, copy QA, and future-locale/RTL readiness.

## Active Locale Policy

| Layer | Current active locales | Fallback/default | Notes |
|-------|------------------------|------------------|-------|
| Backend | `de`, `en` | `de` default in `locale_service.py` | Canonical API values remain locale-neutral. |
| Frontend/PWA | `en`, `de` | i18next `fallbackLng: 'en'`; browser/local storage initial language | `fr` and `it` catalog files exist but are not active in `supportedLanguages`. |
| Future native | Must match product activation list | Use backend `/auth/me` effective locale after login | Native must not activate locales unsupported by backend/product policy. |

Activation rule: a locale is active only when backend supported locales, frontend/native supported language lists, translation resources, QA evidence, and release notes all agree.

## Catalog Ownership

| Namespace | Primary surface | Owner |
|-----------|-----------------|-------|
| `common` | Shared shell, buttons, statuses, labels | Product/content plus frontend implementation |
| `auth` | Login, registration, locale/session copy | Product/content plus frontend implementation |
| `chat` | Student chat/question conversation UI | Learning product/content |
| `parent` | Parent portal child/report/progress copy | Parent experience owner |
| `practice`, `questionBank`, `uploads`, `liveClassroom` | Learning and curriculum surfaces | Learning product/content |
| `tutor` | Tutor queue and AI teacher tools | Tutor workflow owner |
| `billing`, `pricing` | Subscription, checkout, finance copy | Product/finance owner |
| `support` | Support handoff and status copy | Support operations owner |
| `admin` | Admin operations surfaces | Operations owner |
| `errors` | Error, unavailable, retry, validation copy | Product/content plus engineering |
| `contact`, `home` | Marketing/contact surfaces | Marketing/product owner |

## Key Lifecycle

| State | Meaning | Release rule |
|-------|---------|--------------|
| `draft` | Key exists but copy is not reviewed in both active locales | Allowed during development only. |
| `reviewed` | English and German copy reviewed for meaning and tone | Required for critical-flow release candidates. |
| `approved` | Copy owner accepts the key for release | Required for release-ready critical flows. |
| `deprecated` | Key should no longer be used; kept temporarily for safe removal | Must be removed or tracked before broad release. |

Recommended metadata can live in a future catalog manifest or QA report rather than inside runtime JSON files.

## Missing-Key And Fallback Behavior

- Runtime fallback may use English for missing frontend keys, but missing keys in active critical flows are release blockers.
- Backend locale fallback may default to `de`; frontend display fallback currently uses `en`. Client copy should not assume these are identical.
- Missing translation evidence should include namespace, key, route/surface, active locale, owner, and resolution status.
- Missing keys must not localize or alter API canonical values.
- Unsupported locale requests should be rejected or normalized by backend/frontend allowlists, not silently activated.

## English/German Catalog Audit

Static key parity check across loaded frontend namespaces found matching English/German key counts:

| Namespace | English keys | German keys | Missing German keys | Extra German keys |
|-----------|--------------|-------------|---------------------|-------------------|
| admin | 5 | 5 | 0 | 0 |
| auth | 69 | 69 | 0 | 0 |
| billing | 38 | 38 | 0 | 0 |
| chat | 44 | 44 | 0 | 0 |
| common | 114 | 114 | 0 | 0 |
| contact | 42 | 42 | 0 | 0 |
| errors | 19 | 19 | 0 | 0 |
| home | 41 | 41 | 0 | 0 |
| liveClassroom | 47 | 47 | 0 | 0 |
| parent | 16 | 16 | 0 | 0 |
| practice | 36 | 36 | 0 | 0 |
| pricing | 18 | 18 | 0 | 0 |
| questionBank | 8 | 8 | 0 | 0 |
| support | 7 | 7 | 0 | 0 |
| tutor | 8 | 8 | 0 | 0 |
| uploads | 40 | 40 | 0 | 0 |

This proves key parity, not complete visual or semantic coverage. Hardcoded strings can still exist in components and services.

## Broad Copy QA Workflow

For each critical surface, release QA should check:

- route/page/component owner
- namespace and key coverage
- English/German semantic equivalence
- German text fit on mobile viewport
- status/error/empty/loading/offline copy
- canonical API values preserved separately from display labels
- tone and terminology consistency
- legal/financial/support wording reviewed by the right owner where relevant

Critical surfaces:

| Surface | QA focus |
|---------|----------|
| Student | Dashboard, chat/question, OCR/AI answer, teacher takeover, practice/curriculum, assignments, notifications |
| Parent | Child list/detail, history, reports, learning profile, billing/subscription, notifications |
| Tutor | Queue/detail, reply composer, AI teacher tools, assignments, SLA/status labels, notifications |
| Admin | Moderation, report operations, billing, support, notification delivery, curriculum authoring/analytics |
| Billing | Checkout readiness, provider states, refunds, invoices/finance handoff, dunning wording |
| Notification | Center, preferences, digest, push permission/provider states, offline/reconnect |
| Support | Handoff queue/status, provider errors, retry/sync/message states |
| Curriculum/AI tools | Lesson/exercise/admin authoring copy, reviewed AI draft labels, content-quality signals |

## Implementation Tasks From Current Gaps

1. Add a catalog parity/coverage script or CI check for active locale namespaces.
2. Inventory hardcoded strings in notification, admin, billing, support, curriculum, and AI teacher tool surfaces.
3. Remove or explicitly gate demo fallback from critical localized/mobile flows before release-ready status.
4. Add a copy QA report template capturing owner, namespace, keys, locale, mobile fit, and approval state.
5. Align backend/frontend default/fallback documentation so implementers understand backend `de` default versus frontend `en` fallback.
6. Decide whether inactive `fr`/`it` resources are retained as experimental assets or removed until product activation.

## Future Locale And RTL Readiness

Future locale activation requires:

- product owner and reviewer for each new locale
- backend allowlist update
- frontend/native supported-language update
- complete namespace catalog
- date/number/currency formatting review
- mobile text expansion review
- accessibility and screen-reader pronunciation spot checks
- release note and rollback plan

RTL is deferred. Readiness means future UI work should avoid hardcoded left/right assumptions where practical, but no RTL layout implementation is part of v5.0 unless explicitly promoted later.

## Release Evidence

Phase 175 should capture:

- active locale list and fallback policy
- English/German key parity result
- hardcoded-string/copy QA gap list
- critical-flow copy QA status
- future-locale/RTL deferred scope
- rollout classification: `contract-ready`, `frontend-ready`, `native-ready`, `blocked`, or `deferred`
