---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 12
subsystem: auth
tags: [dynamodb, capability-lineage, reconciliation, audit, authorization]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: canonical privileged identity inventory and fresh Actor grant resolution
provides:
  - Immutable capability revisions with one conditional current pointer per capability and scope
  - Conflict-wide grant quarantine with replay-safe repository and audit application
  - Permanent restore non-revival and explicit next-generation manager-approved regrant
affects: [phase-474-testing, phase-475-transactions, privileged-identity-operations]

tech-stack:
  added: []
  patterns: [immutable grant history, conditional current pointer, deterministic tightening replay]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/capability_repo.py
    - src/stoa/security/reconciliation.py
    - src/stoa/services/privileged_identity_service.py
    - src/stoa/routers/admin.py
    - scripts/reconcile_privileged_identities.py
    - tests/test_privileged_identity_reconciliation.py
    - tests/test_identity_authorization.py

key-decisions:
  - "Authorize only an active current pointer joined to its exact immutable grant revision; historical and shadowed legacy rows never broaden authority."
  - "Capability restoration is not a state transition: a new manager command and grant identity must create the next lineage generation."
  - "Construct the concrete apply adapter only after every explicit non-production CLI authorization gate passes."

patterns-established:
  - "Reconciliation replay recognizes only the exact last_action_id on the revoked current pointer."
  - "Legacy capability rows remain readable only when exactly one valid active row exists and no current pointer shadows the lineage."

requirements-completed: [V9AUTH-04]

duration: 13 min
completed: 2026-07-15
---

# Phase 472 Plan 12: Conflict-wide Capability Quarantine and Non-revival Summary

**Every conflicted privileged identity now loses all current capability authority through an immutable, conditionally advanced grant lineage that historical restore operations cannot revive.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-15T12:39:00Z
- **Completed:** 2026-07-15T12:52:34Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Reconciliation plans removal of every snapshot grant for every non-exact identity and projects zero remaining current grants.
- Capability state now uses immutable generation/version revisions plus one exact current pointer; stale transitions, duplicate legacy rows, and shadowed history fail closed.
- The concrete repository adapter conditionally revokes once, repairs a missing audit on replay, and never revokes a later replacement generation.
- Capability restore is mutation-free and returns `409 capability_regrant_required`; only a new active `admin_identity_manager` command and new grant ID can create the next generation.
- CLI apply remains unavailable by default and in production, and constructs collaborators only after exact non-production, confirmation, run-approval, factory, and config gates pass.

## Task Commits

Each task was committed atomically:

1. **Task 1: Introduce immutable grant lineage and revoke all non-exact grants** - `c425371` (feat)
2. **Task 2: Wire concrete replay-safe apply and eliminate restore revival** - `cd4037f` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/capability_repo.py` - Current-pointer and immutable-revision grant model, atomic legacy migration, conditional revoke, and next-generation regrant.
- `src/stoa/security/reconciliation.py` - Conflict-wide removal planning and concrete repository-backed tightening adapter.
- `src/stoa/services/privileged_identity_service.py` - New-command revoke wiring and mutation-free restore contract.
- `src/stoa/routers/admin.py` - Explicit command ID and expected generation request contracts.
- `scripts/reconcile_privileged_identities.py` - Strict authorized non-production adapter construction boundary.
- `tests/test_privileged_identity_reconciliation.py` - Classification, lineage, migration, replay, stale replacement, restore, privacy, and apply-gate proofs.
- `tests/test_identity_authorization.py` - Fresh Actor grant lifecycle regression for the immutable model.

## Decisions Made

- A current pointer is the sole authority once present; immutable history is evidence, never an authorization fallback.
- Ambiguous legacy lineages deny all grants and cannot be migrated until ambiguity is resolved.
- A revoked pointer may be replayed only for its exact `last_action_id`; any different or newer state is a conflict and remains untouched.
- Account/provider restoration changes identity availability only and never changes capability lineage.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The default uv cache path remains read-restricted in the managed sandbox. Verification used `UV_CACHE_DIR=/tmp/stoa-uv-cache`; source behavior was unchanged.

## User Setup Required

None - no external service configuration required. No AWS, network, sandbox, or production mutation was performed.

## Verification

- Task 1 immutable lineage/classification/legacy/stale gate: **10 passed**.
- Task 2 adapter/apply/checkpoint/replay/restore/regrant/revocation gate: **13 passed**.
- Plan-level reconciliation, identity authorization, and production-admin gate: **68 passed**.
- Focused admin route and authorization-inventory regression: **12 passed**.
- Extended changed-boundary regression: **198 passed**.
- Ruff on all changed Python files: **passed**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Plan 472-14 can persist policy decisions without latent capability revival from conflicted identities.
- Phase 474 retains ownership of unrelated strict production Settings fixtures.
- Phase 475 retains ownership of teacher takeover and relationship transaction atomicity.
- Production/provider apply remains disabled without explicit external authorization and a separately supplied adapter factory/configuration.

## Self-Check: PASSED

- Both task commits are present in history.
- The concrete `RepositoryTighteningAdapter` artifact exists.
- Every task acceptance gate and the plan-level verification suite passed.
- All 16 plan files remain present, and this summary makes 12 completed plans.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
