---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 09
subsystem: database
tags: [dynamodb, transactions, rate-limit, idempotency, concurrency]

requires:
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: permanent account fences and durable message-command quota identity
provides:
  - capped transactional chat and hint rate admission
  - payload-bound logical-operation replay and conflict outcomes
  - explicit practice hint idempotency request identity
affects: [475-13-integrated-evidence, V9DATA-04, practice-hints, conversation-messages]

tech-stack:
  added: []
  patterns: [period-scoped opaque operation identity, operation-row plus capped-counter transaction, strong-read contention reconciliation]

key-files:
  created:
    - tests/test_phase475_rate_limit.py
  modified:
    - src/stoa/services/rate_limit.py
    - src/stoa/routers/practice.py
    - tests/test_conversations.py
    - tests/test_practice.py
    - tests/test_curriculum_analytics.py

key-decisions:
  - "Rate-operation IDs are domain-separated SHA-256 values over kind, owner, UTC period, and caller idempotency identity, so raw caller keys are not persisted."
  - "The legacy chat adapter shares the existing CHAT counter, while the conversation message command remains the sole authoritative production chat admission path."
  - "Practice hints require an explicit idempotencyKey bound to the challenge digest; unrelated legacy request fields remain ignored for backward-compatible ownership behavior."

patterns-established:
  - "Rate admission: active account fence, absent payload-bound operation row, and capped counter update commit together; contention always reconciles by strong reads."
  - "Rejected operations have no durable operation row and never increase the counter; admitted operations remain counted across downstream failure and replay."

requirements-completed: [V9DATA-04]

duration: 10 min
completed: 2026-07-21
---

# Phase 475 Plan 09: Capped Idempotent Rate Admission Summary

**Chat and hint limits now admit one payload-bound logical operation exactly once through an account-fenced DynamoDB transaction that cannot increment beyond the configured daily cap.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-21T21:50:07Z
- **Completed:** 2026-07-21T22:00:43Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Replaced unconditional post-increment rejection with one operation-row and capped-counter transaction guarded by `attribute_not_exists(count) OR count < limit`.
- Added closed admitted, replayed, limit, idempotency-conflict, and retryable outcomes with strong-read reconciliation after transaction contention or ambiguity.
- Added an explicit bounded `idempotencyKey` to practice hint requests and bound that identity to the exact challenge digest.
- Kept conversation chat quota ownership in the established message-command transaction, avoiding a second production chat admission path or counter.
- Added deterministic concurrency, repeated rejection, provider retry, changed-payload, day-boundary, request-contract, and inherited message-command regression coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement capped idempotent chat and hint admission** - `093899c` (feat)

## Files Created/Modified

- `src/stoa/services/rate_limit.py` - Typed logical-operation admission, opaque identity construction, capped transaction, strong-read reconciliation, and chat/hint adapters.
- `src/stoa/routers/practice.py` - Explicit hint request model and authorization dependency carrying the required idempotency identity.
- `tests/test_phase475_rate_limit.py` - Transaction shape, exact cap, final-slot concurrency, retry, conflict, and UTC boundary proof.
- `tests/test_conversations.py` - Regression guard that the durable message command remains the authoritative chat quota path.
- `tests/test_practice.py` - Hint request identity, ownership, approval, and missing-key route coverage.
- `tests/test_curriculum_analytics.py` - Existing counter-backed hint ledger regression updated for the explicit operation identity.

## Decisions Made

- Used a domain-separated, length-prefixed SHA-256 operation identity over kind, owner, UTC day, and caller key. This isolates daily namespaces and avoids persisting caller-supplied identifiers.
- Kept the operation row and capped `ADD` update in the same account-fenced transaction. A failed cap condition therefore creates neither an operation row nor another count.
- Reconciled all contention through strong operation and counter reads: matching payload returns replay, changed payload returns a coordinate-free 409, missing operation at the durable cap returns 429, and unresolved dependency state remains retryable.
- Required `idempotencyKey` for hints while continuing to ignore unrelated legacy body fields, preserving the existing rule that body data cannot substitute another student identity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated inherited hint-ledger regression for the required operation identity**
- **Found during:** Task 1 (Implement capped idempotent chat and hint admission)
- **Issue:** `tests/test_curriculum_analytics.py` was not listed in the plan, but its existing hint-route mock used the removed two-argument adapter contract and would no longer exercise the real request shape.
- **Fix:** Added the explicit operation argument to the mock and `idempotencyKey` to the request fixture.
- **Files modified:** `tests/test_curriculum_analytics.py`
- **Verification:** The complete changed regression set passes 107 tests, including the counter-backed hint ledger case.
- **Committed in:** `093899c`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The additional test-only change preserves an inherited route contract directly affected by the planned required idempotency field; no production scope was added.

## Issues Encountered

- Git staging initially hit the workspace sandbox's `.git/index.lock` restriction. The same scoped `git add` and normal hook-enabled commit were rerun with the approved repository permission; no files or verification results changed.

## Verification

- Plan command — 56 passed, 37 deselected; Ruff passed all planned runtime and new test files.
- Complete changed regression set — 107 passed across rate admission, inherited message command, conversations, practice, and curriculum analytics.
- `.venv/bin/mypy src/stoa/services/rate_limit.py` — passed with no issues.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-10 can implement bounded submitted-answer and legacy-unknown projection independently of rate admission.
- Plan 475-13 can include the new lower-boundary rate nodes in Phase 475 integrated evidence.

## Known Stubs

None.

## Self-Check: PASSED

- The new rate-limit test module and both modified runtime files exist in the working tree.
- Task commit `093899c` exists and contains exactly the six intended implementation and regression files with no deletions.
- Every acceptance criterion and the plan-level automated verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
