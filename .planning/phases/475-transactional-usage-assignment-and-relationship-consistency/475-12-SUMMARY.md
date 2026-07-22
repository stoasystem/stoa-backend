---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 12
subsystem: auth
tags: [account-deletion, idempotency, fastapi, terminal-receipt, privacy]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 06
    provides: identity-bound account lifecycle and strict relationship persistence
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: permanent deletion fence, terminal command compaction, and stored nested receipt
provides:
  - strict projection of the stored nested terminal deletion receipt
  - side-effect-free real endpoint replay after active identity removal
  - terminal-only completion timestamp with pending-response compatibility
affects: [475-13-integrated-evidence, 478-web-account-lifecycle, V9DATA-08]

tech-stack:
  added: []
  patterns: [nested terminal receipt authority, terminal-aware background suppression, identity-fallback replay]

key-files:
  created:
    - tests/test_phase475_completed_deletion_replay.py
  modified:
    - src/stoa/services/account_deletion_service.py
    - src/stoa/routers/auth.py
    - tests/test_phase473_account_deletion.py

key-decisions:
  - "A complete deletion command is projected only from its validated nested receipt; compacted terminal commands do not need the active command's removed branch registry fields."
  - "DeletionReceipt.is_terminal is the sole route scheduling gate, so pending requests continue once per accepted request while deleted replay schedules nothing."

patterns-established:
  - "Terminal replay: preserve issuer, subject, fingerprint, user, generation, method, path, body, and inventory binding, then validate command_id/deleted/completed_at from the nested receipt."
  - "Public projection: compatibility fields remain stable and completedAt is emitted only for a terminal receipt."

requirements-completed: [V9DATA-08]

duration: 5 min
completed: 2026-07-22
---

# Phase 475 Plan 12: Completed Account Deletion Replay Summary

**The real account-deletion endpoint now replays the original stored `deleted` receipt after identity removal with no new cleanup, claim, fence, or background effects.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-22T00:14:21Z
- **Completed:** 2026-07-22T00:20:05Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added strict terminal receipt validation for the persisted nested `command_id`, exact `deleted` status, and UTC completion timestamp.
- Preserved all immutable verified-identity, fingerprint, generation, request, and inventory checks while accepting the deliberately compact terminal command shape.
- Extended the public receipt with terminal-only `completedAt` and made `DeletionReceipt.is_terminal` suppress continuation scheduling.
- Proved a first real endpoint request can complete after its response is lost, then replay through the post-profile identity fallback with every effect counter unchanged.
- Added fail-closed malformed receipt, fingerprint mismatch, verified identity mismatch, and pending continuation regression coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Return stored deleted receipt without reopening cleanup** - `4a97a3d` (fix)

## Files Created/Modified

- `src/stoa/services/account_deletion_service.py` - Terminal receipt projector, optional completion time, terminal state helper, and compact-command replay validation.
- `src/stoa/routers/auth.py` - Terminal-only completion response and nonterminal-only continuation scheduling.
- `tests/test_phase475_completed_deletion_replay.py` - Real endpoint lost-response replay, zero-effect counters, malformed receipt denial, identity/fingerprint conflicts, and pending scheduling proof.
- `tests/test_phase473_account_deletion.py` - Inherited pending receipt shape updated for the optional completion field and nonterminal helper.

## Decisions Made

- Treated the nested receipt as the only authority for terminal public status and completion time. The top-level complete state selects the terminal path but cannot fabricate the returned outcome.
- Kept active command registry validation for pending/running commands only because the Phase 473 terminalizer intentionally removes `branch_ids` and `branch_contracts` during compaction.
- Used `response_model_exclude_none=True` so existing pending clients retain the same three response fields while terminal clients receive `completedAt`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated the inherited pending receipt contract**
- **Found during:** Task 1 (Return stored deleted receipt without reopening cleanup)
- **Issue:** The Phase 473 replay regression asserted the original three-field dataclass shape and failed after the planned optional completion field was added.
- **Fix:** Extended the inherited assertion to require `completed_at=None` and `is_terminal=False` for pending replay.
- **Files modified:** `tests/test_phase473_account_deletion.py`
- **Verification:** The complete 225-node deletion/auth regression gate passes.
- **Committed in:** `4a97a3d`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The additional inherited test change proves pending compatibility and directly prevents terminal metadata from leaking into nonterminal behavior; no product scope was added.

## Issues Encountered

- The sandbox denied the first `.git/index.lock` creation. The same scoped, hook-enabled commit succeeded after approved repository permission; no hook was bypassed.

## Verification

- Plan command — 71 passed across completed replay, auth lifecycle, and deletion seal tests; Ruff passed every planned runtime/test file.
- Acceptance node gate — 10 passed for lost-response terminal replay, six malformed receipt variants, fingerprint/identity conflict, and pending scheduling.
- Expanded deletion/auth regression — 225 passed across deletion orchestration, claim fencing, seal finalization, lifecycle auth, token security, identity authorization, public error boundaries, and route inventory.
- Expanded Ruff gate over all four changed files — passed.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-13 can bind the real endpoint replay and zero-effect node into integrated V9DATA-08 evidence.
- Phase 478 can render `completedAt` only for the terminal `deleted` response while preserving pending polling behavior.

## Known Stubs

None.

## Self-Check: PASSED

- The new completed-replay test and all three modified runtime/regression files exist.
- Task commit `4a97a3d` exists and contains the four intended files with no deletions.
- Every acceptance criterion, the exact plan verification command, the 225-test expanded regression gate, Ruff, and `git diff --check` pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
