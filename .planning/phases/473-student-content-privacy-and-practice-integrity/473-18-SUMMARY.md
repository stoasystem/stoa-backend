---
phase: 473-student-content-privacy-and-practice-integrity
plan: 18
subsystem: storage-integrity
tags: [multipart, sha256, s3, crash-recovery, privacy]

requires:
  - phase: 473-17
    provides: Strict major provider coordinates, provider-body ownership, and source-bound privacy evidence
provides:
  - Exact UploadPart and ListParts acknowledgement validation bound to streamed SHA-256 bytes
  - Bounded duplicate-safe multipart and object-version pagination
  - Unique exact-version recovery with create-only immutable promotion and read-back verification
  - Staging-coordinate retention until exact provider absence is proved
affects: [473-19, 473-35, 479-provider-integration]

tech-stack:
  added: []
  patterns: [closed provider parsers, conditional acknowledgement persistence, unique-match recovery, create-only promotion]

key-files:
  created:
    - tests/test_phase473_provider_state_machine.py
  modified:
    - src/stoa/services/attachment_service.py
    - src/stoa/db/repositories/attachment_repo.py

key-decisions:
  - "Provider acknowledgements cross one closed parser boundary: exact nonblank ETags, non-bool positive integers, canonical SHA-256, and strictly progressing continuation markers."
  - "Immutable promotion uses a persisted never-reused key plus If-None-Match create-only semantics, exact version read-back, and absence-proved staging cleanup."

patterns-established:
  - "Acknowledgement before transition: provider success is parsed and checksum-matched before a conditional repository write can remove a lease."
  - "Recovery without guessing: zero or multiple matching versions retain the durable fence; only one exact byte-proven version may advance."

requirements-completed: [V9PRIV-02]

duration: 13 min
completed: 2026-07-17
---

# Phase 473 Plan 18: Provider acknowledgement and recovery integrity Summary

**Strict multipart acknowledgements, unique ledger-bound recovery, and create-only checksum-verified immutable promotion now prevent malformed or ambiguous provider success from becoming durable student content.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-17T14:27:28Z
- **Completed:** 2026-07-17T14:40:56Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Added a 56-case adversarial provider state-machine suite covering malformed scalar/checksum shapes, pagination, duplicate parts, conditional conflicts, commit-then-raise replay, ambiguous versions, promotion verification, and privacy canaries.
- Bound UploadPart and ListParts completion to exact ETag, canonical provider checksum, streamed SHA-256, byte count, part number, lease owner, and durable repository state.
- Replaced first-page/first-match recovery with bounded marker-pair pagination and unique exact-version selection, then added create-only immutable writes with exact metadata and byte read-back before persistence.
- Prevented stale terminal CAS attempts from aborting provider state and retained staging coordinates until the exact version is demonstrably absent.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the failing provider acknowledgement and recovery contract** - `398c79b` (test)
2. **Task 2: Enforce exact part acknowledgements and ledger invariants** - `798cc4e` (fix)
3. **Task 3: Bind crash recovery and immutable promotion to exact ledger proof** - `6be680c` (fix)

## Files Created/Modified

- `tests/test_phase473_provider_state_machine.py` - Stateful malformed-success, pagination, recovery, promotion, conditional-conflict, and redaction matrix.
- `src/stoa/services/attachment_service.py` - Closed acknowledgement parsers, bounded provider pagination, unique recovery, create-only promotion, exact byte verification, and absence-proved cleanup.
- `src/stoa/db/repositories/attachment_repo.py` - Independent acknowledgement, part-ledger, assembly, and promotion invariant enforcement before conditional state transitions.

## Decisions Made

- Provider dictionaries are untrusted until exact named parsers validate type, positivity, canonical encoding, checksum equality, and marker progress; no scalar coercion contributes durable facts.
- Operation-lease expiry authorizes bounded reconciliation only. Provider abort runs solely after the current-generation terminal repository CAS returns exact success.
- Promotion records success only after the returned immutable tuple and an exact versioned read/head agree with the validated bytes and server-owned metadata.
- Staging cleanup remains retryable durable debt unless an exact versioned HEAD proves the deleted coordinate is absent.

## Verification

- RED gate: the pre-implementation selector exited with pytest status 1 and reported 44 expected integrity failures with no private-canary disclosure.
- Task 2 acknowledgement/reconciliation gate: **45 passed**.
- Task 3 recovery/promotion gate: **76 passed**.
- Combined provider state-machine and inherited attachment-security suites: **268 passed**.
- Targeted Ruff on both production files and the new test module: **passed**.
- `git diff --check`: **passed**.
- Production-source fixed-string privacy-canary denylist: **passed**.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The managed filesystem initially denied one sandboxed Git index-lock write. The already-authorized normal commit was rerun with the required managed escalation; hooks remained enabled and the commit succeeded unchanged.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 473-19 gap closure.
- Real S3 multipart, conditional-write, and deployed recovery behavior remains explicitly unclaimed and assigned to Phase 479.

## Self-Check: PASSED

- Created and modified key files exist.
- Task commits `398c79b`, `798cc4e`, and `6be680c` exist in repository history.
- All task acceptance gates and plan-level verification commands pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
