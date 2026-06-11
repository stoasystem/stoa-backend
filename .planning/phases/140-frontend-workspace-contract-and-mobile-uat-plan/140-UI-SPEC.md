# Phase 140 UI Design Contract

**Phase:** 140 Frontend Workspace Contract And Mobile UAT Plan
**Status:** Approved
**Updated:** 2026-06-11

## Product Surface

Phase 140 is a contract phase for the existing React/Vite frontend at `/Users/zhdeng/stoa-frontend`. It sets the design and verification boundaries for Phase 141 responsive flow polish and Phase 142 visible localization work.

## Visual Direction

- Keep the current STOA operational product language: quiet, dense, warm, and work-focused.
- Continue using Tailwind utility classes, Radix UI primitives, lucide icons, and existing brand tokens in `src/styles/*.css`.
- Preserve existing `PageContainer`, `PageHeader`, `SectionHeader`, `DashboardLayout`, `Card`, `Button`, `Tabs`, `Sheet`, and status/badge components rather than introducing another design system.
- Avoid landing-page composition, oversized hero treatments, decorative gradients, and nested cards in dashboard/tool surfaces.

## Responsive Contract

- Mobile baseline viewport: 390 x 844.
- Tablet/compact desktop viewport: 768 x 1024.
- Desktop regression viewport: 1280 x 900.
- Every selected flow must render with no horizontal overflow at 390 px.
- Primary actions must remain reachable without requiring horizontal scrolling.
- Tables, dense lists, and multi-column panels should collapse to stacked rows, scrollable internal regions, tabs, or compact summaries.
- Fixed-format controls such as bottom navigation, tabs, icon buttons, cards, counters, and form actions need stable dimensions so hover/loading/translated text does not shift layout.
- Text must wrap cleanly inside buttons/cards/badges. Do not scale font size with viewport width.

## Localization Contract

- v4.3 implementation should focus on English/German visible UI first even though the current frontend has `en`, `de`, `fr`, and `it` resource directories.
- `LanguageSwitcher` and `i18next` are the existing UI/localization foundation.
- `/auth/me` locale fields and the backend locale preference update route are the persistence source for Phase 142.
- Frontend display labels may be localized; backend canonical enum/status/ID values must remain stable in API logic.
- Missing translation keys should fall back to English without breaking layout.
- German labels must be treated as the longest expected copy for mobile fit checks.

## Selected Flow Targets

Student:

- `/dashboard`
- `/practice`
- `/chat`
- `/question-bank`

Parent:

- `/parent`
- `/parent/children/:childId`
- `/parent/children/:childId/report`

Tutor:

- `/tutor`
- `/tutor/requests/:requestId`
- AI teacher tools inside the request detail page

Admin:

- `/admin`
- `/admin/report-operations`
- `/admin/moderation`

## Interaction Requirements

- Preserve keyboard focus visibility and browser back/forward behavior.
- Use familiar controls: icons in icon buttons, tabs for view switching, menus/sheets for compact navigation, toggles/checkboxes for binary preferences, and buttons only for commands.
- Keep mobile bottom navigation limited to the most important role actions.
- Do not hide role-critical actions behind hover-only affordances.
- Loading, empty, and error states must use existing shared state components where available.

## Verification Requirements

- `npm run lint`
- `npm run build`
- Targeted Playwright/mobile evidence for representative student, parent, tutor, and admin flows.
- Language switching evidence for English and German after Phase 142.
- Screenshots or Playwright assertions must prove no horizontal overflow and visible primary actions at mobile viewport width.
