---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 04
subsystem: database
tags: [dynamodb, transactions, teacher-takeover, concurrency, idempotency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 01
    provides: versioned questions, active account fences, and durable transaction conventions
provides:
  - one account-fenced transaction for teacher ownership and deterministic session creation
  - typed claimed, replayed, already-claimed, and retryable takeover outcomes
  - identity-safe structured 409 projection for concurrent losers
affects: [475-05-teacher-notification-recovery, 475-13-integrated-evidence, V9DATA-02]

tech-stack:
  added: []
  patterns: [domain-separated deterministic identities, strong-read contention reconciliation, conditional owner-session transaction]

key-files:
  created:
    - tests/test_phase475_teacher_takeover.py
  modified:
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/routers/teachers.py
    - src/stoa/security/authorization.py
    - tests/test_teacher_dispatch.py
    - tests/test_teacher_reply_sla.py

key-decisions:
  - "Teacher takeover claim identity is a domain-separated digest of question and teacher, and the sole session identity is derived from that durable claim."
  - "The account fence, exact question status/version, current dispatch owner/deadline, ownership transition, and absent deterministic session are checked in one transaction."
  - "Only the exact winning teacher may authorize a teacher-active CLAIM replay; concurrent losers receive a coordinate-free 409 and other teachers retain concealed-resource behavior."

patterns-established:
  - "Takeover transaction: active account fence, conditional versioned question update, and absent deterministic session put commit together."
  - "Takeover reconciliation: strong question/session reads replay the exact winner; mismatched ownership returns no winner identity."

requirements-completed: [V9DATA-02]

duration: 9 min
completed: 2026-07-21
---

# Phase 475 Plan 04: Atomic Teacher Takeover Summary

**Teacher takeover now assigns one owner and one deterministic session in a single account-fenced transaction, with zero loser side effects and identity-safe replay/conflict outcomes.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-21T23:30:45Z
- **Completed:** 2026-07-21T23:39:45Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `TeacherTakeoverDisposition`, `TeacherTakeoverResult`, deterministic claim/session identity helpers, and `claim_teacher_takeover()`.
- Joined the active account fence, exact question state/version, active dispatch owner/deadline, ownership/SLA update, and absent session put in one DynamoDB transaction.
- Reconciled contention through strong question/session reads so the exact winner replays the original session without another write while every concurrent loser receives a generic structured 409.
- Removed the route's unconditional status update, independent session creation, random session identity, and takeover notification; notification recovery remains owned by Plan 475-05.
- Added real barrier concurrency, same-winner HTTP replay, transaction-shape, stale/wrong dispatch, privacy, dispatch regression, SLA regression, and authorization regression coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement atomic teacher claim and session** - `287bee0` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_repo.py` - Typed takeover results, deterministic identities, conditional transaction, and strong-read replay classification.
- `src/stoa/routers/teachers.py` - Atomic claim routing with stable 200/409/503 projection and no notification side effect.
- `src/stoa/security/authorization.py` - Narrow same-winner CLAIM replay authorization for the exact active owner and durable claim/session.
- `tests/test_phase475_teacher_takeover.py` - Barrier race, unique owner/session, zero-write replay, dispatch denial, and private loser proof.
- `tests/test_teacher_dispatch.py` - Existing dispatch ownership and suspended-teacher regressions migrated to the typed claim boundary.
- `tests/test_teacher_reply_sla.py` - Existing takeover timestamp/SLA regression migrated to the atomic claim input.

## Decisions Made

- Derived the claim from exact question and teacher identities, then derived the session from that claim. Retry therefore cannot create a new random session.
- Preserved legacy versionless question compatibility with an `attribute_not_exists(version)` condition that initializes version 1; versioned rows compare and increment the exact current positive version.
- Required an unexpired exact dispatch assignment for dispatched questions. Wrong owners and stale assignments fail before any transaction or session write.
- Allowed CLAIM replay for `teacher_active` only when the actor is the exact persisted owner and both durable claim/session identities exist; this enables winner retry without broadening access for other teachers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added narrow same-winner authorization replay**
- **Found during:** Task 1 (Implement atomic teacher claim and session)
- **Issue:** The existing CLAIM policy accepted only `escalated` questions, so the route could not satisfy the planned 200 response for the winning teacher's retry after the question became `teacher_active`.
- **Fix:** Permitted CLAIM only for the exact persisted active owner when deterministic claim and session identities are present; unrelated teachers remain denied and concealed.
- **Files modified:** `src/stoa/security/authorization.py`, `tests/test_phase475_teacher_takeover.py`
- **Verification:** Same-winner HTTP retry returns the identical session with zero writes; the expanded authorization/takeover suite passes 83 tests.
- **Committed in:** `287bee0`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The narrow authorization change is required for the plan's explicit winner-retry contract and does not disclose the winner to another teacher.

## Issues Encountered

- Targeted mypy passes for the changed repository and authorization policy. `src/stoa/routers/teachers.py` retains its pre-existing 50 unrelated module-level type errors; the newly changed takeover lines add none.

## Verification

- Plan command — 24 passed across barrier takeover, dispatch, and teacher SLA suites; Ruff passed all planned runtime and new test files.
- Expanded question/admission/replay/authorization/takeover regression — 119 passed.
- Authorization/takeover regression — 83 passed.
- `.venv/bin/mypy src/stoa/db/repositories/question_repo.py src/stoa/security/authorization.py` — passed with no issues.
- `git diff --check` — passed.
- Acceptance criteria — exactly one 200 and one generic 409, one matching owner/session, identical zero-write winner replay, no winner identity or notification in loser execution, and stale/wrong dispatch denial all passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 475-05 to add one claim-keyed takeover notification with winner-owned recovery without reopening teacher competition.
- Plan 475-13 can include the new barrier and lower-boundary transaction nodes in integrated V9DATA-02 evidence.

## Known Stubs

None.

## Self-Check: PASSED

- The created takeover concurrency test and all five modified runtime/regression files exist.
- Task commit `287bee0` exists and contains exactly the six intended files with no deletions.
- Every task acceptance criterion and the plan-level automated verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
