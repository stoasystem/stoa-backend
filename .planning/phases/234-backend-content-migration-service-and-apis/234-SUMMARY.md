---
phase: 234
name: Backend Content Migration Service And APIs
status: complete
completed: 2026-07-05
requirements:
  - CURRBUILD-03
commits:
  - 77c6fb2 feat(234): add curriculum migration APIs
---

# Phase 234 Summary

Phase 234 implemented manifest-driven backend curriculum migration so content operators can validate and apply curriculum imports without manual database writes.

## Completed

- Added migration evidence storage primitives to the curriculum ops repository.
- Added `curriculum_migration_service` with manifest normalization, dry-run analysis, apply confirmation, idempotent evidence handling, audit writes, and optional publish pointer/projection updates.
- Added dry-run API at `POST /admin/curriculum/migrations/dry-run`.
- Added apply API at `POST /admin/curriculum/migrations/{migration_id}/apply`.
- Added evidence read API at `GET /admin/curriculum/migrations/{migration_id}`.
- Required `migration_operator` or `curriculum_publisher` capability for migration APIs, with ordinary teacher/tutor refusal preserved.
- Added focused migration tests covering dry-run no mutation, apply, evidence, audit, idempotency, confirmation token mismatch, conflicts, validation failures, and route-level refusal.

## Key Files

- `src/stoa/services/curriculum_migration_service.py`
- `src/stoa/db/repositories/curriculum_ops_repo.py`
- `src/stoa/routers/admin.py`
- `tests/test_curriculum_migration.py`

## Verification

- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_curriculum_migration.py -q` — 19 passed.
- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_curriculum_migration.py tests/test_curriculum_analytics.py -q` — 31 passed.
- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_curriculum_migration.py tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger -q` — 20 passed.
- `.venv/bin/python -m ruff check src/stoa/db/repositories/curriculum_ops_repo.py src/stoa/services/curriculum_migration_service.py src/stoa/services/curriculum_ops_service.py src/stoa/routers/admin.py tests/test_curriculum_migration.py tests/test_curriculum_ops.py` — passed.

## Deviations from Plan

None - plan executed as scoped. Actual import of approved source material remains out of scope until source material is available.

## Next

Phase 235 should implement the frontend curriculum editor and migration console against the Phase 233 and Phase 234 backend APIs.
