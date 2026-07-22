---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 24
subsystem: database
tags: [dynamodb, transactions, rate-limit, idempotency, concurrency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 09
    provides: capped account-fenced rate admission with opaque logical-operation identity
provides:
  - immutable per-operation rate admission receipts
  - expected-counter CAS with bounded contention retry
  - byte-stable replay after unrelated accepted or rejected traffic
affects: [475-42-static-gate, 475-44-coverage, V9DATA-04, CR-09]

tech-stack:
  added: []
  patterns: [operation-owned authoritative receipt, absent-or-expected counter CAS, strong-read duplicate reconciliation]

key-files:
  created: []
  modified:
    - src/stoa/services/rate_limit.py
    - tests/test_phase475_rate_limit.py

key-decisions:
  - "Rate admission operation schema v2 stores decision, exact post-operation count, configured limit, and counter expiry as one immutable receipt in the same transaction as the counter CAS."
  - "Public replay preserves the original admissionStatus and receipt fields while internal disposition remains replayed for control flow."
  - "A missing counter uses attribute-not-exists CAS; an existing counter uses exact expected-count CAS and rereads after contention within the existing three-attempt bound."

patterns-established:
  - "Authoritative replay: read and validate only the operation-owned receipt before consulting the mutable aggregate counter."
  - "CAS admission: compute the next count from a strong read, persist that value on the operation row, and condition the aggregate transition on the exact observation."

requirements-completed: [V9DATA-04]

duration: 7 min
completed: 2026-07-22
---

# Phase 475 Plan 24: Immutable Rate Operation Receipt Summary

**Each admitted chat or hint operation now owns a durable exact counter receipt that remains byte-stable across replay, unrelated traffic, contention, and period rollover.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-22T07:42:18Z
- **Completed:** 2026-07-22T07:49:37Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Replaced the capped additive update with an absent-or-expected counter CAS that stores the exact next count on the operation row in the same transaction.
- Added operation schema v2 receipt fields for the committed decision, post-operation count, limit snapshot, quota period, and counter expiry.
- Made replay project only the immutable operation receipt, preserving byte-equivalent public fields even when the caller's current limit or the shared counter has changed.
- Added bounded CAS retry for concurrent distinct operations and strong-read convergence for exact duplicates or ambiguous transaction results.
- Proved accepted traffic, rejected traffic, distinct-operation concurrency, exact-duplicate concurrency, dependency redaction, and period rollover behavior.

## TDD Cycle

- **RED:** Added immutable receipt fields and interleaving/concurrency assertions; the pre-change implementation failed 5 nodes because operation rows had no receipt and replay returned the mutable count/current limit/replayed status.
- **GREEN:** Persisted and validated the receipt, changed the counter transition to exact CAS, and returned stored receipt fields; all 11 focused nodes pass.
- **REFACTOR:** No separate refactor was necessary; the minimal implementation passed focused, affected-regression, Ruff, and mypy gates.

## Task Commits

1. **RED: Add failing immutable rate receipt tests** - `d4af24f` (test)
2. **GREEN: Persist immutable rate operation receipts** - `99c87da` (feat)

## Files Created/Modified

- `src/stoa/services/rate_limit.py` - Operation schema v2 receipt, stored-receipt replay, exact counter CAS, and bounded contention retry.
- `tests/test_phase475_rate_limit.py` - CAS-aware fake transaction interpreter plus intervening-traffic, concurrency, rollover, and redacted dependency-error proof.

## Decisions Made

- Kept `RateAdmissionDisposition.REPLAYED` as internal control flow while storing `decision=admitted` as the authoritative public receipt, so replay detection remains explicit without changing response bytes.
- Stored `receipt_expires_at` separately from the operation row's DynamoDB TTL. This preserves both the original counter expiry returned to clients and the operation record's retention policy.
- Bumped the operation schema to v2 because the immutable receipt fields are mandatory for safe replay; old incomplete rows fail closed as retryable rather than fabricating an outcome from the current counter.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The GSD requirement handler found the V9DATA-04 traceability row already marked Complete and therefore left its stale top-level checkbox unchecked; the checkbox was aligned manually after the successful handler call.
- The expanded regression emitted one inherited Starlette/httpx deprecation warning; it did not affect behavior or verification.

## Verification

- RED gate: 5 failed and 5 passed before implementation, with failures on missing receipt fields and mutable replay output.
- Exact plan command: 11 passed; Ruff passed both planned files.
- Acceptance criteria nodes: 4 passed for exact-once duplicate concurrency, same-transaction receipt/counter commit, byte-stable replay, and redacted dependency errors.
- Affected Plan 09 regression: 81 passed across rate admission, conversations, practice, and curriculum analytics.
- `.venv/bin/mypy src/stoa/services/rate_limit.py`: success with no issues.
- `git diff --check HEAD~2..HEAD`: passed.
- Normal repository commit hooks ran for both TDD commits; no verification was bypassed.

## User Setup Required

None - no external service configuration, package installation, provider call, deployment, or production mutation was required.

## Known Stubs

None.

## Threat Flags

None. The change narrows an existing DynamoDB trust boundary and introduces no endpoint, authentication path, external effect, file access, or new schema boundary beyond the planned operation-row receipt fields.

## Next Phase Readiness

- CR-09 is closed locally with direct D-13/V9DATA-04 concurrency and replay proof.
- Plans 475-42 through 475-45 can include the v2 receipt fields and exact test nodes in their static, coverage, snapshot, and publication gates.

## Self-Check: PASSED

- Both modified files exist and contain the planned receipt/CAS behavior.
- RED commit `d4af24f` and GREEN commit `99c87da` exist in the required order.
- Every acceptance criterion and the plan-level verification command passes.
- Stub and threat-surface scans found no goal-blocking placeholders or unplanned surface.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
