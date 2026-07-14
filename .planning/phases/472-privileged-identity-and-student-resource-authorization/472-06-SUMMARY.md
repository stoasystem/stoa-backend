---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 06
subsystem: security
tags: [authorization, actor, student-ownership, questions, conversations, fastapi]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 05
    provides: central Actor-ResourceRef-Action-Purpose policy and current relationship, assignment, and capability facts
provides:
  - Actor-derived self identity for every student, question, and conversation create/list route
  - Executable AuthorizationSpec dependencies on all nineteen registered decorators in the three route families plus teacher-help
  - Load-once canonical owner resolution for student, question, and conversation identifier paths
  - Hidden 404, known 403, authorization-store 503, and owner/relationship/task/capability positive controls
affects: [472-07, 472-08, 472-09, 472-10, 473, 475, 478]

tech-stack:
  added: []
  patterns: [typed FastAPI authorization dependency, canonical Actor self ID, authorized object handoff, pre-stream authorization]

key-files:
  created:
    - src/stoa/security/route_authorization.py
    - tests/test_students.py
  modified:
    - src/stoa/security/authorization.py
    - src/stoa/routers/students.py
    - src/stoa/routers/questions.py
    - src/stoa/routers/conversations.py
    - src/stoa/models/question.py
    - src/stoa/services/moderation_service.py
    - tests/test_questions.py
    - tests/test_conversations.py

key-decisions:
  - "Student self-service always uses Actor.user_id; email, username, Cognito subject, and legacy parent fields never resolve business ownership."
  - "Identifier dependencies resolve the canonical owner once and handlers consume that exact AuthorizedResource rather than reloading caller-controlled IDs."
  - "Conversation teacher authority requires a current linked question/session task; list/create remain self-only and streaming authorization completes before response construction."
  - "Unknown client owner fields are forbidden on question and conversation create bodies so ownership substitution cannot be silently accepted."

patterns-established:
  - "Executable route metadata: each dependency call exposes its concrete AuthorizationSpec tuple in the registered FastAPI dependency tree."
  - "Known-versus-hidden denial: unrelated identifiers return indistinguishable resource_not_found, while known actors lacking exact action/capability receive action_not_allowed."
  - "Fail before effects: resource and policy fact outages become authorization_temporarily_unavailable before DynamoDB writes, notifications, quota mutations, or SSE bytes."

requirements-completed: [V9ACCESS-02, V9ACCESS-03]

duration: 19 min
completed: 2026-07-15
---

# Phase 472 Plan 06: Student, question, and conversation route migration Summary

**Every student, question, conversation, message, stream, and teacher-help identifier now crosses one typed Actor authorization boundary and hands the already-authorized canonical object to its handler.**

## Performance

- **Duration:** 19 min
- **Started:** 2026-07-14T22:41:00Z
- **Completed:** 2026-07-14T23:00:13Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Removed raw `sub`, email/Cognito lookup, broad role, and route-local ownership authorization from all five student and five question decorators; self identity is the stable internal `Actor.user_id`.
- Attached executable central policy dependencies to list/create/read/history/content/message/stream routes, including path and body `conversationId` resolution, strict create-body ownership, formal parent and exact assignment/capability paths, and current teacher task scope.
- Preserved authorized owner, active bidirectional parent, explicitly scoped teacher, current dispatched teacher, and exact administrator content-capability controls while hiding unrelated real resources exactly like random IDs.
- Made authorization-store failures return safe 503 before profile/question/conversation mutation and completed stream authorization before `StreamingResponse` or generator construction.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-06-01 | Actor-authorized student profile, summary, learning-profile, and history routes | `1cab5cb` |
| 472-06-02 | Load-once question create/read/request/feedback/report authorization | `92742c0` |
| 472-06-03 | Actor-owned conversation list/create/read/message/stream and teacher-help authorization | `a8fb58d` |
| Regression | Moderation tests follow the question policy boundary | `ae16066` |
| Regression | Existing route fixtures override canonical Actor dependencies | `d30f691` |

## Files Created/Modified

- `src/stoa/security/route_authorization.py` — reusable typed dependencies, Actor-only create/list checks, dynamic purpose selection, executable specs, and canonical student/question/conversation resolvers.
- `src/stoa/security/authorization.py` — passes the already-loaded value to fresh fact resolution, supports linked conversation question/session facts, and distinguishes known relationships from hidden unrelated resources.
- `src/stoa/routers/students.py` — all five decorators use authorized student/profile objects and never call Cognito/email fallback.
- `src/stoa/routers/questions.py` — create derives ownership from Actor; identifier handlers consume one authorized question.
- `src/stoa/routers/conversations.py` — list/create derive self identity and read/message/stream/body teacher-help IDs authorize before effects or bytes.
- `src/stoa/models/question.py` — rejects undeclared owner substitution fields.
- `src/stoa/services/moderation_service.py` — accepts the already-authorized question so report creation cannot reload a swapped identifier.
- `tests/test_students.py`, `tests/test_questions.py`, `tests/test_conversations.py` — SEC-002 reproductions, real/random hiding, outage-before-mutation, body substitution, and positive controls.
- `tests/test_moderation.py`, `tests/test_learning_expansion.py`, `tests/test_notifications.py`, `tests/test_teacher_availability.py`, `tests/test_teacher_reply_sla.py` — canonical Actor fixture migration and isolation from real AWS clients.

## Decisions Made

- The dependency tree carries all permitted purpose variants as executable `AuthorizationSpec` objects; Plan 472-10 can inventory registered behavior rather than trusting source-text declarations.
- A teacher conversation read is authorized only when the conversation names a question/session whose fresh current task facts name that teacher and the question links back to the same conversation.
- Parent conversation reads use the same formal relationship facts, so an unrelated parent receives hidden 404 and no legacy profile link can authorize access.
- Student message and stream mutation remain self-service operations. A teacher's current-task positive control is bounded to conversation content read; the student AI-message endpoint does not impersonate a teacher message.
- Phase 475's quota, multi-write, takeover, session, and notification transaction boundaries were not changed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Two normal documentation/test commits initially could not create `.git/index.lock` under the managed filesystem. Approved normal retries committed the same verified files; no lock was removed and no hook was bypassed.
- Full-suite observation is **766 passed, 44 failed**. The failures are not hidden: eleven adaptive cases retain the accepted Phase 474 DynamoDB credential/isolation baseline; the remaining failures are pre-existing Wave 0 RED surfaces for unexecuted Plans 472-07 through 472-10 and production-settings fixtures made stale by earlier strict Cognito readiness validation. They were not treated as Plan 472-06 verification success or changed outside this plan.
- No AWS credentials, network, provider call, production mutation, or Phase 475 transaction rewrite was used.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/pytest -q tests/test_students.py tests/test_questions.py tests/test_conversations.py tests/test_student_authorization_matrix.py`: **71 passed**.
- `.venv/bin/pytest -q tests/test_identity_authorization.py tests/test_moderation.py tests/test_parent_children.py tests/test_teacher_dispatch.py`: **115 passed**.
- `.venv/bin/pytest -q tests/test_teacher_availability.py tests/test_teacher_reply_sla.py tests/test_learning_expansion.py tests/test_notifications.py`: **37 passed**.
- Plan Task 1 gate: **47 passed**; Task 2 gate: **18 passed**; Task 3 gate: **10 passed**.
- Registered FastAPI dependency-tree inspection: **19/19 decorators carry executable AuthorizationSpec metadata**.
- Targeted Ruff across every implementation and test surface: **passed**.
- `git diff --check`: **passed**.
- Full suite (observation only): **766 passed, 44 failed** with the limitations recorded above.

## Next Phase Readiness

- Ready for `472-07` to reuse the same typed dependency and authorized-object pattern for practice, adaptive, and parent routes.
- `472-08` can reuse linked question/session facts for teacher and assistance routes; `472-10` can inventory the executable specs already attached here.
- Plans 07-10 remain pending. Phase 472 stays `executing` and is not complete.

## Self-Check: PASSED

- All required artifacts exist, every plan task has an atomic implementation commit, and the complete plan verification is green.
- Every registered decorator in `students.py`, `questions.py`, `conversations.py`, and the teacher-help router exposes executable central-policy metadata with positive and negative controls.
- The exact milestone name, roadmap structure, and Phase 472 executing status remain unchanged; no phase completion was recorded.
- No AWS/network/production mutation or Phase 475 write-transaction scope was introduced.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
