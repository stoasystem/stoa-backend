# Phase 140 Frontend Mobile And Localization Contract

**Status:** Complete
**Updated:** 2026-06-11
**Requirement:** MOBILEUI-01

## Target Workspace

Frontend implementation should happen in:

- `/Users/zhdeng/stoa-frontend`

Confirmed workspace evidence:

- React 19 + TypeScript + Vite 6 SPA.
- Tailwind CSS 4, Radix UI primitives, lucide icons, TanStack Query, Zustand, Axios, i18next/react-i18next, and Playwright are installed.
- Key scripts:
  - `npm run dev`
  - `npm run lint`
  - `npm run build`
  - `npm run test:e2e`
- `playwright.config.ts` starts the app with demo API flags and targets `http://127.0.0.1:5173`.
- `src/app/router/routeConfig.ts` owns route metadata and role navigation.
- `src/layouts/AppLayout.tsx` owns sidebar, top navigation, language switcher, notification center, user menu, and mobile bottom navigation.
- API clients live under `src/services/**`; route data hooks live under `src/hooks/**`.
- Shared UI and page shell components live under `src/components/common` and `src/components/ui`.
- Existing localization resources live under `src/i18n/locales/{en,de,fr,it}`.

## Mobile Flow Targets

Phase 141 should implement selected responsive improvements against these concrete surfaces.

Student:

- `/dashboard` via `src/pages/dashboard/StudentDashboardPage.tsx`.
- `/practice` via `src/pages/practice/PracticeOverviewPage.tsx`.
- `/chat` via `src/pages/chat/ChatPage.tsx` and chat components under `src/components/chat`.
- `/question-bank` and question sessions under `src/pages/question-bank`.

Parent:

- `/parent` via `src/pages/parent/ParentDashboardPage.tsx`.
- `/parent/children/:childId` via `src/pages/parent/ChildSummaryPage.tsx`.
- `/parent/children/:childId/report` via `src/pages/parent/ChildReportPage.tsx`.
- Parent cards/lists under `src/components/parent`.

Tutor:

- `/tutor` via `src/pages/tutor/TutorDashboardPage.tsx`.
- `/tutor/requests/:requestId` via `src/pages/tutor/TutorHelpRequestDetailPage.tsx`.
- AI teacher tools via `src/components/tutor/AiTeacherToolsPanel.tsx`.
- Queue, filters, reply composer, and request context components under `src/components/tutor`.

Admin:

- `/admin` via `src/pages/admin/Dashboard.tsx`.
- `/admin/report-operations` via `src/pages/admin/ReportOperationsPage.tsx`.
- `/admin/moderation` via `src/pages/admin/AdminModerationPage.tsx`.
- Admin cards and operational widgets under `src/components/admin`.

## Mobile UAT Criteria

- No horizontal overflow at 390 x 844 mobile viewport.
- Tablet sanity viewport: 768 x 1024.
- Desktop regression viewport: 1280 x 900.
- Primary actions remain visible and reachable.
- Dense data becomes scannable through stacked, tabbed, or compact layouts.
- Loading, empty, and error states are readable without layout jumps.
- Route navigation and browser back/forward behavior remain predictable.
- Text does not clip within buttons, tabs, badges, or compact panels.
- Mobile bottom navigation keeps role-critical destinations reachable without crowding.
- Keyboard focus remains visible after layout changes.

## Localization Targets

- Existing `LanguageSwitcher` changes `i18next` language and writes `stoa_language` to local storage.
- Phase 142 should connect language preference persistence to `/auth/me` and the backend locale preference API.
- v4.3 selected rollout language pair is English/German even though `fr` and `it` resources currently exist.
- Localize selected visible UI copy in the chosen student, parent, tutor, and admin flows.
- Keep backend enum/status/ID logic canonical and localize display labels separately.
- Provide fallback behavior for missing translation keys.
- German copy must be included in mobile fit checks because it is usually longer.

## Implementation Handoff

Phase 141 should focus on layout and interaction polish first:

- Strengthen `AppLayout` mobile top/bottom navigation and overflow behavior.
- Audit selected page grids/cards/lists for mobile wrapping and clipped actions.
- Add targeted Playwright checks for mobile viewport overflow and visible primary actions.

Phase 142 should add preference UI and translation maps after route/component ownership is clear:

- Extend auth user types and auth service mapping for `preferredLocale` / `effectiveLocale`.
- Persist language changes through the backend locale preference API.
- Route selected page copy and display labels through existing i18n namespaces.
- Add English/German language switching checks.

## Verification Commands

- `npm run lint` -> passed during Phase 140 audit.
- `npm run build` -> passed during Phase 140 audit after allowing the frontend workspace to write TypeScript/Vite build artifacts.
- `npm run test:e2e` -> available for Phase 141/142 targeted browser evidence.
