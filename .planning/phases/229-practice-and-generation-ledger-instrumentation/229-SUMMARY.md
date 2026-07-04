---
phase: 229
name: Practice And Generation Ledger Instrumentation
status: complete
completed: 2026-07-04
---

# Phase 229 Summary: Practice And Generation Ledger Instrumentation

## Completed

- Instrumented practice answer submissions with `practice_answer` usage events.
- Instrumented lesson completion with `practice_lesson_completion` usage events.
- Instrumented hint requests with counter-backed `hint_request` usage events.
- Instrumented reviewed assignment creation with `reviewed_assignment_generation` usage events.
- Instrumented assignment lifecycle side effects with `assignment_started`, `assignment_completed`, `assignment_skipped`, and `assignment_archived` usage events.
- Added safe metadata allowlist fields needed for assignment/generation support visibility.
- Added focused privacy tests proving raw answers, prompts, and hint text are not copied into ledger calls.

## Files Changed

- `src/stoa/routers/practice.py`
- `src/stoa/services/adaptive_learning_service.py`
- `src/stoa/services/usage_ledger_service.py`
- `tests/test_curriculum_analytics.py`
- `tests/test_adaptive_learning.py`

## Verification

- Phase 229 focused pytest: 4 passed.
- Usage ledger pytest: 8 passed.
- Ruff: All checks passed.

## Deferred

- Multi-action summary aggregation and parent/admin account operations payload compatibility remain Phase 230.
