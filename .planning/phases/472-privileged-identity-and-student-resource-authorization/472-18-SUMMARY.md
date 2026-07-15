---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 18
subsystem: auth
tags: [capability-grants, reconciliation, immutable-lineage, authorization]
requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: immutable capability history and conditional current pointers
provides:
  - full-coordinate reconciliation actions
  - collision-safe duplicate grant ID quarantine
  - account-restore non-revival evidence
affects: [privileged-identity, capability-authorization, security-audit]
tech-stack:
  added: []
  patterns:
    - immutable capability scope generation grant ID and version coordinates
    - coordinate-bound deterministic reconciliation checkpoints
key-files:
  created: []
  modified:
    - src/stoa/security/reconciliation.py
    - tests/test_privileged_identity_reconciliation.py
    - tests/test_identity_authorization.py
key-decisions:
  - "Grant reconciliation action identity is derived from the complete immutable coordinate, never inventory order or caller grant ID alone."
  - "All grant coordinates are validated before the first apply mutation, and account restoration remains separate from capability regrant."
patterns-established:
  - "Coordinate before effect: capability, exact scope, generation, grant ID, and version cross the plan/apply boundary together."
  - "Restore is not regrant: a fresh active Actor remains unprivileged until a new manager-approved command creates a new grant identity."
requirements-completed: [V9AUTH-04]
duration: 4 min
completed: 2026-07-15
---

# Phase 472 Plan 18: Scope-qualified Grant Reconciliation and Non-revival Summary

**Privileged reconciliation now revokes every capability lineage by a complete immutable coordinate, so duplicate caller IDs, retries, and account restore cannot preserve or revive old authority.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-15T15:59:00Z
- **Completed:** 2026-07-15T16:02:18Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added a frozen, lossless grant-coordinate value object containing canonical capability, exact scope, generation, grant ID, and version.
- Replaced grant-ID lookup and position-based action IDs with direct coordinate carriage and deterministic coordinate-bound checkpoints.
- Added preflight validation that rejects incomplete, noncanonical, zero-version, or duplicate coordinates before any tightening collaborator mutates state.
- Proved two active lineages sharing one caller grant ID are each revoked once in either inventory order, including audit-failure retry and replay.
- Proved the separately approved account restore path does not alter capability history or revive authority on a fresh Actor; only a new manager-approved command and grant identity can regrant.

## Task Commits

1. **Task 1: Carry a canonical immutable grant coordinate in every action** - `1ed9a58` (fix)
2. **Task 2: Revoke exact duplicate-ID lineages and prove non-revival** - `0dc0de1` (test)

## Files Created/Modified

- `src/stoa/security/reconciliation.py` - Carries, validates, fingerprints, and applies exact immutable grant coordinates without grant-ID search.
- `tests/test_privileged_identity_reconciliation.py` - Covers coordinate validation/redaction, duplicate-ID apply ordering, audit recovery, account restore, and new-command regrant.
- `tests/test_identity_authorization.py` - Proves a restored active account resolves a fresh Actor with no revived grant and receives a deny decision.

## Decisions Made

- Exact duplicate coordinates within one reconciliation item fail closed before effects rather than sharing one checkpoint ambiguously.
- Safe projections continue exposing only action names, reasons, counts, and redacted checkpoint identifiers; coordinate material remains internal.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 coordinate/redaction/action gate: 8 passed.
- Task 2 duplicate/revoke/replay/restore/non-revival/stale/regrant gate: 13 passed.
- Expanded focused gate after final assertions: 19 passed.
- Complete reconciliation and identity authorization suites: 72 passed.
- Source inspection confirms no grant-ID-only `next(...)` or action-target lookup remains.
- All collaborators are injected local fakes; no AWS, network, provider sandbox, or production mutation ran.

## Next Phase Readiness

- CR-02 is closed locally with collision-safe planning, apply, audit recovery, restoration, and authorization evidence.
- Phase 474 Settings fixtures and Phase 475 teacher takeover atomicity remain unchanged and deferred to their owning phases.
- Ready for Plan 472-19.

## Self-Check: PASSED

- All three modified source/test files exist.
- Both task commits are present in git history.
- Every task acceptance criterion and the plan-level verification command pass.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
