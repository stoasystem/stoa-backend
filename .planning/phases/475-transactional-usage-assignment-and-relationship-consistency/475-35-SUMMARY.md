---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 35
subsystem: services
tags: [python, mypy, usage-ledger, dynamodb, reconciliation]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 15
    provides: opaque question command digests and atomic admission ledger identity
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 20
    provides: durable terminal proof and exact-once four-row compensation
provides:
  - exact-file mypy closure for the usage-ledger service
  - validated persisted integer conversion for counters, expiry, and event quantities
  - unchanged opaque admission identity and exact reversal accounting
affects: [usage-ledger, question-reconciliation, V9DATA-01, phase-475-verification]

tech-stack:
  added: []
  patterns: [explicit int and integral Decimal narrowing at DynamoDB read boundaries]

key-files:
  created: []
  modified:
    - src/stoa/services/usage_ledger_service.py

key-decisions:
  - "Accept persisted ledger integers only as exact int or finite integral Decimal values, excluding bool and lossy coercions."
  - "Keep counter and quantity values nonnegative while requiring a persisted repair TTL to remain positive."

patterns-established:
  - "Usage-ledger reconciliation narrows object-valued DynamoDB numbers before arithmetic without weakening repository types."

requirements-completed: [V9DATA-01]

duration: 4 min
completed: 2026-07-23
---

# Phase 475 Plan 35: Usage Ledger Service Mypy Closure Summary

**Usage-ledger reconciliation is exact-file mypy-clean with validated DynamoDB integers, opaque question identity, and exact-once terminal compensation preserved.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-23T08:36:33Z
- **Completed:** 2026-07-23T08:40:45Z
- **Tasks:** 1
- **Files modified:** 1 production file

## Accomplishments

- Removed all four real mypy diagnostics from `usage_ledger_service.py` without ignores, casts, configuration changes, broad `Any`, or dependency changes.
- Narrowed stored counter counts, repair expiry, and ledger quantities through one exact integer boundary that supports valid DynamoDB `Decimal` values.
- Preserved the opaque question command digest as the event identity and left the terminal reversal delegation unchanged.
- Retained original audit quantities on reversed events while excluding them from active ledger totals.

## Task Commits

1. **Task 1: Eliminate usage-ledger service mypy diagnostics** - `2db3ddd` (fix)

## Files Created/Modified

- `src/stoa/services/usage_ledger_service.py` - Exact persisted integer narrowing for reconciliation counters, expiry, and event quantities.
- `.planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-35-SUMMARY.md` - Execution evidence and plan close-out.

## Decisions Made

- Accepted only Python integers or finite integral DynamoDB `Decimal` values at persisted accounting boundaries; booleans, fractional values, and negative values fail closed instead of being silently coerced.
- Kept zero valid for absent/nonnegative counters and quantities to preserve existing reconciliation semantics, while requiring an explicitly persisted TTL to be positive.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The sandbox initially denied creation of `.git/index.lock`. The exact single-file stage and commit were retried with repository write approval; normal hooks ran and were not bypassed.

## Verification

- Exact-file mypy: `Success: no issues found in 1 source file`.
- Exact plan regression: 24 passed across question admission and question reconciliation.
- Usage-ledger service regression: 12 passed.
- Ruff over the modified service file: passed.
- `git diff --check` over the modified service file: passed.
- Normal commit hooks: passed.
- Commit isolation: task commit contains only `src/stoa/services/usage_ledger_service.py`; the five user-owned parallel files were neither staged nor committed.

## User Setup Required

None - no dependency, credential, provider call, migration, deployment, or external configuration is required.

## Known Stubs

None.

## Threat Flags

None. The only touched trust boundaries are the planned ledger-quantity tampering and opaque-identity boundaries; exact integer narrowing and unchanged digest/reversal paths satisfy their mitigations.

## Next Phase Readiness

- The usage-ledger service now passes unfiltered exact-file mypy after opaque admission and terminal recovery landed.
- Phase 475 aggregate verification can consume the unchanged ledger identity, audit quantity, active-total, and exact compensation contracts.

## Self-Check: PASSED

- The modified production file and this summary exist.
- Task commit `2db3ddd` exists and contains only `src/stoa/services/usage_ledger_service.py`, with no tracked deletions.
- Exact mypy, both planned regression suites, usage-ledger regressions, Ruff, diff check, stub scan, threat-surface scan, and commit-isolation checks passed.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-23*
