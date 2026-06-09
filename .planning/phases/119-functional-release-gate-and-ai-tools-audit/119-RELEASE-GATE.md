---
phase: 119
milestone: v3.7
status: passed
verified: 2026-06-09
requirement: VERIFY-20
---

# v3.7 Release Gate

## Backend

```bash
PYTHONPATH=src .venv/bin/pytest
```

Result: passed, 307 tests.

```bash
.venv/bin/ruff check src/stoa/db/repositories/ai_teacher_tools_repo.py src/stoa/services/ai_teacher_tools_service.py src/stoa/routers/tutors.py tests/test_ai_teacher_tools.py
```

Result: passed.

## Frontend

```bash
npm run lint
npm run build
npx playwright test tests/e2e/tutor-workflow.spec.ts
```

Results:

- Frontend lint passed.
- Frontend production build passed.
- Playwright tutor workflow passed: 2 tests.

## Notes

- Frontend build and Playwright required escalated filesystem access because the frontend repository is outside the backend workspace root and writes cache/result artifacts.
- Vite emitted the existing large chunk warning.
- Full-repo backend Ruff is not used as a blocking v3.7 gate because it reports unrelated legacy lint debt in modules outside the AI teacher tools scope.
