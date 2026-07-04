---
phase: 235
name: Frontend Curriculum Editor And Migration Console
status: complete
created: 2026-07-05
completed: 2026-07-05
---

# Phase 235 Context: Frontend Curriculum Editor And Migration Console

## Milestone

v5.12 Curriculum Editor And Content Migration Buildout

## Why This Phase Exists

Backend authoring and migration APIs are only useful if internal operators can use them without manual API calls. Phase 235 builds the frontend workbench for users who have backend-granted curriculum capabilities.

## Frontend Reality

- Current frontend has student-facing practice/curriculum pages.
- Current frontend has admin/support/analytics/report operations pages.
- There is no dedicated authorized curriculum operator workbench.
- There is no migration dry-run/apply console.

## Authorization Boundary

Frontend must not decide who can edit. It should render based on backend user/capability responses and API authorization outcomes.

Ordinary teachers/tutors should see no editor mutation affordances or should receive clear missing-permission states if they attempt direct routes.

## Completion Notes

- Implemented in frontend repo `/Users/zhdeng/stoa-frontend`.
- Frontend commit: `dff7430 feat(235): add curriculum operations console`.
- Added `/admin/curriculum` admin route, nav metadata, typed API client, TanStack Query hooks, worklist/editor/review/migration/evidence UI, and focused Playwright coverage.
- Curriculum frontend APIs do not use demo fallback and preserve backend capability enforcement, including explicit 403 missing-permission states.
