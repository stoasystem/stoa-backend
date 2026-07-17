---
phase: 473-student-content-privacy-and-practice-integrity
plan: 26
subsystem: practice-integrity
tags: [authorization, practice, teacher, curriculum, privacy]

requires:
  - phase: 473-25
    provides: Direct answer-free challenge pointers and exact immutable canonical challenge rows
provides:
  - Exact current course-and-class teacher authorization for privileged practice answers
  - Strict deterministic assignment-row and read-contract validation with fresh consistent reads
  - Load-once privileged answer resolution with read-only admin access and concealed denials
affects: [473-35, practice-authorization, curriculum-assignments, route-inventory]

tech-stack:
  added: []
  patterns: [mandatory scope dimensions before optional narrowing, deterministic current-fact projection, load-once authorization value]

key-files:
  created:
    - tests/test_phase473_practice_authorization.py
  modified:
    - src/stoa/security/authorization.py
    - src/stoa/security/route_authorization.py
    - src/stoa/db/repositories/question_repo.py
    - tests/test_practice_privacy.py
    - tests/test_student_authorization_matrix.py

key-decisions:
  - "Teacher curriculum-answer reads require both exact current course and exact current class; lesson, subject, and grade can only narrow that already-authorized scope."
  - "The current curriculum assignment is accepted only from its deterministic teacher key with a positive non-boolean version, canonical entity type, strict string read-contract collections, and a fresh active teacher account."
  - "The privileged answer dependency validates one direct-resolver identity/version/hash/scope value and passes that same loaded value to the answer projection; admins retain only the narrow READ purpose."

patterns-established:
  - "Mandatory-first scope evaluation: course and class must both match before any optional curriculum dimension is considered."
  - "Fresh-fact authorization: account and assignment rows are consistently reloaded on every request and malformed projections fail closed."

requirements-completed: [V9PRIV-03]

duration: 15 min
completed: 2026-07-17
---

# Phase 473 Plan 26: Exact teacher course/class answer authorization Summary

**Privileged practice answers now require a fresh exact teacher course-and-class assignment, while admin access remains one global read-only contract and every unauthorized scope stays concealed.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-17T15:29:58Z
- **Completed:** 2026-07-17T15:44:53Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added a 41-test policy and real-route matrix covering exact assignments, subject/grade overlap, cross-course/class access, stale and malformed facts, spoofed scope, actor roles, read-only admin behavior, fresh reads, load-once projection, concealed errors, and redacted audit evidence.
- Made teacher answer authorization require an active actor-bound deterministic assignment row whose exact course and class both match the canonical challenge; optional lesson, subject, and grade fields can only narrow access.
- Preserved a fresh consistent assignment/account read per request, strict non-coercive resource/action/purpose collections, and stable hidden-resource behavior for malformed or unavailable facts.
- Bound the privileged route to one direct-resolver result with matching opaque ID, canonical SHA-256 version/hash tuple, and authoritative course/class coordinates before authorization and answer projection.
- Retained automatic admin access only for `CURRICULUM_ANSWER` + `READ` + `CURRICULUM_ANSWER_READ`; no privileged answer mutation route or role-derived curriculum mutation authority exists.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing exact course/class answer authorization matrix** - `9ce3615` (test)
2. **Task 2: Require exact fresh course-and-class assignment facts** - `d4bf0c1` (fix)
3. **Task 3: Bind the privileged route to one canonical challenge and read-only policy** - `4d951cb` (fix)

## Files Created/Modified

- `tests/test_phase473_practice_authorization.py` - Exhaustive policy, repository, route, inventory, denial, freshness, load-count, and audit-redaction matrix.
- `src/stoa/security/authorization.py` - Deterministic assignment validation, strict read-contract sets, and mandatory exact course/class matching before optional narrowing.
- `src/stoa/db/repositories/question_repo.py` - Consistent exact-key current assignment read with fail-closed entity/version/actor validation.
- `src/stoa/security/route_authorization.py` - Load-once direct challenge identity/version/hash and authoritative coordinate validation.
- `tests/test_practice_privacy.py` - Inherited privileged-answer fixtures aligned with the exact current assignment and canonical challenge contract.
- `tests/test_student_authorization_matrix.py` - Inherited policy fixtures aligned with mandatory course/class scope and deterministic assignment identity.

## Decisions Made

- Course and class are independent mandatory dimensions. A matching subject, grade, or lesson never creates authority, even when both sides otherwise overlap.
- Assignment collections reject scalar, boolean, mapping, blank, duplicate, or coerced members. Authorization compares only exact declared strings.
- The current assignment projection must use `TEACHER_ASSIGNMENT#{teacher_id}` / `CURRICULUM#CURRENT`, canonical entity type, and a positive integer version; malformed rows are treated as absent.
- Missing, wrong-scope, revoked, expired, malformed, and unrelated requests retain the same resource-not-found projection, while anonymous requests stop at authentication before loading challenge content.
- The canonical term remains `teacher`; the one-account/one-role Actor contract and capability-based curriculum mutation boundary are unchanged.

## Verification

- RED gate: **8 failed, 27 passed**, with pytest exit exactly **1** before implementation; failures reproduced subject/grade-only authorization, missing course/class, malformed current facts, spoofing, and malformed loaded scope.
- Task 2 exact policy/current-fact gate: **passed**.
- Task 3 focused route/policy/inventory gate: **63 passed**.
- New Plan 473-26 authorization suite: **41 passed**.
- Combined practice authorization, privacy, student matrix, route inventory, authorization audit, and terminology gate: **208 passed**.
- Targeted Ruff: **passed**.
- `git diff --check`: **passed**.
- Canonical teacher terminology gate and touched-surface denylist: **passed**.
- Recursive response/audit canary checks for answer, explanation, assignment, challenge, course, and class coordinates: **passed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Aligned inherited answer-authorization fixtures with the exact assignment schema**
- **Found during:** Tasks 2 and 3 verification
- **Issue:** Existing positive fixtures represented the superseded subject/grade-only assignment and omitted deterministic assignment identity/version and canonical challenge course/class fields.
- **Fix:** Updated only the inherited test fixtures to express the new exact current course/class contract; production compatibility fallbacks were not added.
- **Files modified:** `tests/test_student_authorization_matrix.py`, `tests/test_practice_privacy.py`
- **Verification:** Focused route/policy gate passes 63 tests and the complete plan-level gate passes 208 tests.
- **Committed in:** `d4bf0c1`, `4d951cb`

**Total deviations:** 1 auto-fixed blocking issue. **Impact:** The fixture updates preserve the new fail-closed production contract and avoid legitimizing stale subject/grade-only authority; no feature scope was added.

## Issues Encountered

- The managed filesystem initially denied Git index-lock creation. Each required commit was rerun through the approved managed escalation path with normal repository hooks enabled.

## Known Stubs

None - the stub scan found only normal typed optional values and test-local accumulators; all plan behavior is wired to current repository, policy, route, projection, and audit paths.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 473-27 can build on a strict privileged answer boundary that no longer treats subject or grade overlap as assignment authority.
- Assignment writers owned by later transactional phases must emit the deterministic current-row schema enforced here; malformed or legacy projections intentionally deny until reconciled.
- No blockers remain for the next Phase 473 gap-closure plan.

## Self-Check: PASSED

- The new authorization suite and all five modified source/test files exist.
- Task commits `9ce3615`, `d4bf0c1`, and `4d951cb` exist in repository history.
- All task acceptance gates and plan-level verification commands pass.
- No tracked files were deleted and the working tree was clean before summary creation.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
