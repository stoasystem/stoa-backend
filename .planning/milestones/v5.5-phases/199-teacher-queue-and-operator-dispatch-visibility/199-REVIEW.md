---
status: clean
phase: 199
milestone: v5.5
reviewed_at: 2026-06-15
---

# Phase 199 Code Review

## Scope

Reviewed changed backend dispatch files:

- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/services/teacher_dispatch_service.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/teachers.py`
- `src/stoa/routers/admin.py`
- `tests/test_teacher_dispatch.py`

## Findings

No open findings remain.

## Fixed During Review

- Fixed immediate post-escalation dispatch to use the fresh escalated question snapshot, avoiding an eventual-consistency read of the pre-escalation question state.
- Made automatic dispatch best-effort from `request-teacher` so student escalation and manual queue visibility still succeed when dispatch profile reads are unavailable.

## Verification

- `uv run pytest tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py -q` passed with 16 tests.
- `uv run ruff check src/stoa/db/repositories/question_repo.py src/stoa/services/teacher_dispatch_service.py src/stoa/routers/questions.py src/stoa/routers/teachers.py src/stoa/routers/admin.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py` passed.
