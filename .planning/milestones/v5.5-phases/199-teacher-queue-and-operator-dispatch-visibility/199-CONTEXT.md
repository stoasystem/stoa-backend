# Phase 199 Context: Teacher Queue And Operator Dispatch Visibility

## Phase Boundary

Make dispatch state visible to teachers and operators while preserving simple, role-safe status for students.

## Existing Context

- `GET /teachers/queue` already returns escalated questions.
- `GET /admin/stats` already exposes aggregate teacher SLA metrics.
- Student/parent surfaces should not see internal teacher ranking or refused candidate details.

## Decisions

- Decorate teacher queue items with dispatch status, assigned-to-me, deadline, attempt count, no-candidate reason, queue age, and SLA risk.
- Hide active non-stale dispatches assigned to another teacher from normal teacher queue views.
- Add `/admin/teacher-dispatch/dashboard` for aggregate queue health, teacher load, dispatch attempts, timeout/reassignment counts, SLA risk, and no-candidate reasons.
- Keep dashboard content-safe by returning IDs and aggregates, not question content.

## Deferred

- Frontend dashboard implementation.
- Live notification provider wiring for dispatch-specific events.
