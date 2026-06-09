# Summary: Phase 122 Student/Parent Curriculum UX And Tutor Signals

**Status:** Complete
**Milestone:** v3.8 Full Curriculum Rollout
**Requirement:** UI-23
**Completed:** 2026-06-09
**Frontend commit:** b562b01

## Delivered

- Added curriculum rollout frontend types for subjects, topics, units, lessons, exercises, catalog, and progress.
- Added frontend API methods for `/practice/curriculum/catalog` and `/practice/curriculum/progress`.
- Added demo fallbacks for math, physics, German, and English curriculum coverage.
- Added `CurriculumRolloutPanel` for active subject count, unit/lesson/exercise depth, progress signals, weak areas, and lesson bank sample.
- Added the rollout panel to:
  - `/practice`,
  - `/parent/children/:childId`,
  - `/tutor/requests/:requestId`.
- Extended Playwright tests for student practice, parent child summary, and tutor request detail surfaces.

## Verification

- `npm run lint` passed.
- `npm run build` passed.
- `npx playwright test tests/e2e/learning-profile.spec.ts tests/e2e/tutor-workflow.spec.ts` passed.
