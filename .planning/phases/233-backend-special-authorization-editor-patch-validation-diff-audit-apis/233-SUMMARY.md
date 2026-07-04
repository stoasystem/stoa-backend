---
phase: 233
name: Backend Special Authorization Editor Patch Validation Diff And Audit APIs
status: complete
completed: 2026-07-05
requirements:
  - CURRBUILD-02
commits:
  - 210010d feat(233): add curriculum editor capability APIs
---

# Phase 233 Summary

Phase 233 implemented the backend curriculum editor authorization and API surface needed for the v5.12 frontend editor.

## Completed

- Replaced broad curriculum authoring role checks with explicit backend-granted curriculum capabilities:
  - `curriculum_author`
  - `curriculum_reviewer`
  - `curriculum_publisher`
  - `migration_operator` reserved for Phase 234
- Added draft patch support at `PATCH /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}`.
- Added validation preview at `POST /admin/curriculum/lessons/{public_lesson_id}/drafts/{version_id}/validation-preview`.
- Added bounded structural diff at `GET /admin/curriculum/lessons/{public_lesson_id}/diff`.
- Added bounded audit-read at `GET /admin/curriculum/lessons/{public_lesson_id}/audit`.
- Expanded curriculum ops tests from broad role expectations to capability-specific author, reviewer, and publisher flows.

## Key Files

- `src/stoa/services/curriculum_ops_service.py`
- `src/stoa/routers/admin.py`
- `tests/test_curriculum_ops.py`

## Verification

- `.venv/bin/python -m pytest tests/test_curriculum_ops.py -q` — 12 passed.
- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_curriculum_analytics.py -q` — 24 passed.
- `.venv/bin/python -m pytest tests/test_curriculum_ops.py tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger -q` — 13 passed.
- `.venv/bin/python -m ruff check src/stoa/services/curriculum_ops_service.py src/stoa/routers/admin.py tests/test_curriculum_ops.py` — passed.

## Deviations from Plan

None - plan executed as scoped. Migration dry-run/apply remains Phase 234.

## Next

Phase 234 should implement the backend content migration manifest, dry-run/apply APIs, evidence records, conflict reporting, and rollback metadata using the reserved `migration_operator` capability.
