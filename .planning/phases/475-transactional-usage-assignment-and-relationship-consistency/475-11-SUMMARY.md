---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 11
subsystem: database
tags: [dynamodb, notifications, transactions, recovery, account-deletion]

requires:
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: durable delivery intents, permanent account fences, and provider acceptance-unknown recovery
provides:
  - typed delivery-begin outcomes for begun, claim-lost, proven-deletion, and dependency-retry states
  - ordered transaction-cancellation classification backed by strong fence and intent reads
  - recoverable transient delivery-begin failures with exactly-once healthy retry
affects: [475-13-integrated-evidence, V9DATA-07, notification-delivery]

tech-stack:
  added: []
  patterns: [ordered cancellation reason classification, strong-read ambiguity reconciliation, typed pre-provider transition]

key-files:
  created:
    - tests/test_phase475_delivery_begin.py
  modified:
    - src/stoa/db/repositories/notification_repo.py
    - src/stoa/services/notification_service.py
    - tests/test_phase473_delivery_intent_recovery.py
    - tests/test_phase473_notification_deletion.py

key-decisions:
  - "A permanent delivery cancellation requires both the ordered fence-condition failure and a strong fence read proving deletion_pending or deleted for the exact owner generation."
  - "An exact strong-read effect_inflight row at claim version plus one proves an ambiguous begin committed; all unclassified, malformed, throttled, and timeout failures remain dependency retries."
  - "The sendable precheck verifies only the durable claim; the account fence is decided atomically by the final begin transaction immediately before provider mutation."

patterns-established:
  - "Delivery begin: closed repository disposition first, service cancellation only for PROVEN_ACCOUNT_DELETED."
  - "Transaction ambiguity: reconcile exact committed state by strong read without exposing provider messages or coordinates."

requirements-completed: [V9DATA-07]

duration: 7 min
completed: 2026-07-21
---

# Phase 475 Plan 11: Typed Delivery-Begin Recovery Summary

**Notification delivery now permanently cancels only from ordered transaction evidence plus a strong deleted fence, while dependency failures remain recoverable and healthy retry invokes the provider exactly once.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-21T22:03:54Z
- **Completed:** 2026-07-21T22:11:17Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Added `DeliveryBeginDisposition`, `DeliveryBeginResult`, and `classify_delivery_transaction_failure()` as a closed provider-neutral delivery-begin taxonomy.
- Classified an exact committed-but-ambiguous begin from the strongly read inflight intent, claim/scope condition loss as retryable conflict, and unclassified dependency failures as retryable without cancellation.
- Required an ordered fence cancellation reason plus a strong exact owner-generation fence in `deletion_pending` or `deleted` before terminal account-deletion cancellation.
- Removed the broad account-fence inference from the sendable precheck while preserving the final account-fenced transaction immediately before provider invocation.
- Added deterministic dependency failure, healthy retry, proven deletion, claim loss, malformed cancellation, throttling, timeout, ambiguous commit, and inherited recovery proof.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement typed delivery-begin outcomes and recoverable dependency retry** - `ad58c72` (fix)

## Files Created/Modified

- `src/stoa/db/repositories/notification_repo.py` - Typed begin results, ordered cancellation classification, strong intent/fence reconciliation, and claim-only sendable check.
- `src/stoa/services/notification_service.py` - Cancellation only for proven deletion with separate claim-conflict and dependency-retry routing.
- `tests/test_phase475_delivery_begin.py` - Lower-boundary failure classification, healthy retry, exactly-once provider call, deletion denial, and ambiguous-commit coverage.
- `tests/test_phase473_delivery_intent_recovery.py` - Existing begin-transaction assertion migrated to the typed result contract.
- `tests/test_phase473_notification_deletion.py` - Existing deletion race assertion now supplies explicit proven-deletion evidence.

## Decisions Made

- Required two independent facts for terminal cancellation: the fence operation's exact ordered conditional failure and an authoritative strong read of the same account generation in a permanent deletion state.
- Treated malformed/missing cancellation reasons, nonconditional provider errors, throttling, timeouts, and unreadable dependencies as `DEPENDENCY_RETRY`; exception text never influences classification.
- Reconciled an exact `effect_inflight` row at `intent_version + 1` as `BEGUN`, preserving the no-call window and avoiding a false dependency retry after a committed transaction response was lost.
- Kept the existing provider acceptance-unknown terminalization after provider mutation unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated inherited deletion-race regression to require typed proof**
- **Found during:** Task 1 (Implement typed delivery-begin outcomes and recoverable dependency retry)
- **Issue:** The inherited Phase 473 deletion test injected a broad `AccountDeletionConflict` and therefore encoded the unsafe behavior this plan removes.
- **Fix:** Replaced the broad exception injection with `DeliveryBeginResult(PROVEN_ACCOUNT_DELETED)` so the regression still proves zero provider calls and terminal cancellation from explicit evidence.
- **Files modified:** `tests/test_phase473_notification_deletion.py`
- **Verification:** The complete planned recovery/deletion gate passes 24 tests.
- **Committed in:** `ad58c72`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The test-only adjustment is necessary to preserve the inherited deletion safety proof under the new typed contract; no production scope was added.

## Issues Encountered

- The combined targeted mypy command reports three pre-existing errors in unchanged sections of `notification_service.py` at lines 1282, 1284, and 1616. The new repository and delivery-begin test module pass mypy independently; this unrelated baseline was not expanded into the plan.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_delivery_begin.py tests/test_phase473_delivery_intent_recovery.py tests/test_phase473_notification_deletion.py` — 24 passed.
- `.venv/bin/ruff check src/stoa/db/repositories/notification_repo.py src/stoa/services/notification_service.py tests/test_phase475_delivery_begin.py` — passed.
- `.venv/bin/mypy src/stoa/db/repositories/notification_repo.py tests/test_phase475_delivery_begin.py` — passed with no issues.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-12 can implement completed account-deletion receipt replay independently of delivery begin.
- Plan 475-13 can include the new lower-boundary delivery nodes in the integrated Phase 475 evidence gate.

## Known Stubs

None.

## Self-Check: PASSED

- The new delivery-begin test module and all four modified implementation/regression files exist.
- Task commit `ad58c72` exists and contains the five intended files with no deletions.
- Every plan acceptance criterion and the complete automated verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
