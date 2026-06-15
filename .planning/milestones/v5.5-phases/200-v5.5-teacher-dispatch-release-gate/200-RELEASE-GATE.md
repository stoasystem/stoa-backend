# v5.5 Teacher Dispatch Release Gate

**Date:** 2026-06-15
**Milestone:** v5.5 Automatic Teacher Dispatch And SLA Load Balancing
**Rollout state:** dispatch-ready

## Backend Evidence

- Commit: `7f1d759 feat: add teacher dispatch and SLA load balancing`
- Focused tests: `uv run pytest tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py -q` passed with 16 tests.
- Ruff: `uv run ruff check src/stoa/db/repositories/question_repo.py src/stoa/services/teacher_dispatch_service.py src/stoa/routers/questions.py src/stoa/routers/teachers.py src/stoa/routers/admin.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py` passed.
- Code review: `199-REVIEW.md` status `clean` after fixing stale-read dispatch and dispatch best-effort fallback issues.

## Delivered Scope

- Dispatch contract and state model.
- Non-mutating dispatch planner with selected/refused candidate reasons.
- Conditional dispatch claim metadata for escalated questions.
- Timeout reassignment behavior that avoids previous assignees.
- Teacher queue dispatch filtering and SLA summaries.
- Admin dispatch dashboard with aggregate queue age, teacher load, dispatch attempts, timeout/reassignment counts, SLA risk, and no-candidate reasons.

## Privacy And Role-Safety Notes

- Student-facing dispatch state remains simple: waiting, assigned, active, replied, or resolved.
- Teacher queue hides active non-stale dispatches assigned to another teacher from normal teacher views.
- Admin dashboard returns aggregate/operator metadata and does not expose question content.

## Deferred

- Production scheduled worker/CDK wiring for periodic reassignment.
- Live staffing calendar integration.
- Frontend operator dashboard implementation.
- Native push dispatch notifications.
- Payroll/compensation automation.
- Final payment/support external provider activation.
