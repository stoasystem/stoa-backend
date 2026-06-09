# Release Gate: v4.0 Adaptive Learning Memory And Assignment

**Status:** Passed locally
**Date:** 2026-06-10

## Scope Verified

- Adaptive memory repository, service, and router exist.
- Memory summaries aggregate question, feedback, practice, curriculum, and topic evidence.
- Memory refresh persists durable per-student subject/topic snapshots.
- Recommendations are review-required and explicitly not autonomous decisions.
- Tutor/admin can create reviewed assignments from curriculum exercises or accepted AI exercise drafts.
- Students can start, complete, and skip assignments.
- Parent progress signals include weak areas, recommendations, assigned/completed practice counts, freshness, and assignment summaries.

## Quality Gates

- `.venv/bin/python -m pytest tests/test_adaptive_learning.py -q` -> `3 passed`.
- `.venv/bin/python -m ruff check src/stoa/services/adaptive_learning_service.py src/stoa/db/repositories/adaptive_learning_repo.py src/stoa/routers/adaptive.py src/stoa/main.py tests/test_adaptive_learning.py` -> passed.
- `.venv/bin/python -m pytest tests/test_adaptive_learning.py tests/test_ai_teacher_tools.py tests/test_curriculum_rollout.py tests/test_learning_expansion.py tests/test_parent_children.py -q` -> `99 passed`.
- `.venv/bin/python -m pytest -q` -> `318 passed`.
- `.venv/bin/python -m ruff check src tests` -> failed on pre-existing unrelated lint in `src/stoa/deps.py`, `src/stoa/routers/conversations.py`, and `src/stoa/routers/files.py`; adaptive milestone files passed focused Ruff.

## Residual Scope

- Production deployment and live smoke were not performed.
- Frontend component implementation is outside this backend repository.
- Fully autonomous tutoring, assignment, and long-term sequencing remain out of scope.
- Rich learning analytics dashboards, native mobile apps, production notification delivery, and support integrations remain future scope.
