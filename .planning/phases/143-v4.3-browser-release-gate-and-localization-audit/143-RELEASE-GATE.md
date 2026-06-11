# v4.3 Release Gate

## Status

Passed on 2026-06-11.

## Frontend Workspace

`/Users/zhdeng/stoa-frontend`

## Evidence

- `npm run lint` - passed
- `npm run build` - passed; Vite emitted the existing large chunk warning only
- `npx playwright test tests/e2e/mobile-responsive.spec.ts tests/e2e/localization-preferences.spec.ts --reporter=line` - passed, 5/5

## Browser Coverage

- Student dashboard, practice, and chat fit a 390x844 mobile viewport.
- Parent overview and child report surfaces fit a 390x844 mobile viewport.
- Tutor queue and AI teacher tools fit a 390x844 mobile viewport.
- Admin dashboard and moderation surfaces fit a 390x844 mobile viewport.
- Authenticated language switching calls the locale preference API, sets German document language, renders translated student navigation copy, and persists through reload.

## Residual Risk

- The production build still reports a pre-existing large chunk warning for the main app bundle.
- v4.3 covers selected core frontend flows, not native apps, translation management, RTL layout, or every copy surface.
- Production deploy/live smoke for the frontend was not part of this local milestone.

