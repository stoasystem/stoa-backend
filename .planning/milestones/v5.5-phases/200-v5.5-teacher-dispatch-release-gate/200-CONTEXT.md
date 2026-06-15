# Phase 200 Context: v5.5 Teacher Dispatch Release Gate

## Milestone

v5.5 Automatic Teacher Dispatch And SLA Load Balancing

## Release Purpose

Close v5.5 after verifying dispatch planning, conditional claim/reassignment, teacher queue visibility, operator dashboard visibility, and documentation alignment.

## Completed Scope

- Phase 196: dispatch contract.
- Phase 197: planner and candidate ranking.
- Phase 198: dispatch claim and timeout reassignment.
- Phase 199: teacher queue and operator dashboard visibility.

## Verification Inputs

- Focused backend tests: `uv run pytest tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py -q`.
- Ruff: `uv run ruff check src/stoa/db/repositories/question_repo.py src/stoa/services/teacher_dispatch_service.py src/stoa/routers/questions.py src/stoa/routers/teachers.py src/stoa/routers/admin.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py`.
- Code review artifact: `199-REVIEW.md`.

## Deferred Items

- Production scheduled worker/CDK wiring.
- Live staffing calendar integration.
- Frontend operator dashboard implementation.
- Native push dispatch notifications.
- Payroll/compensation automation.
