---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 08
subsystem: database
tags: [dynamodb, profile, cas, privacy-scrub, concurrency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 06
    provides: atomic parent relationship/profile projection and strict bidirectional relationship authority
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: permanent account fences and parent-profile child scrub branch
provides:
  - one version/CAS-and-increment primitive for every ordinary profile mutation
  - bounded retry for unrelated profile fields and scrub-priority handling for sensitive linkage
  - closed source-backed registry for every direct USER profile mutation primitive
  - real locale writer versus real privacy scrub barrier-race proof
affects: [475-07-parent-binding-reconciliation, 475-13-integrated-evidence, V9DATA-06]

tech-stack:
  added: []
  patterns: [strong-read bounded profile CAS, narrow scrub-owned field mutation, source-sealed writer registry]

key-files:
  created:
    - tests/test_phase475_profile_version_cas.py
  modified:
    - src/stoa/db/repositories/user_repo.py
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/routers/admin.py
    - src/stoa/services/subscription_service.py
    - tests/test_phase473_account_deletion_claim_fencing.py
    - tests/test_subscription_operations.py

key-decisions:
  - "Unrelated ordinary profile writes retry a strong-read CAS at most three times; a stale ordinary write touching scrub-owned child linkage never replays after CAS loss."
  - "Privacy scrub replaces only changed child collections, removes only matching scalar linkage, and increments the same profile version without a whole-row Put."
  - "The closed registry inventories the three direct profile mutation primitives; admin, subscription, relationship, locale, availability, verification, and student-profile callers compose those primitives instead of writing PROFILE directly."

patterns-established:
  - "Ordinary profile writer: active exact-generation fence plus attribute-exists/version CAS Update with exactly one version increment."
  - "Sensitive conflict priority: writer-first is followed by scrub retry; scrub-first returns the stale sensitive writer as typed retryable without restoring linkage."

requirements-completed: [V9DATA-06]

duration: 14 min
completed: 2026-07-21
---

# Phase 475 Plan 08: Shared Profile Version CAS Summary

**Every ordinary profile writer and the privacy scrub now share an account-fenced version CAS, with real barrier races proving unrelated bytes survive and scrubbed child linkage cannot be revived.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-21T23:43:04Z
- **Completed:** 2026-07-21T23:57:30Z
- **Tasks:** 1
- **Files modified:** 7

## Accomplishments

- Added `ProfileWriteDisposition`, `ProfileWriteResult`, `profile_update_operation()`, and `update_profile_fields_versioned()` with strong reads, exact account-fence generation, exact profile version, narrow updates, and bounded typed retry.
- Replaced the scrub's whole-profile conditional `Put` with a narrow conditional `Update` that removes only matching scalar child linkage, rewrites only changed child collections, and increments version once.
- Initialized all newly materialized profiles at version 1 and made the atomic parent relationship projection increment the same profile version under its existing identity/conflict conditions.
- Routed the administrator user update and both manual/provider subscription-tier transactions through the shared profile operation, eliminating every direct ordinary `USER#*/PROFILE` mutation.
- Added a closed AST-backed writer registry test and real two-thread barriers covering scrub-first and writer-first ordering, exact preference bytes, locale preservation, sibling preservation, bounded contention, and same-sensitive-field scrub priority.

## Task Commits

Each task was committed atomically:

1. **Task 1: Unify parent profile writers and scrub under one version contract** - `c4e1d38` (fix)

## Files Created/Modified

- `src/stoa/db/repositories/user_repo.py` - Shared typed version/CAS operation, bounded writer, sensitive-field retry policy, registry, and versioned relationship projection.
- `src/stoa/db/repositories/account_deletion_repo.py` - Version-1 materialization and bounded narrow parent-profile scrub.
- `src/stoa/routers/admin.py` - Administrator profile updates routed through the shared versioned writer.
- `src/stoa/services/subscription_service.py` - Manual/provider subscription transactions compose the active fence and shared profile CAS operation.
- `tests/test_phase475_profile_version_cas.py` - Real barrier races, transaction shape, bounded retry, legacy initialization, and source-registry seal.
- `tests/test_phase473_account_deletion_claim_fencing.py` - Inherited scrub CAS assertions upgraded for bounded retry and narrow final state.
- `tests/test_subscription_operations.py` - Subscription transaction fixture upgraded with profile versions, account fences, and CAS checks.

## Decisions Made

- Kept ordinary updates field-owned and narrow. Unrelated CAS loss is retried from a fresh strong profile read up to three attempts, while a sensitive-linkage write receives one attempt so it cannot replay after scrub wins.
- Kept scrub priority without retaining a child identifier tombstone in the parent profile: writer-first is removed by scrub's bounded retry; scrub-first rejects the stale sensitive writer by version.
- Sealed direct mutation primitives rather than every business wrapper. This makes a new literal profile `Put`, `Update`, or `update_item` fail the source registry while allowing business transactions to compose the one reviewed operation.
- Preserved the parent-binding transaction's pre-existing student identity, role, and conflict conditions in addition to the new profile-version CAS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Migrated existing admin and subscription profile-write bypasses**
- **Found during:** Task 1 (Unify parent profile writers and scrub under one version contract)
- **Issue:** The required whole-source writer inventory found three ordinary direct profile updates outside the four files named by the plan: the admin user update and the manual/provider subscription-tier transactions. Leaving them direct would make the registry dishonest and allow unrelated profile changes to bypass version/CAS.
- **Fix:** Routed admin updates through `update_profile_fields()` and composed the active-fence condition plus `profile_update_operation()` into both subscription transactions. Added `ConditionCheck` serialization to the subscription transaction adapter and upgraded its deterministic fixture.
- **Files modified:** `src/stoa/routers/admin.py`, `src/stoa/services/subscription_service.py`, `tests/test_subscription_operations.py`
- **Verification:** The source-backed registry finds only the three reviewed direct primitives; 35 subscription tests and the 281-test affected regression gate pass.
- **Committed in:** `c4e1d38`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The additional runtime and fixture changes are required to satisfy the plan's closed writer inventory and two-sided concurrency guarantee; no new endpoint or product behavior was added.

## Issues Encountered

- An optional targeted mypy probe retains seven pre-existing DynamoDB table-capability errors in unchanged `user_repo.py` accessors. The new race test itself has no local typing errors once analyzed with the project package configuration; required pytest, Ruff, and regression gates are green.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_profile_version_cas.py tests/test_phase473_account_deletion_claim_fencing.py` — 20 passed.
- `.venv/bin/ruff check src/stoa/db/repositories/user_repo.py src/stoa/db/repositories/account_deletion_repo.py tests/test_phase475_profile_version_cas.py` — passed.
- Expanded profile/deletion/relationship/subscription/admin/auth regression — 281 passed with two existing dependency deprecation warnings.
- Expanded Ruff gate over all seven changed files — passed.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-07 can build relationship reconciliation on a profile projection that now participates in the shared version CAS.
- Plan 475-13 can include the real profile race and closed writer-registry nodes in integrated V9DATA-06 evidence.

## Known Stubs

None.

## Self-Check: PASSED

- All seven created/modified files exist in the working tree.
- Task commit `c4e1d38` exists and contains the complete implementation and regression set with no deletions.
- Every acceptance criterion, the exact plan verification command, the 281-test affected regression gate, Ruff, and `git diff --check` pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
