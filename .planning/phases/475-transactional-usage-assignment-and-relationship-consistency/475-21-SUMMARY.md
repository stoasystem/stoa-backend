---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 21
subsystem: database
tags: [dynamodb, transaction, authorization, teacher-takeover, concurrency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 17
    provides: question owner/status/version CAS and takeover-versus-writer ordering proof
provides:
  - active teacher account-fence condition in the takeover transaction
  - exact canonical-teacher profile role, lifecycle, key, and version condition
  - adversarial rollback proof for suspension, deletion, role drift, and profile-version races
affects: [475-37-teacher-router-types, 475-44-coverage-registry, V9DATA-02, CR-04]

tech-stack:
  added: []
  patterns: [authorized-observation transaction fence, exact canonical-role condition, all-or-nothing lifecycle rollback]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/routers/teachers.py
    - tests/test_phase475_teacher_takeover.py
    - tests/test_phase475_question_state_cas.py

key-decisions:
  - "Takeover binds the authenticated teacher's exact PROFILE key and observed positive version, while the repository independently reads and conditions on the current active account-fence generation."
  - "Only role=teacher and account_status=active satisfy the profile condition; aliases, other canonical roles, suspension, inactivity, deletion, or version drift all return the existing redacted retryable outcome."

patterns-established:
  - "Teacher takeover identity fence: student fence + teacher fence + exact teacher PROFILE observation + question CAS + deterministic session Put in one transaction."

requirements-completed: [V9DATA-02]

duration: 8 min
completed: 2026-07-22
---

# Phase 475 Plan 21: Active Canonical-Teacher Takeover Fence Summary

**Teacher takeover now commits only while the authenticated teacher's active account fence and exact canonical PROFILE observation remain unchanged inside the ownership transaction.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-22T14:33:03Z
- **Completed:** 2026-07-22T14:40:43Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added the active teacher account fence and exact `USER#<teacher>/PROFILE` condition to the same transaction as question ownership and deterministic session creation.
- Bound the profile condition to the authenticated user ID, canonical `teacher` role, `active` lifecycle, and authorization-time positive profile version.
- Preserved the existing structured, coordinate-free 503 response for stale or malformed teacher observations.
- Proved total rollback for suspended, inactive, deleted, role-changed, alias-role, profile-version, and deletion-fence races with the real multi-item transaction adapter.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing active-teacher takeover fence proof** - `fd7b3d2` (test)
2. **GREEN: Fence takeover with active teacher identity** - `b90161f` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_repo.py` - Validates the authorized teacher profile observation and adds teacher fence plus PROFILE conditions to takeover.
- `src/stoa/routers/teachers.py` - Passes the authorized teacher PROFILE key and observed version into the repository claim.
- `tests/test_phase475_teacher_takeover.py` - Executes the expanded transaction and proves lifecycle/version race rollback and redacted failure projection.
- `tests/test_phase475_question_state_cas.py` - Keeps the existing AI-versus-takeover ordering proof on the expanded transaction shape.

## Decisions Made

- The route passes only the exact PROFILE primary key and observed version from authorization facts; the repository rejects missing, mismatched, nonpositive, or otherwise malformed observations before any write.
- The teacher deletion fence is read at the repository boundary and its exact generation is conditioned in the same transaction, so deletion beginning after the read still cancels the claim.
- Conditional loss remains `RETRYABLE` and projects through the pre-existing safe `teacher_takeover_temporarily_unavailable` response; no account, role, version, or storage coordinate is disclosed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migrated the inherited question-CAS transaction fixture**
- **Found during:** Task 1 GREEN regression verification
- **Issue:** Plan 17's two direct repository tests called the takeover primitive without the newly required authorized teacher observation and assumed the former three-operation transaction shape.
- **Fix:** Added one active teacher fence/profile fixture, passed the exact PROFILE key/version, and made the interpreter locate and validate the expanded transaction operations.
- **Files modified:** `tests/test_phase475_question_state_cas.py`
- **Verification:** The 32-test question-CAS, takeover-effect, dispatch, and reply/SLA regression gate passes.
- **Committed in:** `b90161f`

---

**Total deviations:** 1 auto-fixed (1 blocking test-fixture compatibility update).
**Impact on plan:** The compatibility update preserves Plan 17's existing production ordering contract while exercising the new CR-04 fence; no feature or production scope was added.

## Issues Encountered

- The filesystem sandbox denied normal `.git/index.lock` creation. Individually scoped plan files were staged and committed with approved repository permission; normal hooks ran and no verification was bypassed.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_teacher_takeover.py` - 14 passed.
- `.venv/bin/python -m pytest -q tests/test_phase475_question_state_cas.py tests/test_phase475_teacher_takeover_effect.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py` - 32 passed.
- `.venv/bin/ruff check src/stoa/db/repositories/question_repo.py src/stoa/routers/teachers.py tests/test_phase475_teacher_takeover.py tests/test_phase475_question_state_cas.py` - passed.
- `git diff --check` for all four GREEN files - passed.
- Transaction inspection proves one call contains student fence, teacher fence, teacher PROFILE condition, question CAS, and deterministic session Put.
- Commit isolation inspection proves neither TDD commit contains `README.md`, either seed/provision script, or either AWS operator identity file.

## User Setup Required

None - no dependency, credential, schema migration, service, or deployment change is required.

## Known Stubs

None. Stub-pattern matches are existing optional typed fields, retry state, and empty test containers; no new placeholder or unwired production result was introduced.

## Next Phase Readiness

- CR-04 is closed locally: a stale authorization observation cannot assign a suspended, deleted, inactive, role-changed, or concurrently edited teacher.
- V9DATA-02 retains the one-owner/one-session/one-notification behavior while adding atomic teacher lifecycle authority.
- Later teacher-router type cleanup and final Phase 475 evidence plans can consume the stable claim signature and transaction proof.

## Self-Check: PASSED

- All four modified implementation/test files and this summary exist.
- RED commit `fd7b3d2` precedes GREEN commit `b90161f`; both exist with no tracked deletions.
- Exact plan verification, direct regressions, Ruff, stub scan, transaction inspection, commit isolation, and `git diff --check` pass.
- The only remaining non-planning worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
