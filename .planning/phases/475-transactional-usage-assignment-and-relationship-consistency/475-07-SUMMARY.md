---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 07
subsystem: database
tags: [dynamodb, reconciliation, parent-binding, authorization, idempotency]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 06
    provides: atomic forward, reverse, and student-profile relationship writer
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 08
    provides: shared account-fenced profile version/CAS protocol
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: strict active bidirectional parent authorization and durable capability audit
provides:
  - bounded zero-business-write preview across six historical relationship classifications
  - opaque evidence-bound pair and preview identities over every strong-read coordinate
  - version-bound apply that repairs only unchanged unambiguous state through the atomic writer
  - conflict reporting, changed-row skips, zero-write replay, and capability-first audit proof
affects: [475-13-integrated-evidence, 478-web-admin-reconciliation, V9DATA-03]

tech-stack:
  added: []
  patterns: [strong-read evidence digest, preview-bound atomic apply, capability-before-data access]

key-files:
  created:
    - tests/test_phase475_parent_binding_reconciliation.py
  modified:
    - src/stoa/db/repositories/user_repo.py
    - src/stoa/routers/admin.py
    - tests/test_admin_authorization.py
    - tests/test_phase475_parent_binding_transaction.py

key-decisions:
  - "Preview returns only opaque pair/evidence identities, closed classifications, versions, and row digests; raw relationship coordinates remain request-bound and are not echoed as evidence."
  - "Apply strongly rereads every preview coordinate and invokes the Plan 475-06 atomic writer only for one unchanged, same-parent repairable classification."
  - "Conflicts outrank repair, changed repairable evidence is skipped, and already-consistent replay returns without another transaction."
  - "Both preview and apply reuse parent_binding_repairer target authorization, with durable target audit completed before relationship reads or mutation."

patterns-established:
  - "Historical relationship reconciliation: pure strong-read classification, evidence-bound confirmation, then one existing atomic domain primitive."
  - "Conflict handling: no winner selection, no coordinate overwrite, and strict bidirectional authorization remains denied until both formal rows agree."

requirements-completed: [V9DATA-03]

duration: 11 min
completed: 2026-07-22
---

# Phase 475 Plan 07: Preview-Bound Parent Relationship Reconciliation Summary

**Historical parent bindings now expose an opaque zero-business-write preview and repair only unchanged, unambiguous same-parent evidence through the existing atomic relationship transaction.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-22T01:13:35Z
- **Completed:** 2026-07-22T01:24:23Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Added `consistent`, `repairable_missing_forward`, `repairable_missing_reverse`, `repairable_profile_projection`, `conflict`, and `skipped_invalid` preview classifications over strong parent profile, student profile, forward row, exact reverse row, and all reverse-row reads.
- Bound every preview to opaque pair and evidence identities carrying whole-row digests and observed versions, without returning raw storage coordinates.
- Added explicit apply behavior that rereads all evidence, reports `skipped_changed` on stale repairable previews, never auto-selects a conflicting parent, and uses the Plan 475-06 atomic primitive only for an unchanged repair.
- Made successful replay return `already_consistent` with zero additional transactions and preserved concurrent profile bytes when CAS loses during apply.
- Added capability-first preview/apply routes with durable per-target authorization evidence and denial before any relationship repository read or mutation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement version-bound preview/apply relationship reconciliation** - `053c5b8` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/user_repo.py` - Closed repair classifications/results, strong-read evidence digests, preview identity, version-bound apply, and conflict/replay classification.
- `src/stoa/routers/admin.py` - Typed preview/apply request and response contracts plus capability-protected preview and explicit apply routes.
- `tests/test_phase475_parent_binding_reconciliation.py` - Six-class preview, zero-write, atomic repair, changed-row, transaction-race, conflict, authorization-denial, and replay proof.
- `tests/test_admin_authorization.py` - Route inventory, exact capability, pre-data denial, durable target audit, and structured apply regression.
- `tests/test_phase475_parent_binding_transaction.py` - Existing single-writer source seal updated to require the preview-bound apply wrapper.

## Decisions Made

- Used domain-separated SHA-256 identities over length-prefixed pair fields and canonical whole-row evidence. The response exposes only opaque digests, coordinate classes, and observed versions.
- Required active canonical parent/student profiles, active same-relationship formal rows, matching formal versions, and no other reverse parent before any classification can be repairable.
- Allowed a profile projection repair when both formal rows agree and every existing profile projection field is either absent or already equal; contradictory values remain conflict or invalid.
- Kept durable operation evidence in the established administrator authorization sink, which completes target-scoped audit before the preview or apply endpoint body executes. Preview performs no relationship/profile transaction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Preserved the inherited atomic-writer source seal**
- **Found during:** Task 1 (Implement version-bound preview/apply relationship reconciliation)
- **Issue:** The Plan 475-06 source regression required the admin route itself to name `put_parent_student_relationship`; the new contract intentionally routes through `apply_parent_binding_repair`, which is now the sole version-bound caller of that atomic primitive.
- **Fix:** Updated the inherited regression to require the apply wrapper while retaining guards against the obsolete direct binding and profile-link writers.
- **Files modified:** `tests/test_phase475_parent_binding_transaction.py`
- **Verification:** The expanded 279-node relationship, profile-CAS, administrator authorization, student authorization, and parent-route regression passed.
- **Committed in:** `053c5b8`

---

**Total deviations:** 1 auto-fixed (1 missing critical regression update).
**Impact on plan:** The test-only adjustment preserves the exact single-writer boundary introduced by this plan; no product or authorization scope was broadened.

## Issues Encountered

- The repository sandbox initially denied `.git/index.lock`; the same individually scoped staging and normal hook-enabled commit succeeded with approved repository permission. No hook was bypassed.
- Optional targeted mypy retains the seven pre-existing DynamoDB table-capability errors already documented by Plans 475-06 and 475-08. Required pytest and Ruff gates are green, and no new repair line is reported.

## Verification

- Exact plan command — 207 passed across parent-binding reconciliation, administrator authorization, and student authorization; Ruff passed every planned file.
- Expanded relationship/concurrency gate — 279 passed across reconciliation, Plan 475-06 atomic binding, Plan 475-08 profile CAS, administrator authorization, student authorization, and parent child routes.
- Concurrency proof — a profile version/locale change injected between apply recheck and the atomic transaction produced `skipped_changed`, retained the new locale, and created no reverse row.
- `git diff --check` — passed before the task commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-13 can bind the six classifications, zero-write preview, changed-row skip, transaction-race, conflict denial, idempotent replay, and capability/audit nodes into integrated V9DATA-03 evidence.
- Phase 478 can consume the typed preview and apply dispositions without inferring a winner from conflicting rows.

## Known Stubs

None.

## Threat Flags

None - the new preview/apply API surface and its concurrency/authorization controls are explicitly covered by the plan threat model.

## Self-Check: PASSED

- All five created/modified implementation and regression files exist in the working tree.
- Task commit `053c5b8` exists and contains exactly the intended source and test changes with no deletions.
- Every task acceptance criterion, the exact plan verification command, expanded concurrency/authorization regressions, Ruff, and diff checks pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
