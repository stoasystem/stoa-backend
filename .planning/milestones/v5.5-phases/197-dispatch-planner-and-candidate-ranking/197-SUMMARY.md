# Phase 197 Summary: Dispatch Planner And Candidate Ranking

## Completed

- Added `src/stoa/services/teacher_dispatch_service.py`.
- Implemented `plan_dispatch()` with selected/refused candidate payloads.
- Added profile normalization for teacher/tutor/admin roles, subject capability, availability, active load, max sessions, SLA bucket, and last dispatch time.
- Added refusal reason codes for unavailable, overloaded, subject mismatch, missing capability, ineligible role, missing ID, and previous timeout.
- Added deterministic ranking by load, SLA health, and last-dispatch fairness.

## Evidence

- `tests/test_teacher_dispatch.py::test_dispatch_planner_ranks_eligible_and_explains_refusals`
- Focused test suite passed: `15 passed`.
- Ruff passed on touched files.
