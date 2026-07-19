---
phase: 474-deterministic-verification-and-gated-delivery
plan: 42
subsystem: database
tags: [python, mypy, dynamodb, notifications, websocket, privacy, typing]

requires:
  - phase: 474-07
    provides: object-valued DynamoDB repository boundary and runtime Protocol pattern
  - phase: 474-39
    provides: source-bound mypy split-plan verification conventions
provides:
  - mypy-zero notification and WebSocket repositories without semantic suppression
  - explicit DynamoDB response, item, pagination, delivery-claim, and connection narrowing
  - preserved notification delivery recovery, permanent-account fencing, and realtime cleanup behavior
affects: [474-mypy-closure, notification-delivery, websocket-realtime, account-deletion]

tech-stack:
  added: []
  patterns: [object-valued repository records, operation-specific runtime protocols, fail-closed provider narrowing]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/notification_repo.py
    - src/stoa/db/repositories/websocket_repo.py

key-decisions:
  - "DynamoDB notification and connection responses remain object-valued until string-keyed mapping, item-list, cursor, text, and integer checks establish safe use."
  - "Notification and WebSocket paths validate only the get, put, scan, update, or delete capability invoked by each operation."
  - "Malformed provider responses fail through stable redacted account-deletion conflicts while delivery identity, account fences, and pagination behavior remain unchanged."

patterns-established:
  - "Notification boundary: narrow provider mappings and collections before event, preference, push-token, delivery-intent, or deletion logic consumes them."
  - "Realtime boundary: validate minimal table capabilities and connection identities before persistence, expiration, pagination, or revocation."

requirements-completed: [V9QUAL-04]

duration: 6 min
completed: 2026-07-19
---

# Phase 474 Plan 42: Notification and Realtime Repository Typing Summary

**Notification and WebSocket persistence now uses object-valued DynamoDB boundaries with explicit operation and response narrowing while retaining permanent-account fences, crash-safe delivery recovery, pagination, and realtime cleanup semantics.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-19T18:29:58Z
- **Completed:** 2026-07-19T18:34:10Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Reduced focused mypy diagnostics in both notification and WebSocket repositories to zero without `Any`, casts, ignores, exclusions, missing-import suppression, skips, or xfails.
- Narrowed DynamoDB operations, provider mappings, item collections, cursors, delivery claims, global event identifiers, connection identities, and expiration values before use.
- Preserved notification, WebSocket, delivery recovery, private-store inventory, and boundary-inventory behavior across 131 relevant regressions.

## Task Commits

The task was committed atomically after its RED/GREEN verification cycle:

1. **Task 1 GREEN: type notification and realtime repositories** - `42fd0e1` (fix)

The RED gate was the plan's existing focused mypy command and existing notification/WebSocket runtime contracts. No test source was added for the typing implementation. A blocking cross-plan verification defect discovered during GREEN was repaired separately in `b7735a6` so immutable Phase 473 seals are evaluated from the manifest candidate Git archive while current-HEAD semantic guards remain active.

## Files Created/Modified

- `src/stoa/db/repositories/notification_repo.py` - Fully typed notification, assistance, preference, push-token, delivery-intent, recovery, and deletion persistence boundaries.
- `src/stoa/db/repositories/websocket_repo.py` - Fully typed connection persistence, expiration, scan, and account-revocation boundaries.

## Decisions Made

- Kept table arguments object-valued and validated the minimum operation Protocol at every provider call, preserving small test fakes and least-capability boundaries.
- Converted external mappings into string-keyed repository records only after runtime validation; malformed records use stable coordinate-free dependency errors.
- Required explicit non-empty delivery event and connection identities, and narrowed integer-like lease, version, generation, and expiration values before state transitions.
- Preserved the permanent-account-fence transactions and exact delivery scope/claim comparisons instead of weakening runtime behavior to satisfy typing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Read immutable Phase 473 inventory seals from the manifest candidate**

- **Found during:** Task 1 verification
- **Issue:** The two Phase 473 inventory suites compared immutable publication seals with mutable current-HEAD target sources, so a legitimate Phase 474 typing-only change falsely invalidated the frozen candidate even though the checked Phase 473 evidence was unchanged.
- **Fix:** Updated the inventory tests to load sealed source bytes from the manifest candidate Git archive while retaining current-HEAD semantic mutation guards.
- **Files modified:** `tests/test_phase473_boundary_inventory.py`, `tests/test_phase473_private_store_inventory.py`
- **Verification:** Both inventory suites passed as part of the 131-test relevant regression gate; the checked Phase 473 evidence was not regenerated or modified.
- **Committed in:** `b7735a6`

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking issue).
**Impact on plan:** The fix restores immutable candidate verification without weakening the semantic guards applied to current source. It changes tests only and does not alter Phase 473 evidence.

## Issues Encountered

- The first combined regression invocation was still running when the command wrapper yielded; it was rerun with explicit session polling and completed cleanly with 131 passes.
- The repository-wide mypy gate remains owned by the remaining Phase 474 split plans. Both files in this plan contribute zero focused diagnostics and no residual was suppressed.

## Known Stubs

None. Empty result accumulators, optional records, missing cursors, and optional delivery scope inputs are bounded runtime states rather than placeholder behavior.

## Threat Flags

None. The plan adds no endpoint, authentication path, provider mutation, file-access path, schema, dependency, credential, or delivery authority; it narrows existing persistence/provider boundaries and retains all owner-fence checks.

## User Setup Required

None - no external service configuration required.

## Verification

- Focused mypy passed with no issues in both target files.
- Relevant notification/WebSocket regression passed 131 tests across the named notification deletion and private-delivery suites, delivery recovery, general notifications, WebSocket notifications, teacher availability, and both Phase 473 inventory files.
- Focused Ruff passed.
- Suppression scan found no `Any`, `cast(`, `type: ignore`, `noqa`, or mypy directive in either target.
- `git diff --check` passed; task commit `42fd0e1` contains no tracked-file deletions and only the two declared target files.
- Checked Phase 473 evidence remained unchanged; commit `b7735a6` changed only the two inventory tests and was not amended.
- Production infrastructure, deployment, smoke, rollback, and external provider operations remained exact `NOT RUN`.

## Next Phase Readiness

- Later mypy split plans can reuse the object-valued notification and realtime provider boundaries without weakening current diagnostics.
- The repository-wide mypy gate remains release-blocking until the remaining declared coherent domains reach zero.
- Plan 474-26 remains intentionally incomplete: its infrastructure quarantine was not read or modified, and no 474-26 summary exists.

## Self-Check: PASSED

- Both declared target files and this summary exist.
- Task commit `42fd0e1` and dependency commit `b7735a6` exist and contain no unexpected tracked-file deletions.
- Focused mypy, 131 relevant runtime regressions, Ruff, suppression, diff, stub, and threat-surface scans passed.
- Phase summary count advances from 14 to 15 of 80; Plan 474-26 remains incomplete and has no summary.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
