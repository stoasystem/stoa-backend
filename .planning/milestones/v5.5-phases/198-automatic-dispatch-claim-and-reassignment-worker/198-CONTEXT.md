# Phase 198 Context: Automatic Dispatch Claim And Reassignment Worker

## Phase Boundary

Add safe automatic dispatch claim and timeout reassignment around the existing escalated-question workflow.

## Existing Context

- `question_repo.update_status()` updates question rows.
- `teachers.takeover()` already transitions escalated questions to `teacher_active`.
- Existing SLA helpers compute request-to-takeover and reply timing.

## Decisions

- Add `question_repo.update_status_conditionally()` so dispatch claims fail closed when another worker has already assigned the question.
- Keep question status as `escalated` while dispatch is pending; dispatch state lives in `dispatch_status`.
- Treat manual takeover by the dispatched teacher as acceptance; block non-stale takeover by other teachers.
- Reassignment appends previous assignees and avoids selecting teachers who already timed out.

## Deferred

- Background scheduler/CDK worker wiring for production periodic reassignment.
- Native push dispatch notification delivery.
