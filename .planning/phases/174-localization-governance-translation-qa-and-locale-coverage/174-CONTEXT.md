# Phase 174: Localization Governance Translation QA And Locale Coverage - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 174 defines localization as a governed product workflow. It audits current English/German catalog structure, defines ownership and lifecycle states, specifies missing-key/fallback behavior, scopes broad copy QA, and records future-locale/RTL readiness. It does not rewrite the frontend catalog or activate additional locales from this backend workspace.

</domain>

<decisions>
## Implementation Decisions

### Active Locale Scope
- Treat `en` and `de` as the active v5.0 product locales because both backend `locale_service.py` and frontend `supportedLanguages` support that pair.
- Treat existing `fr` and `it` frontend catalog files as readiness/deferred assets, not active supported locales, until product/content ownership promotes them.
- Keep backend canonical values locale-neutral; localized display copy stays in frontend/client translation catalogs or explicit display fields.
- Default/fallback behavior should be documented across backend and frontend because backend currently defaults to `de` while frontend i18next fallback is `en`.

### Catalog Governance
- Use namespace-based ownership aligned with current frontend namespaces: common, auth, chat, parent, practice, questionBank, uploads, liveClassroom, tutor, pricing, billing, support, contact, admin, errors.
- Define key lifecycle states: draft, reviewed, approved, deprecated.
- Require English and German review for critical flows before release-ready status.
- Require missing-key reports and key parity checks as release evidence.

### Copy QA Coverage
- Broad copy QA must cover student, parent, tutor, admin, billing, notification, support, curriculum, and AI teacher tool surfaces.
- German text expansion should be part of mobile fit checks because German strings are often longer.
- Educational/user-generated/AI-generated content should be language-tagged and reviewed, not automatically translated by default.
- Copy QA should check tone, terminology, legal/financial/support wording, and status labels separately from API canonical values.

### Future Locale And RTL Readiness
- Future locales require product owner, catalog owner, reviewer, fallback policy, date/number formatting review, and mobile fit review before activation.
- RTL is explicitly deferred; readiness means avoiding assumptions that would block later RTL work, not implementing RTL now.
- Locale activation must update backend supported locales, frontend supported language list, translation resources, tests, and release evidence together.

### the agent's Discretion
All exact table layout, coverage grouping, and task wording are at the agent's discretion. Keep output usable for Phase 175 release evidence.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/locale_service.py` supports `de` and `en`, normalizes base locales, and defaults to `de`.
- `/Users/zhdeng/stoa-frontend/src/i18n/languages.ts` supports `en` and `de`, stores `stoa_language`, and defaults browser/unsupported values to `en`.
- `/Users/zhdeng/stoa-frontend/src/i18n/index.ts` loads English and German resources for 16 namespaces and uses i18next fallback language `en`.
- Frontend `fr` and `it` locale JSON files exist but are not active in `supportedLanguages`.

### Established Patterns
- Frontend translation files are namespace JSON catalogs under `src/i18n/locales/{locale}/{namespace}.json`.
- Current English/German key parity is clean across loaded namespaces: no missing German or extra German keys in the checked catalog.
- Backend locale API exposes `preferredLocale`, `effectiveLocale`, and `supportedLocales` through auth/profile paths.

### Integration Points
- Phase 175 should include catalog parity and mobile fit evidence.
- Future frontend/native work should remove hardcoded strings from notification, admin, billing, support, curriculum, and AI teacher tool surfaces before claiming broad localization readiness.
- Any locale expansion must update both backend and frontend locale allowlists.

</code_context>

<specifics>
## Specific Ideas

- Produce `174-LOCALIZATION-GOVERNANCE-COVERAGE.md`.
- Include current catalog parity counts from the English/German audit.
- Include active gaps as implementation tasks instead of modifying frontend code in this backend phase.
- Define release evidence needed for `frontend-ready` versus `contract-ready`.

</specifics>

<deferred>
## Deferred Ideas

- Activating `fr` or `it`.
- RTL implementation.
- Machine translation as source of truth.
- Automatic translation of student, tutor, parent-report, curriculum, or AI-generated educational content.

</deferred>
