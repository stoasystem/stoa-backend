# Phase 140 Frontend Mobile And Localization Contract

**Status:** Draft placeholder pending frontend workspace audit
**Updated:** 2026-06-11
**Requirement:** MOBILEUI-01

## Target Workspace

Frontend implementation should happen in:

- `/Users/zhdeng/stoa-frontend`

Initial workspace evidence from backend planning:

- Vite/React workspace is present.
- `package.json`, `vite.config.ts`, `playwright.config.ts`, `src/`, and `.planning/` exist.
- Existing node dependencies and `dist/` are present.

## Mobile Flow Targets

Phase 140 should confirm concrete routes/components, then Phase 141 should implement selected responsive improvements.

Student:

- Question submit and answer review.
- Practice or assignment flow.
- Progress or curriculum navigation.

Parent:

- Child overview.
- Progress/history.
- Report view.

Tutor:

- Queue/list view.
- Question/session detail.
- AI teacher tools and exercise draft review.

Admin:

- Operations/dashboard surfaces that remain relevant on tablet/mobile-width internal use.

## Mobile UAT Criteria

- No horizontal overflow at representative mobile widths.
- Primary actions remain visible and reachable.
- Dense data becomes scannable through stacked, tabbed, or compact layouts.
- Loading, empty, and error states are readable without layout jumps.
- Route navigation and browser back/forward behavior remain predictable.
- Text does not clip within buttons, tabs, badges, or compact panels.

## Localization Targets

- Expose English/German language preference controls.
- Read initial locale from `/auth/me` where available.
- Persist changes through the backend locale preference API.
- Localize selected visible UI copy in core flows.
- Keep backend enum/status/ID logic canonical and localize display labels separately.
- Provide fallback behavior for missing translation keys.

## Implementation Handoff

Phase 141 should focus on layout and interaction polish first. Phase 142 should add preference UI and translation maps after route/component ownership is clear.
