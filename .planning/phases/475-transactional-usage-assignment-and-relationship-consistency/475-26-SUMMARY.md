---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 26
subsystem: database
tags: [dynamodb, account-deletion, relationships, cas, quiescence]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 23
    provides: status/version-fenced formal parent relationship schema
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 25
    provides: strong cross-account parent identity discovery and two-clean-epoch progression
provides:
  - deletion-fenced exact CAS removal of both formal parent relationship directions
  - student profile parent projection scrub preserving unrelated concurrent fields
  - retry-from-strong-discovery behavior after relationship or profile condition loss
affects: [account-deletion-seal, parent-authorization, V9DATA-03]

tech-stack:
  added: []
  patterns: [entity-level relationship CAS, dirty-pass reset, duplicate-pair suppression]

key-files:
  created:
    - tests/test_phase475_deletion_relationship_scrub.py
  modified:
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/services/account_deletion_service.py

key-decisions:
  - "Delete both formal relationship directions and scrub the exact matching student profile projection in one deletion-generation-fenced transaction."
  - "Treat any row or profile condition loss as retryable dirty debt; only a later strong discovery may supply replacement status/version coordinates."
  - "Deduplicate both discovered directions per branch page so one successful pair transaction is not followed by a stale second mutation."

patterns-established:
  - "Relationship deletion CAS: bind PK/SK, entity, participants, relationship, status, and positive version on both formal rows plus the exact profile projection/version."
  - "Non-revival cleanup: remove authority projections only; never write active or select an alternate parent."

requirements-completed: [V9DATA-03]

duration: 10 min
completed: 2026-07-22
---

# Phase 475 Plan 26: Formal Parent Relationship Deletion Summary

**Parent deletion now removes both formal relationship directions and the matching student profile projection through one exact CAS, then requires two later strong clean epochs before quiescence.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-22T10:26:43Z
- **Completed:** 2026-07-22T10:37:03Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added an entity-specific relationship cleanup transaction guarded by the deleting parent's permanent fence generation.
- Bound both Deletes to exact forward/reverse PK/SK, entity type, parent/student identity, relationship, status, and positive version.
- Reused the closed profile scrub writer to remove only `parent_id`, `relationship`, and `parent_binding_status` behind a strong profile-version CAS while preserving concurrent preferences and all unrelated fields.
- Converted transaction condition loss into retryable row debt and deduplicated the two discovered directions so cleanup restarts only from a fresh strong scan.
- Proved a real CAS loss, lifecycle/status advancement, fresh retry, dirty-pass reset, and two subsequent clean epochs in the production branch.

## TDD Cycle

- **RED:** The new branch proof failed because `account_profile` still issued a generic two-operation single-row deletion instead of the required four-operation relationship transaction.
- **GREEN:** Added exact dual-row/profile cleanup and branch dispatch; the target node and 87 related relationship/account-deletion regressions pass.
- **REFACTOR:** No separate refactor commit was needed; the GREEN implementation was reduced inline to reuse the existing registered profile scrub operation.

## Task Commits

1. **RED: Add failing relationship deletion scrub proof** - `7cdcb2e` (test)
2. **GREEN: Scrub formal parent relationships on deletion** - `8f10715` (feat)

## Files Created/Modified

- `tests/test_phase475_deletion_relationship_scrub.py` - Real strong-scan/transaction fake proving CAS loss, untouched newer state, fresh retry, exact cleanup, unrelated-field preservation, and two clean epochs.
- `src/stoa/db/repositories/account_deletion_repo.py` - Exact formal relationship pair Delete operations and matching student profile projection CAS under the deleting account fence.
- `src/stoa/services/account_deletion_service.py` - Parent relationship dispatch and per-page pair deduplication in the `account_profile` branch.

## Decisions Made

- A discovered forward or reverse row supplies one pair snapshot; both formal rows must match that same status/version tuple or the whole transaction loses without mutation.
- The student profile is strongly read immediately before the transaction and must still name the deleting parent with the same relationship/status and exact version.
- A condition loss is never classified as clean: the branch resets to epoch zero and can proceed only when a later full strong scan rediscovers current coordinates.
- Cleanup only removes the deleted parent's authority projection; it never writes an active status or chooses another parent from conflicting rows.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reused the closed profile writer instead of adding an unregistered direct mutation**
- **Found during:** Task 1 expanded profile CAS regression
- **Issue:** The initial GREEN implementation built the profile `Update` directly inside the new cleanup function, causing the Phase 475 closed profile-writer registry test to fail.
- **Fix:** Extended the existing registered `_parent_profile_scrub_operation` with an optional exact relationship-projection condition and routed the new cleanup through it; `user_repo.py` and its writer registry remained unchanged.
- **Files modified:** `src/stoa/db/repositories/account_deletion_repo.py`
- **Verification:** `tests/test_phase475_profile_version_cas.py` passed 6 tests and the combined post-fix regression passed 88 tests.
- **Committed in:** `8f10715`

---

**Total deviations:** 1 auto-fixed (1 blocking closed-writer constraint).
**Impact on plan:** The fix reduced mutation surface and directly enforced the planned reuse of the narrow profile CAS contract; no scope or authority was broadened.

## Issues Encountered

- The restricted sandbox denied `.git/index.lock` for the RED commit. The same individually scoped commit was retried with repository write approval; normal hooks ran and were not bypassed.

## Verification

- RED gate: the target node failed at the generic two-operation deletion boundary before production changes.
- Exact plan command: 1 passed; Ruff passed all three planned files.
- Relationship transaction, relationship reconciliation, profile writer registry, account deletion, claim fencing, and notification deletion regressions: 87 passed.
- Combined pre-commit regression including the target node: 88 passed.
- `git diff --check HEAD~2..HEAD`: passed.
- Acceptance criteria: both formal rows are absent; CAS loss preserves the newer rows/profile; cleanup never writes active or selects a parent; completion occurs only at clean epochs 1 then 2.
- Normal repository hooks passed for both RED and GREEN commits; no `--no-verify` was used.

## User Setup Required

None - no package, credential, provider, deployment, or external configuration is required.

## Known Stubs

None.

## Threat Flags

None. The cross-account student-profile mutation is the trust boundary explicitly registered as T-475-26-01/T-475-26-02 and is protected by the planned exact CAS and non-revival rules.

## Next Phase Readiness

- CR-10 formal parent relationship identity cleanup is locally closed for both directions and the student profile projection.
- The account deletion seal can now rely on two post-cleanup strong clean epochs rather than treating a stale row-condition loss as absence.
- No AWS or other live provider mutation was performed.

## Self-Check: PASSED

- All three planned source/test files and this summary exist.
- RED commit `7cdcb2e` and GREEN commit `8f10715` exist in the required order.
- Exact plan verification, all acceptance criteria, related regressions, Ruff, diff check, stub scan, and planned threat-surface scan passed.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
