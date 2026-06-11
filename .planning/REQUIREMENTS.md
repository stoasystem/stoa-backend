# Requirements: v4.3 Frontend Mobile And Visual Localization Rollout

**Milestone:** v4.3
**Status:** Active planning
**Created:** 2026-06-11

## Goal

Implement the responsive frontend and visual localization work that v4.1 intentionally left outside the backend repository. v4.3 should use the available `/Users/zhdeng/stoa-frontend` workspace to improve real student, parent, tutor, and admin workflows on mobile viewports and expose the backend locale preference foundation through usable UI.

Because STOA is still in internal development, this milestone should prioritize visible feature progress and practical browser verification over broad security/compliance testing.

## Requirements

### MOBILEUI-01 Frontend Workspace Contract And Mobile UAT Plan

Implementers have a concrete frontend workspace contract before UI changes begin.

Acceptance criteria:

- Contract confirms the frontend workspace, framework, key route structure, API client pattern, and available local verification commands.
- Mobile-critical flows are selected for v4.3: student question/practice/assignment, parent child overview/progress/report, tutor queue/detail/AI tools, admin operations dashboards.
- Mobile UAT criteria define expected behavior for narrow viewports, touch targets, navigation, overflow, loading/error states, and route-level back/forward behavior.
- Localization UAT criteria define language preference controls, locale persistence, translated visible UI copy, and fallback behavior for untranslated strings.
- Backend versus frontend ownership remains explicit: backend canonical fields stay stable; frontend owns layout, text, formatting, and visual language switching.

### MOBILEUI-02 Responsive Student Parent Tutor Core Flow Polish

Core learning workflows are usable on realistic mobile viewports.

Acceptance criteria:

- Student question/practice/assignment flows fit mobile viewports without horizontal overflow or clipped primary actions.
- Parent child overview, progress, and report views show scannable mobile layouts with clear loading/empty/error states.
- Tutor queue/detail and AI teacher tool surfaces are usable on mobile-width screens without nested card clutter or broken controls.
- Shared navigation and route transitions work on mobile without hiding key actions.
- Browser or Playwright evidence captures representative mobile viewports.

### I18NUI-01 Visual Localization And Language Preference UI

Users can see and change supported language preferences in the frontend.

Acceptance criteria:

- Frontend exposes English/German language preference controls backed by the v4.1 locale preference API.
- Supported visible UI copy in selected core flows is translated or routed through a translation map.
- Locale preference persists through refresh and is reflected in `/auth/me` derived UI state.
- Canonical backend values remain untranslated in API logic; display labels are localized separately.
- Browser evidence covers language switching and fallback behavior.

### VERIFY-26 v4.3 Browser Release Gate And Localization Audit

v4.3 closes with mobile/browser evidence and an updated `stoa_docs` remaining-feature audit.

Acceptance criteria:

- Frontend lint/build and targeted browser checks pass or isolate documented pre-existing failures.
- Mobile viewport screenshots or Playwright evidence cover student, parent, tutor, and admin representative flows.
- Language preference and translated UI behavior are verified for English/German paths.
- Backend planning docs, frontend handoff notes, feature gap audit, and remaining-feature queue reflect completed v4.3 work.
- The next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Native mobile app surfaces and push token registration.
- Full translation management, translator workflow, and broad copy QA.
- RTL visual layout support if STOA adds RTL languages.
- Live payment-provider rollout, TWINT production validation, invoices/receipts/refunds, tax/accounting, and dunning.
- Support-ticket/evidence destination integrations after approved connector or credential path exists.
- Rich curriculum authoring workflow, production content QA, analytics dashboards, and deeper operations reporting.

## Out of Scope

- Server-side device sniffing or backend route branching by user agent.
- Machine translation of tutor notes, student free text, generated explanations, reports, or educational content.
- Native app implementation unless a native workspace is explicitly selected.
- Broad security/compliance test expansion beyond what is needed for the touched UI/API paths.
- Live production mutation smoke.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILEUI-01 | Phase 140 | Complete |
| MOBILEUI-02 | Phase 141 | Complete |
| I18NUI-01 | Phase 142 | Complete |
| VERIFY-26 | Phase 143 | Planned |
