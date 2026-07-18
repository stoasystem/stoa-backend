---
phase: 473-student-content-privacy-and-practice-integrity
plan: 36
subsystem: account-lifecycle-security
tags: [dynamodb, cas, leases, sha256, privacy, pytest]

# Dependency graph
requires:
  - phase: 473-28
    provides: Immutable source-bound Phase 473 evidence and the exact 17-branch deletion registry
  - phase: 473-35
    provides: Permanent account fence, durable deletion command, and exact terminal seal
provides:
  - Opaque owner/version/digest-bound account-deletion claims
  - Per-branch result-version CAS and canonical durable proof digest
  - Strongly reloaded exact-set finalization with UTC lifecycle validation
  - Version-CAS parent-profile child scrub with retryable conflict debt
affects: [473-39, 473-40, V9PRIV-02, account-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns: [opaque lease token, advancing command CAS, canonical SHA-256 proof, row-version scrub]

key-files:
  created:
    - tests/test_phase473_account_deletion_claim_fencing.py
  modified:
    - src/stoa/jobs/account_deletion.py
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/services/account_deletion_service.py
    - tests/test_phase473_account_deletion.py
    - tests/test_phase473_account_deletion_seal.py

key-decisions:
  - "Every deletion mutation carries one opaque owner/generation/version/digest claim; renewal happens before branch work and claim loss stops the worker immediately."
  - "Each durable branch result advances both its result version and the command proof digest; finalization reloads and validates the current exact 17-branch map."
  - "Legacy parent profiles receive only a narrow version-normalization write and must be rescanned; versioned profiles scrub through both account fences plus row-version CAS."

patterns-established:
  - "Deletion CAS chain: claim -> renew -> branch result -> next claim, with no later mutation after conditional loss."
  - "Lifecycle persistence: nonblank parseable timezone-aware UTC is validated at repository boundaries."

requirements-completed: [V9PRIV-02]

# Metrics
duration: 16min
completed: 2026-07-18
---

# Phase 473 Plan 36: Lease-Fenced Deletion Proof And Conflict-Safe Profile Scrub Summary

**Opaque lease ownership, advancing branch-result digests, durable exact-set finalization, UTC lifecycle evidence, and row-version-safe parent child scrubbing now fence the complete 17-branch deletion proof**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-18T14:36:43Z
- **Completed:** 2026-07-18T14:52:30Z
- **Tasks:** 3
- **Files modified:** 6 implementation/test files plus this summary

## Accomplishments

- Replaced command-ID-only continuation with an immutable `DeletionCommandClaim` carrying only opaque command, generation, owner, expiry, version, and proof-digest coordinates.
- Compared stored lease expiry with an explicit current epoch, renewed before branch work, and conditioned every branch result and terminal transition on the same advancing claim chain.
- Added per-result versions and canonical SHA-256 over the exact sanitized durable branch map; terminalization strongly reloads and rejects stale or forged in-memory evidence.
- Defaulted production deletion time to timezone-aware UTC and rejected blank, naive, malformed, and non-string lifecycle values at persistence boundaries.
- Replaced unconstrained parent profile replacement with legacy narrow normalization or version-CAS scrub, retaining conditional conflicts as retryable branch debt.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing deletion-claim, durable-proof, timestamp, and parent-row race tests** — `99a8628` (test, RED)
2. **Task 2: Thread one opaque claim through branch CAS, renewal, and durable finalization** — `191af9b` (feat, GREEN)
3. **Task 3: Scrub parent child references with row CAS and preserve concurrent parent fields** — `d162446` (test, convergence/race coverage)

## Files Created/Modified

- `tests/test_phase473_account_deletion_claim_fencing.py` — Lower-boundary expressions, two-worker takeover, stale-worker stop, durable reload, timestamp, and parent-row race coverage.
- `src/stoa/db/repositories/account_deletion_repo.py` — Claim contracts, explicit-time lease predicates, renewal/result CAS, durable digest/finalizer checks, lifecycle validation, and parent-row CAS.
- `src/stoa/services/account_deletion_service.py` — Claim-only continuation, renewal-before-handler, advancing claim threading, durable reload, UTC clock, and retryable row-conflict debt.
- `src/stoa/jobs/account_deletion.py` — Scheduled and route-background claim acquisition with distinct current and proposed-expiry epochs.
- `tests/test_phase473_account_deletion.py` — Claim-aware scanner fake and production continuation expectations.
- `tests/test_phase473_account_deletion_seal.py` — Claim/digest-bound exact-once terminalization fixtures.

## Decisions Made

- Kept private branch data out of claim tokens and digests' metadata surface; the token contains only opaque identifiers, numeric CAS facts, expiry, and the canonical digest.
- Advanced command version on both renewal and result persistence so every worker mutation belongs to one serial CAS chain.
- Required a strong current command read immediately before finalization and recomputed its digest before validating the exact source-sealed 17 branches.
- Normalized legacy unversioned parent profiles with a narrow version-only update that intentionally returns retryable debt and forces a fresh strong scan.

## Deviations from Plan

### Execution Sequencing Adjustment

- The parent-profile CAS primitive was implemented in Task 2's production commit because the prescribed Task 2 `-k` expression includes `claim`, which selects the entire claim-fencing test file including the parent race. Task 3 then added the planned two-worker, no-later-handler, durable-finalizer, retryable-debt, and fresh-rescan convergence coverage. Scope and final behavior are unchanged.

### Auto-fixed Issues

**1. [Rule 1 - Tooling Bug] Repaired roadmap progress projection**
- **Found during:** Plan metadata commit
- **Issue:** The registered roadmap progress handler matched the four-column execution-order table as if it were a progress table, replacing the phase name/outcome/dependency cells and failing to match the backtick-wrapped Plan 36 checkbox.
- **Fix:** Restored the four-column execution-order semantics with the current 36/40 progress and marked only Plan 36 complete.
- **Files modified:** `.planning/ROADMAP.md`
- **Verification:** Roadmap Phase 473 row retains all four declared meanings and Plan 37-40 remain unchecked.

## Verification

- **RED:** 9 collected tests failed behaviorally; pytest exited exactly `1` with no collection/import errors.
- **Task 2 GREEN:** 25 passed, 2 deselected; targeted Ruff passed.
- **Combined Plan 36 gate:** 53 passed; targeted Ruff passed; `git diff --check` passed.
- **Full repository suite:** 1935 passed, 2 failed. Both failures are deterministic checked-in source-inventory drift for the two intentionally modified mutating sources. Plan 473-39 explicitly owns refreshing those source-sealed inventories, which are outside Plan 36's declared file ownership.

## Issues Encountered

- The full-suite inventory generators correctly rejected stale source digests for `account_deletion_repo.py` and `account_deletion_service.py`. No inventory was refreshed here because Plan 473-39 is the designated reviewed refresh step; functional and scoped Plan 36 gates are green.

## Authentication Gates

None.

## Known Stubs

None. Empty collections in the focused tests are deliberate initial durable states or negative assertions, not production placeholders.

## User Setup Required

None - no package, external provider, deployment, or production mutation is required.

## Next Phase Readiness

- Plan 473-37 can execute independently in Wave 30.
- Plan 473-39 must refresh and re-review the checked source inventories for the two changed deletion sources before the full suite returns green.
- Plan 473-40 can then capture final immutable evidence across all remaining deletion and delivery findings.

## TDD Gate Compliance

- RED commit: `99a8628`
- GREEN commit: `191af9b`
- Convergence coverage commit: `d162446`

## Self-Check: PASSED

- All six implementation/test artifacts and this summary exist.
- Task commits `99a8628`, `191af9b`, and `d162446` exist in repository history.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
