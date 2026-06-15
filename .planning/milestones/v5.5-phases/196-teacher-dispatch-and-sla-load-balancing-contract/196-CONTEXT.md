# Phase 196 Context: Teacher Dispatch And SLA Load Balancing Contract

## Milestone

v5.5 Automatic Teacher Dispatch And SLA Load Balancing

## Why This Phase Exists

`stoa_docs` includes the student teacher-request flow, teacher queue, teacher takeover, teacher reply, resolve, SLA response tracking, and a risk mitigation note for slow teacher response using multiple teachers and timeout-based reassignment.

The current codebase already has:

- Student escalation through `POST /questions/{question_id}/request-teacher`.
- Manual teacher queue through `GET /teachers/queue`.
- Manual takeover through `POST /teachers/questions/{question_id}/takeover`.
- Teacher reply and resolve routes.
- SLA fields for request-to-takeover, first reply, and resolved duration.
- Notifications for teacher requested, takeover, and reply.

The remaining product gap is automatic routing and reassignment. Students should wait less, teachers should see work targeted to them, and operators should understand queue health.

## Function Purpose

Route student teacher-help requests to the best available teacher/tutor and reassign timed-out requests. The feature improves dispatch and SLA behavior; it does not generate teacher answers.

## Implementation Strategy

Add a dispatch layer around the existing manual workflow:

- Availability/capability profile for teachers/tutors.
- Candidate planner for escalated questions.
- Conditional dispatch claim metadata on the question/session.
- Timeout/reassignment worker.
- Teacher queue and operator visibility updates.

## Code Context

- `src/stoa/routers/questions.py` handles student request-teacher escalation.
- `src/stoa/routers/teachers.py` handles queue, takeover, reply, and resolve.
- `src/stoa/services/teacher_reply_service.py` computes SLA metrics.
- `src/stoa/services/notification_service.py` emits teacher-request lifecycle notifications.
- `tests/test_teacher_reply_sla.py` covers request timestamps, takeover SLA, reply validation, and SLA aggregates.

## Planning Boundary

Phase 196 is a contract phase. Implementation belongs to Phases 197-200.
