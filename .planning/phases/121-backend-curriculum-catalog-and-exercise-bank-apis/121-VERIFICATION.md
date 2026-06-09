# Verification: Phase 121 Backend Curriculum Catalog And Exercise Bank APIs

## Commands

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_curriculum_rollout.py tests/test_learning_expansion.py tests/test_ai_teacher_tools.py
.venv/bin/ruff check src/stoa/services/curriculum_service.py src/stoa/db/repositories/practice_repo.py src/stoa/routers/practice.py tests/test_curriculum_rollout.py
```

## Results

- Focused backend tests passed: 15 tests.
- Focused Ruff passed.

## Notes

- Full-repo Ruff still has unrelated legacy lint debt outside this phase's changed surface.
- Curriculum APIs intentionally reuse existing practice identifiers to preserve progress and challenge attempt compatibility.
