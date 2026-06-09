# Summary: Phase 121 Backend Curriculum Catalog And Exercise Bank APIs

**Status:** Complete
**Milestone:** v3.8 Full Curriculum Rollout
**Requirement:** CURRIC-02
**Completed:** 2026-06-09

## Delivered

- Added `curriculum_service` to project curriculum catalog, lesson detail, exercises, and progress summaries from existing practice content.
- Added `practice_repo.get_all_challenges` for exercise bank listing by lesson, subject, and topic.
- Added backend routes:
  - `GET /practice/curriculum/catalog`
  - `GET /practice/curriculum/lessons/{lesson_id}`
  - `GET /practice/curriculum/exercises`
  - `GET /practice/curriculum/progress`
- Added preview/inactive content checks so only tutor/teacher/admin callers can inspect non-active curriculum states.
- Added answer-key visibility controls so student curriculum lesson/exercise responses do not expose answer keys.
- Added focused tests in `tests/test_curriculum_rollout.py`.

## Verification

- `PYTHONPATH=src .venv/bin/pytest tests/test_curriculum_rollout.py tests/test_learning_expansion.py tests/test_ai_teacher_tools.py` passed.
- `.venv/bin/ruff check src/stoa/services/curriculum_service.py src/stoa/db/repositories/practice_repo.py src/stoa/routers/practice.py tests/test_curriculum_rollout.py` passed.
