---
phase: 473-student-content-privacy-and-practice-integrity
plan: 19
subsystem: storage-integrity
tags: [cleanup, multipart, s3-versioning, dynamodb-ttl, pagination]

requires:
  - phase: 473-18
    provides: Strict provider acknowledgement parsing and create-only immutable promotion
provides:
  - Exact post-mutation multipart UploadId and object VersionId absence proof
  - Durable bounded provider reconciliation and cleanup-job continuations
  - Terminal-or-expired cleanup eligibility with generation-fenced PART-row scrubbing
affects: [473-20, 473-35, 479-provider-integration, 480-deployed-observability]

tech-stack:
  added: []
  patterns: [mutation-plus-reconciliation, exact absence proof, generation-fenced metadata scrub]

key-files:
  created:
    - tests/test_phase473_provider_cleanup.py
  modified:
    - src/stoa/services/attachment_service.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/jobs/upload_cleanup.py
    - tests/test_attachment_security.py

key-decisions:
  - "Provider mutation acknowledgement never advances cleanup; only a complete validated listing that excludes the exact UploadId or VersionId establishes absence."
  - "The 120-second operation lease authorizes takeover only; destructive cleanup requires terminal state or the original 30-minute intent expiry."
  - "PART rows inherit the parent intent expiry and cleanup completion requires a generation-fenced bounded scrub followed by an empty-page proof."

patterns-established:
  - "Mutation plus reconciliation: one bounded mutation attempt is followed by closed, resumable provider listing before durable progress."
  - "Cleanup generation fence: provider progress, reference scans, PART deletion, and completion all remain conditional on the current cleanup version."

requirements-completed: [V9PRIV-02]

duration: 16 min
completed: 2026-07-17
---

# Phase 473 Plan 19: Exact provider absence and cleanup convergence Summary

**Multipart abort, exact-version deletion, and terminal upload cleanup now converge only after bounded provider and repository absence proofs, without shortening the 30-minute student intent lifetime.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-17T15:07:58Z
- **Completed:** 2026-07-17T15:23:57Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added a stateful 13-test cleanup contract covering no-op success, commit-then-raise, exact multi-page targets, malformed/repeating markers, invocation-budget continuation, stale generations, early lease expiry, PART TTL/scrub, candidate isolation, and wraparound.
- Replaced acknowledgement-based abort/delete completion with exact UploadId/VersionId listing state machines that validate item shapes, truncation, marker progress, and bounded durable cursors.
- Restricted destructive candidates and claims to terminal or past-expiry intents while preserving active-operation takeover separately from cleanup.
- Added parent-aligned PART TTL plus generation-fenced bounded deletion and an empty-page predicate required by cleanup completion.
- Hardened job/repository continuation cursors against coordinate coercion while preserving candidate-local isolation and observable global listing failure.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing stateful absence and cleanup continuation tests** - `d0142cb` (test)
2. **Task 2: Require repeated exact provider absence before cleanup progress** - `91c54af` (fix)
3. **Task 3: Restrict cleanup eligibility and complete orphan metadata lifecycle** - `1be5dfc` (fix)

## Files Created/Modified

- `tests/test_phase473_provider_cleanup.py` - Stateful provider/repository cleanup matrix and deterministic continuation/wraparound coverage.
- `src/stoa/services/attachment_service.py` - Exact absence reconciliation, bounded cursors, TTL guard, and PART absence orchestration.
- `src/stoa/db/repositories/attachment_repo.py` - Terminal/expired claims, durable provider cursors, parent-aligned PART TTL, conditional scrub, and completion predicates.
- `src/stoa/jobs/upload_cleanup.py` - Exact opaque candidate cursor validation without private-coordinate coercion.
- `tests/test_attachment_security.py` - Inherited cleanup fakes now model retained/removed provider state and the original intent-expiry contract.

## Decisions Made

- A successful or raised abort/delete call is intentionally ambiguous. Cleanup reconciles the same exact coordinate and advances only when the complete validated listing proves it absent.
- Mutation and listing budgets are recorded independently; a listing budget exhaustion persists its marker pair and returns `deferred`, while malformed/repeating markers return a category-only retry.
- Unexpired `issuing`, `assembling`, and `promoting` intents are not cleanup candidates even when their operation lease expired. They remain eligible for safe operation takeover until the original intent expiry.
- PART cleanup is not inferred from TTL. TTL is a backstop; explicit conditional deletion and a subsequent empty page are required before `cleanup_complete`.

## Verification

- RED gate: **8 failed, 3 passed**, and the wrapper confirmed pytest exit status 1.
- Task 2 exact absence/reconciliation gate: **37 passed, 187 deselected**.
- Task 3 lifecycle/continuation gate: **37 passed, 188 deselected**.
- Complete provider state-machine, new cleanup, and inherited attachment-security suites: **281 passed**.
- Targeted Ruff on all three production paths and the new test module: **passed**.
- `git diff --check`: **passed**.
- Fixed-string production-source privacy-canary denial: **passed**.
- Real S3 multipart/version behavior: **NOT RUN** (Phase 479).
- Deployed scheduler/IaC and production observability: **NOT RUN** (Phases 479/480).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected inherited cleanup fakes that contradicted lost-response semantics**
- **Found during:** Task 2 (Require repeated exact provider absence before cleanup progress)
- **Issue:** Existing fakes raised abort/delete failures while simultaneously listing the exact target as absent, and modeled stale-operation cleanup before the parent intent expired. Those fixtures made safe commit-then-raise convergence indistinguishable from a retained failed mutation and conflicted with D-06.
- **Fix:** Made inherited fakes retain targets on true mutation failure, remove targets on committed mutation, and expire stale-operation fixtures through the original intent TTL.
- **Files modified:** `tests/test_attachment_security.py`
- **Verification:** Combined inherited and new cleanup selectors pass, including candidate-local failure isolation.
- **Committed in:** `91c54af`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fixture correction was required to verify the planned lost-response and TTL contracts; it introduced no production scope beyond Plan 473-19.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- Ready for Plan 473-20 gap closure.
- Real S3 and deployed cleanup schedule behavior remain honestly unclaimed and assigned to Phases 479/480.

## Self-Check: PASSED

- All created and modified key files exist.
- Task commits `d0142cb`, `91c54af`, and `1be5dfc` exist in repository history.
- Every task acceptance gate and the plan-level verification suite pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
