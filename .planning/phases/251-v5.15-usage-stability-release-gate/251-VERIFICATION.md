# Phase 251 Verification

status: passed

## Final Backend Gate

```bash
.venv/bin/pytest tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_questions.py tests/test_conversations.py tests/test_curriculum_analytics.py tests/test_adaptive_learning.py::test_assignment_generation_and_transition_record_usage_ledger
```

Result:

- `43 passed in 1.18s`

```bash
.venv/bin/ruff check src/stoa/services/core_smoke_service.py src/stoa/services/usage_ledger_service.py src/stoa/routers/admin.py src/stoa/routers/parents.py src/stoa/routers/practice.py src/stoa/routers/questions.py tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_curriculum_analytics.py tests/test_questions.py
```

Result:

- `All checks passed!`

## Frontend Gate

Phase 249 frontend build passed:

- `npm run build`
- Existing Vite chunk-size warning only.

## Worktree Check

Before release docs were written, both backend and frontend worktrees were clean.

## Result

v5.15 local release gate passed with external/live-provider blockers documented.
