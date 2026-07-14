---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 08
subsystem: security
tags: [authorization, actor, teacher-dispatch, assistance, ai-drafts]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 03
    provides: canonical teacher identity and Actor-only privileged terminology
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 05
    provides: central Actor-ResourceRef-Action-Purpose policy and fresh task, assignment, and capability facts
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 06
    provides: executable route dependencies and authorized-object handoff
provides:
  - Complete Actor and central-policy coverage for all twenty-three canonical teacher routes
  - Minimal queue metadata plus exact dispatch-operator capability enforcement
  - Current-task question, assistance, help-request, note, and draft authorization
  - Load-once indirect request and draft resolution before handler effects
  - Separate AI-tool operator grants with curriculum publication remaining independently authorized
affects: [472-09, 472-10, 473, 475, 478]

tech-stack:
  added: []
  patterns: [teacher portal self policy, current-task claim policy, indirect draft owner resolution, capability-separated AI tooling]

key-files:
  created: []
  modified:
    - src/stoa/routers/teachers.py
    - src/stoa/security/authorization.py
    - src/stoa/security/route_authorization.py
    - src/stoa/services/teacher_dispatch_service.py
    - src/stoa/services/teacher_assistance_service.py
    - src/stoa/services/ai_teacher_tools_service.py
    - src/stoa/db/repositories/ai_teacher_tools_repo.py
    - src/stoa/services/adaptive_learning_service.py
    - tests/test_teacher_availability.py
    - tests/test_teacher_dispatch.py
    - tests/test_teacher_reply_sla.py
    - tests/test_ai_teacher_tools.py

key-decisions:
  - "Queue access returns only bounded dispatch metadata; current dispatch or successful takeover is the first authority for question content."
  - "Claim permits only an active teacher on an unassigned or non-expired actor-dispatched escalated question; reply, resolve, help, and draft mutation require the current owner/task."
  - "Dispatch operations and broader AI tooling use separate exact local capabilities; teacher or administrator role alone grants neither."
  - "AI draft acceptance remains review metadata only and never invokes curriculum author, reviewer, or publisher authority."

patterns-established:
  - "Indirect teacher resource handoff: request and draft identifiers resolve to canonical student/question/session owners before policy, and handlers consume that exact AuthorizedResource."
  - "List policy: self-authorized portal entry points filter each help request or AI draft through fresh current-task facts; authorization-store outage fails the entire request closed."
  - "Teacher current-task actions are asymmetric: dispatched teachers may read, only the takeover owner may respond/resolve, and stale/previous assignments never survive."

requirements-completed: [V9ACCESS-02, V9ACCESS-03]

duration: 20 min
completed: 2026-07-15
---

# Phase 472 Plan 08: Teacher task, assistance, and AI-tool route migration Summary

**Every canonical teacher route now starts from an active Actor and an executable self-, current-task-, assignment-, or exact-capability policy, with indirect help and draft IDs resolved before effects.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-14T23:27:31Z
- **Completed:** 2026-07-14T23:47:24Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Converted all 23 `/teachers` decorators from role/sub checks to executable policy metadata and Actor-derived identity, including queue, dispatch, takeover, reply, resolve, availability, stats, assistance, help requests, notes, and AI draft lifecycle.
- Reduced queue output to operational metadata, rejected plain teachers from dispatch control, and enforced fresh current dispatch/takeover facts for content and mutation.
- Resolved help-request and AI draft identifiers to canonical conversation/question/student owners before handlers, filtering lists to current assignments and returning safe hidden 404, known 403, or dependency 503 before mutation.
- Kept AI draft review isolated from curriculum mutation, while an exact `ai_teacher_tools_operator` grant permits broader tooling without turning teacher/admin role into authority.

## Task Commits

| Task | Description | Commit |
| --- | --- | --- |
| 472-08-01 | Teacher queue, dispatch, takeover, reply, and resolve policy | `3bde104` |
| 472-08-02 | Availability, assistance, help-request, and note policy | `10ddcbb` |
| 472-08-03 | AI teacher draft creation, listing, and lifecycle policy | `95624d8` |
| Regression | Consume authorized AI drafts from adaptive assignment flows | `680ffe7` |
| Regression | Expose exact list and self-update authorization specs | `ff88bca` |

## Files Created/Modified

- `src/stoa/routers/teachers.py` — Actor dependencies, current-task resolvers, item-filtered lists, and authorized handler inputs across the canonical surface.
- `src/stoa/security/authorization.py` — teacher portal/help/draft resource types, dispatch/AI purposes, narrow claim/read/respond/resolve rules, and exact operator capabilities.
- `src/stoa/security/route_authorization.py` — self, operator, indirect help-request, and draft dependencies plus loaded-resource authorization.
- `src/stoa/services/teacher_dispatch_service.py` — bounded queue projection that excludes student content and profile/history fields.
- `src/stoa/services/teacher_assistance_service.py` — consumes the already-authorized question and Actor without role-local visibility fallback or reload.
- `src/stoa/services/ai_teacher_tools_service.py` and `src/stoa/db/repositories/ai_teacher_tools_repo.py` — consume authorized draft/question objects and avoid lifecycle reloading before update.
- `src/stoa/services/adaptive_learning_service.py` — reuses the already-authorized adaptive student scope for accepted AI draft assignment.
- Teacher, AI, notification, and adaptive tests — Actor/fact overrides, positive controls, cross/stale/suspended denials, minimal lists, exact grants, and outage-before-effect coverage.

## Decisions Made

- An unassigned escalated question is claimable by an active teacher, but queue membership itself authorizes no content; a current non-expired dispatch or completed claim is required for content access.
- Dispatch preview/run/reassign require `teacher_dispatch_operator`; broader AI draft access requires `ai_teacher_tools_operator`. Both are current local grants and support exact scoped or explicitly global operational grants.
- Plain teachers can use AI drafts only through a current linked question/task or exact assignment. Creator identity alone does not preserve access after reassignment.
- Accepted AI exercise drafts may be consumed only by an independently authorized adaptive assignment flow; acceptance never publishes or mutates curriculum.
- Phase 475 remains responsible for atomic takeover/session/notification redesign. This plan preserved the existing write sequence and only read its resulting facts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Migrated adaptive AI-draft consumers off removed role-local visibility helpers**
- **Found during:** Plan-level full-suite verification after Task 3
- **Issue:** Adaptive recommendation and assignment flows still called private role/creator helpers removed by the central-policy migration, creating eight new failures and preserving a second authorization model.
- **Fix:** Reused Plan 07's already-authorized student assignment scope, while retaining exact student ownership, accepted status, and practice-draft validation.
- **Files modified:** `src/stoa/services/adaptive_learning_service.py`, `tests/test_adaptive_learning.py`
- **Verification:** `tests/test_adaptive_learning.py`: 19 passed; full suite returned to the 33-failure baseline.
- **Committed in:** `680ffe7`

**2. [Rule 2 - Missing Critical] Added item-level executable specs to list routes**
- **Found during:** Final registered-route classification
- **Issue:** Runtime item filtering was central-policy enforced, but help and draft list dependency metadata exposed only portal-self entry classification.
- **Fix:** Added help-request and AI-draft read specs and distinguished availability update from read metadata.
- **Files modified:** `src/stoa/routers/teachers.py`, `src/stoa/security/route_authorization.py`
- **Verification:** 23/23 registered teacher decorators expose one or more executable specs; focused plan suite remains green.
- **Committed in:** `ff88bca`

**Total deviations:** 2 auto-fixed (2 missing critical authorization integrations). **Impact:** Both close policy-model gaps directly caused or exposed by the migration; no Phase 475 transaction work or unrelated baseline repair was added.

## Issues Encountered

- Two normal regression commit attempts could not create `.git/index.lock` under the managed filesystem. Approved normal retries committed the same verified files; no lock was removed and no hook was bypassed.
- Full-suite observation is **778 passed, 33 failed**, compared with the Plan 472-07 baseline of **766 passed, 33 failed**: **+12 passed, 0 new failures**. The remaining failures are the unchanged AI terminology, strict production Cognito settings, unimplemented reconciliation/route inventory, report settings, and subscription production-fixture families owned by pending work.
- No AWS credentials, network, provider call, production mutation, or takeover/session transaction redesign was used.

## User Setup Required

None - no external service configuration required.

## Verification

- Plan command: `.venv/bin/pytest -q tests/test_teacher_availability.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py tests/test_ai_teacher_tools.py tests/test_student_authorization_matrix.py`: **79 passed**.
- Task 1 gate: **33 passed, 29 deselected**.
- Task 2 gate: **8 passed, 42 deselected**; full availability/matrix: **50 passed**.
- Task 3 gate including curriculum separation: **34 passed, 29 deselected**.
- Teacher plus adaptive regression: **98 passed**.
- Related curriculum, notification, conversation, question, and identity regression: **79 passed**.
- Registered route inspection: **23/23 canonical teacher decorators carry executable authorization specs**.
- Targeted Ruff and `git diff --check`: **passed**.
- Full suite: **778 passed, 33 failed**; delta from baseline is **+12 passed, 0 new failures**.

## Next Phase Readiness

- Ready for Plan 472-09 admin/report/support route migration and Plan 472-10 deterministic route inventory/reconciliation evidence.
- Plans 09-10 remain pending. Phase 472 stays `executing` and is not complete.

## Self-Check: PASSED

- All three tasks, acceptance criteria, plan verification, broader regressions, and positive controls passed; all five implementation/regression commits exist.
- Every canonical teacher decorator has executable policy metadata, and no teacher router/service retains bare `require_role`, `get_current_user`, raw `sub`, or role-local content visibility authorization.
- Cross-teacher, previous/stale, suspended, wrong-student, and repository-outage cases fail before mutation; queue output contains no student profile/history/content.
- The exact milestone name and Phase 472 executing status are unchanged; no Phase 475 transaction scope, AWS/network access, or production mutation was introduced.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
