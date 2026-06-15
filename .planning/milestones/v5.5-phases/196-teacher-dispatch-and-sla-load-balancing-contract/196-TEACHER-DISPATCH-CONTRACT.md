# Teacher Dispatch And SLA Load Balancing Contract

## Function Purpose

v5.5 automatically routes student teacher-help requests to eligible teachers/tutors so students wait less and operators can manage SLA risk.

The system dispatches the request. The teacher still writes the reply and resolves the question.

## Not This Feature

- Not AI auto-answering.
- Not automatic practice assignment.
- Not payment/support provider activation.
- Not payroll or compensation automation.

## Existing Flow To Preserve

1. Student calls `POST /questions/{question_id}/request-teacher`.
2. Question becomes escalated and records request/queue timestamps.
3. Teachers can view `GET /teachers/queue`.
4. A teacher calls `POST /teachers/questions/{question_id}/takeover`.
5. Teacher replies and resolves through existing routes.

v5.5 adds dispatch before or alongside step 3 without breaking manual takeover.

## Dispatch States

| State | Meaning |
|-------|---------|
| `unassigned` | Escalated and visible but no teacher has been selected. |
| `dispatched` | System selected a teacher/tutor and set an accept deadline. |
| `accepted` | Dispatched teacher accepted or took over. |
| `active` | Existing `teacher_active` state is in force. |
| `timed_out` | Dispatched teacher did not accept before deadline. |
| `reassigned` | System selected another teacher/tutor after timeout/decline. |
| `declined` | Teacher declined or operator removed assignment. |
| `resolved` | Existing resolved state is in force. |

## Teacher/Tutor Profile Inputs

Minimum matching inputs:

- `teacherId`.
- `role`: teacher, tutor, admin override where allowed.
- `subjects`.
- `status`: available, busy, offline, paused.
- `maxActiveSessions`.
- `activeSessionCount`.
- `recentSlaBucket` or aggregate SLA score.
- `lastDispatchedAt`.
- `lastAcceptedAt`.
- optional `gradeBands`, `languages`, `timezone`.

Initial implementation can derive availability from profile metadata and active sessions without live calendar integration.

## Ranking Inputs

Planner should score candidates by:

- Subject match.
- Availability.
- Active load.
- Recent SLA health.
- Last dispatch time for fairness.
- Queue age and escalation priority.
- Previous assignee avoidance after timeout/decline.

Planner should return selected and refused candidates with reason codes.

## Claim And Reassignment Rules

- Dispatch claim must be conditional on question still being escalated/unassigned or dispatch still being current.
- One request must not be dispatched to two teachers at the same time.
- Manual takeover can accept current dispatch or override when the question is still escalated and visible.
- Timeout worker should mark stale dispatch as `timed_out`, append previous assignee, and select the next eligible candidate.
- If no candidate exists, request remains manually visible with a no-candidate reason.

## Metadata

Question/session metadata should include:

- `dispatch_id`.
- `dispatch_status`.
- `dispatched_teacher_id`.
- `dispatch_attempt_count`.
- `dispatch_reason`.
- `dispatch_deadline_at`.
- `dispatch_updated_at`.
- `previous_dispatch_teacher_ids`.
- `dispatch_no_candidate_reason`.

## Teacher Queue Visibility

Teacher queue should distinguish:

- Dispatched to me.
- Manually available.
- Stale/at-risk.
- Accepted/active.
- No-candidate escalations for admin/operator views.

## Operator Visibility

Operator dashboard should expose:

- Queue age.
- Assigned load by teacher.
- Dispatch attempts.
- Timeout and reassignment counts.
- SLA risk.
- No-candidate reasons.

## Student Visibility

Student-facing status should stay simple:

- Waiting for teacher.
- Teacher assigned.
- Teacher active.
- Teacher replied.
- Resolved.

Do not expose internal teacher ranking or refused candidate details to students.

## Follow-Up Phases

- Phase 197: dispatch planner and candidate ranking.
- Phase 198: automatic dispatch claim and reassignment worker.
- Phase 199: teacher queue and operator dispatch visibility.
- Phase 200: release gate, evidence, and next milestone decision.
