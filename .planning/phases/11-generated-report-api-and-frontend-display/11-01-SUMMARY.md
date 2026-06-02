---
phase: 11-generated-report-api-and-frontend-display
plan: 01
subsystem: backend-frontend
tags: [reports, parent-api, parent-frontend, generated-reports]
requires:
  - phase: 10-scheduled-job-orchestration
    provides: Stored generated report records and report statuses
provides:
  - Generated weekly report API detail fields
  - Parent-safe pending and failed report states
  - Frontend generated report rendering
  - Frontend e2e coverage for generated, missing, email-failed, pending, and failed states
affects: [backend-report-verification, frontend-report-verification]
tech-stack:
  added: []
  patterns:
    - Parent report state mapping from stored report status
    - Frontend graceful rendering for partial generated report records
    - Parent-safe error display without raw generation failure messages
key-files:
  created: []
  modified:
    - src/stoa/routers/parents.py
    - tests/test_parent_children.py
    - /Users/zhdeng/stoa-frontend/src/types/parentReport.ts
    - /Users/zhdeng/stoa-frontend/src/pages/parent/ChildReportPage.tsx
    - /Users/zhdeng/stoa-frontend/tests/e2e/parent-dashboard.spec.ts
key-decisions:
  - "`generation_claimed` reports render as pending rather than available."
  - "`generation_failed` reports render as failed with a parent-safe message."
  - "Raw generation error messages are not exposed to the parent response or rendered by the frontend."
  - "Week-specific report lookups recheck the returned student id before exposing a report."
patterns-established:
  - "Phase 12 can verify parent report API behavior against available, missing, pending, failed, and email-failed states."
  - "Phase 13 can extend the focused frontend state tests already covering the generated report page."
requirements-completed: [API-01, API-02, API-03, FRONT-01, FRONT-02, FRONT-03, FRONT-04]
duration: 65min
completed: 2026-06-02
---

# Phase 11 Plan 01 Summary

**Generated report API and parent display**

## Accomplishments

- Extended the parent report API response with week end, stats, summary, strengths, weak topics, recommendation items, teacher note, generated timestamp, email status, report status, and selected error classes.
- Added API state mapping for available, missing, pending, failed, and email-failed report records.
- Preserved parent-child ownership checks and added a week-specific child id recheck before returning a report.
- Updated the parent frontend report type contract to match the generated report response.
- Reworked the parent report page to render generated report summary, week range, metrics, weak topics, recommendations, generated timestamp, email status, and clear report notes.
- Added e2e coverage for generated report, missing report, email-failed, generation-pending, and generation-failed states.

## Task Commits

1. **Backend generated report API** - `5e9adcf` (`feat(11): expose generated parent reports`)
2. **Frontend generated report display** - `3700955` (`feat(11): render generated parent reports`)

## Verification

- `uv run --extra dev pytest tests/test_parent_children.py -q` - passed, 60 tests
- `uv run --extra dev ruff check src/stoa/routers/parents.py tests/test_parent_children.py` - passed
- `/Users/zhdeng/stoa-frontend`: `npm run build` - passed, with existing chunk-size warning
- `/Users/zhdeng/stoa-frontend`: `npm run lint` - passed
- `/Users/zhdeng/stoa-frontend`: `npm run test:e2e -- tests/e2e/parent-dashboard.spec.ts` - passed, 6 tests

## Issues Encountered

- Code review found `generation_claimed` reports were initially exposed as available. Fixed by mapping them to pending with a safe progress message.
- Code review found the week-specific route relied on repository filtering without rechecking returned `student_id`. Fixed with a local child id guard.
- Code review found raw generation error text could be exposed or rendered. Fixed by returning `generationErrorMessage: null` and rendering only safe state messages.
- Frontend e2e strict mode found repeated safe messages in the pending and failed views. Fixed by tightening the assertions to exact badge text and explicit safe-message counts.

## Next Phase Readiness

Phase 12 can consolidate backend report-flow verification across aggregation, generation, storage, idempotency, email failure, and parent API state behavior.
