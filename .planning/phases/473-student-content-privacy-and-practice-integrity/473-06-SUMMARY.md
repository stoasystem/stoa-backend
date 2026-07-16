---
phase: 473-student-content-privacy-and-practice-integrity
plan: 06
subsystem: curriculum-answer-authorization
tags: [fastapi, authorization, teacher-scope, curriculum, privacy, openapi]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: Verified Actor, load-once ResourceRef policy, current fact loading, safe denials, and executable route inventory
  - phase: 473-05
    provides: Answer-free previews, durable student attempt results, and explicit privileged-answer schema
provides:
  - Narrow curriculum-answer resource and read purpose with current teacher assignment facts
  - Exact course, class, lesson, subject, and grade scope matching for active teachers
  - Automatic global admin answer read without curriculum mutation authority
  - Explicit typed privileged answer endpoint backed by a load-once challenge dependency
affects: [473-07, 475-assignment-consistency, 478-mobile-practice]

tech-stack:
  added: []
  patterns:
    - Distinct resource and purpose for privileged answer reads
    - Current assignment projection matched only against server-loaded challenge coordinates
    - Hidden-resource equivalence for missing, stale, unrelated, and wrong-scope answer requests

key-files:
  created: []
  modified:
    - src/stoa/security/authorization.py
    - src/stoa/security/route_authorization.py
    - src/stoa/security/route_inventory.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/services/curriculum_service.py
    - src/stoa/services/practice_projection_service.py
    - src/stoa/routers/practice.py
    - tests/test_student_authorization_matrix.py
    - tests/test_practice_privacy.py
    - tests/test_route_authorization_inventory.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Curriculum answer reads use a dedicated resource and purpose; admin automatic access applies only to READ plus CURRICULUM_ANSWER_READ."
  - "Teacher scope is derived only from the load-once challenge and one fresh current assignment projection; every declared coordinate must match and at least one coordinate must be present."
  - "Stale, absent, disabled, unrelated, and wrong-scope teacher answer requests remain indistinguishable from a missing challenge."
  - "Privileged answer access returns one explicit schema and never grants curriculum create, update, delete, archive, or mutation capability."

patterns-established:
  - "Privileged answer dependency: load challenge once, project immutable curriculum coordinates into ResourceRef, load current assignment facts, authorize, and pass the same challenge to the handler."
  - "Answer contract separation: catalog and preview routes stay answer-free; only the dedicated privileged route can serialize PrivilegedPracticeAnswer before a student attempt."

requirements-completed: [V9PRIV-03]

duration: 20 min
completed: 2026-07-16
---

# Phase 473 Plan 06: Scoped teacher and global admin answer access Summary

**Assigned teachers now read only matching curriculum answers through current server-derived scope, while admins receive a narrow global answer read and neither role gains curriculum mutation authority.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-16T11:24:00Z
- **Completed:** 2026-07-16T11:44:00Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Added `CURRICULUM_ANSWER`, `CURRICULUM_ANSWER_READ`, curriculum scope coordinates, fresh teacher assignment facts, and a fail-closed central policy branch.
- Added exact active teacher scope matching across course, class, lesson, subject, and grade coordinates plus the narrow automatic admin READ decision.
- Added `GET /practice/curriculum/challenges/{challenge_id}/answer`, which consumes the already-resolved challenge and returns only `PrivilegedPracticeAnswer`.
- Removed the role-only answer-key helper and preserved answer-free preview contracts regardless of `includeAnswers` query input.
- Extended checked runtime/OpenAPI authorization inventory with governed `challengeId` metadata and the executable curriculum-answer dependency.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add curriculum-answer resource policy and assignment scope facts** - `3143d61` (feat)
2. **Task 2: Expose explicit privileged answer route and remove role-only toggles** - `7471f4e` (feat)

## Files Created/Modified

- `src/stoa/security/authorization.py` - Dedicated resource, purpose, scope coordinates, assignment facts, narrow policy decisions, and hidden denial behavior.
- `src/stoa/security/route_authorization.py` - Load-once privileged challenge dependency with executable inventory metadata.
- `src/stoa/security/route_inventory.py` - Governed challenge identifier compatibility for practice and curriculum answers.
- `src/stoa/db/repositories/question_repo.py` - Consistent current teacher curriculum assignment projection read.
- `src/stoa/services/curriculum_service.py` - Removed the role-only answer-key authorization helper.
- `src/stoa/services/practice_projection_service.py` - Explicit privileged answer projection.
- `src/stoa/routers/practice.py` - Typed privileged curriculum answer endpoint.
- `tests/test_student_authorization_matrix.py` - Teacher/admin positives, exact scope, stale/disabled/wrong-scope, role, outage, and mutation controls.
- `tests/test_practice_privacy.py` - Endpoint, anonymous, hidden existence, load-once, schema, toggle, and mutation-boundary tests.
- `tests/test_route_authorization_inventory.py` and `docs/security/route-authorization-inventory.json` - Runtime/OpenAPI/checked inventory evidence.

## Decisions Made

- Admin automatic answer access is encoded only at the exact curriculum-answer READ/purpose tuple, so it cannot flow into support access or curriculum mutation.
- A teacher assignment may declare one or more authoritative curriculum dimensions; all declared dimensions must match the loaded challenge and at least one must exist.
- Teacher denial never reveals whether a challenge or stale/wrong assignment exists; public responses remain the established safe structured error contract.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 authorization/inventory acceptance gate: **37 passed, 51 deselected**.
- Task 2 privileged/privacy acceptance gate: **43 passed, 30 deselected**.
- Combined authorization, privacy, curriculum operations, and mutation controls: **277 passed**.
- Full Phase 473 privacy/practice/authorization matrix: **227 passed**.
- Full backend suite: **1229 passed** against the requested **1200 passed** baseline.
- Targeted Ruff and `git diff --check`: PASS.
- No ambient AWS, provider, or network access was used by tests.

## Next Phase Readiness

- Plan 473-07 can run the final cleanup, combined regression, OpenAPI, and evidence gate with the privileged answer policy included.
- Phase 475 retains ownership of assignment write consistency; this plan reads the current projection consistently and fails closed during absence or outage.
- No blocker remains for Plan 473-06.

## Self-Check: PASSED

- Every named modified file exists and both task commits are present in repository history.
- All task acceptance criteria, plan verification, Phase 473 matrix, mutation controls, static checks, and the full suite pass.
- Student previews remain answer-free and only the explicit privileged route returns pre-attempt answer content.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
