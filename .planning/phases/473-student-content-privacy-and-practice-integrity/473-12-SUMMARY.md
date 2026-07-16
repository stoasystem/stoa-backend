---
phase: 473-student-content-privacy-and-practice-integrity
plan: 12
subsystem: private-upload-lifecycle
tags: [privacy, s3, crash-recovery, cleanup, fencing, immutable-storage]

requires:
  - phase: 473-08
    provides: Opaque multipart chunk gateway and version-bound immutable consumers
  - phase: 473-11
    provides: Verification finding CR-007 and source-bound gap evidence
provides:
  - Pre-mutation durable staging and immutable provider coordinates
  - Fenced bounded restart recovery for staging assembly and immutable promotion
  - Exact multipart, staging-version, and immutable-version cleanup progress
  - Durable-reference-safe cleanup for stale and terminal upload states
affects: [473-13, 473-14, phase-473-verification, 479-infrastructure]

tech-stack:
  added: []
  patterns:
    - Durable provider-operation coordinates precede every irreversible provider mutation
    - Exact per-target cleanup progress gates terminal cleanup truth

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - tests/test_attachment_security.py

key-decisions:
  - "Staging assembly and immutable promotion use expiring operation fences with at most two recovery takeovers; every takeover increments the row version so stale workers cannot record success."
  - "Cleanup persists multipart, staging-version, and immutable-version progress independently and cannot reach cleanup_complete until all three markers are durable."
  - "Recovery and cleanup select only exact never-reused keys and exact VersionIds; mismatching or newer same-key versions are not deleted."

patterns-established:
  - "Provider split recovery: persist key/fence/expected evidence, mutate provider, then conditionally record the returned exact version."
  - "Cleanup truth: scan durable references first, persist each exact provider effect, then remove private coordinates only in the final conditional transition."

requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 14 min
completed: 2026-07-16
---

# Phase 473 Plan 12: Crash-safe immutable cleanup and recovery Summary

**Every upload provider mutation now has durable pre-mutation identity and bounded fenced recovery, while cleanup can report completion only after all exact unreferenced provider targets are durably removed.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-16T20:16:25Z
- **Completed:** 2026-07-16T20:30:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Persisted a globally unique staging key, operation kind, random fence, lease, and takeover counter before multipart creation; provider-success/repository-write loss remains exactly recoverable.
- Added ordered-ledger assembly fencing and exact staging-version recovery, plus a bounded-spool immutable `PutObject` whose key, checksum, length, MIME, and fence are durable before the provider write.
- Added bounded stale-operation takeovers that change both fence and row version, preventing an old worker from persisting staging or immutable success.
- Expanded cleanup eligibility to terminal, expired unconsumed, and lease-stale operation states while excluding active leases, consuming/consumed rows, and durable references.
- Required durable progress for exact multipart abort, staging VersionId deletion, and immutable VersionId deletion before `cleanup_complete`; finalization removes every provider and operation coordinate.
- Added adversarial lost-response, restart, repository-split, durable-reference, active-lease, newer-version, and idempotent retry controls.

## Task Commits

1. **Task 1: Persist fenced provider operations and recover every provider/database split** — `1cc2ccf` (fix)
2. **Task 2: Delete every exact unreferenced upload target before cleanup completion** — `9c3d95e` (test)

## Files Created/Modified

- `src/stoa/db/repositories/attachment_repo.py` — durable operation preparation/recording, bounded recovery takeover, stale-state cleanup claims, exact target progress, and completion guards.
- `src/stoa/services/attachment_service.py` — pre-mutation staging/promotion fencing, restart reconciliation, exact multipart/version cleanup, and bounded provider discovery.
- `tests/test_attachment_security.py` — split-window, recovery, exact-delete, durable-reference, active-lease, retry, and newer-version adversarial fixtures.

## Verification

- Task 1 lifecycle/restart selector: **8 passed, 112 deselected**.
- Task 2 cleanup selector: **26 passed, 88 deselected**.
- Plan-level files/questions/conversations matrix: **169 passed**.
- Full repository suite: **1,311 passed in 32.73s**.
- Targeted Ruff: PASS.
- `git diff --check`: PASS.
- External real-S3 versioning and scheduler behavior: **NOT RUN**, retained for Phase 479 as required by the plan threat model.

## Decisions Made

- Used one bounded-spool `PutObject` for the maximum 50 MiB immutable promotion so the exact key/checksum/length contract exists before a single provider mutation.
- Capped recovery takeovers at two and changed the operation fence plus row version on takeover; the prior worker can no longer commit through its old coordinate.
- Treated a same-key metadata/length mismatch as non-authoritative rather than deleting it during request recovery; only a positively matched or already recorded exact VersionId is destructive-cleanup eligible.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required and no production/provider mutation was performed.

## Next Phase Readiness

- CR-007 and D-09 are locally closed with executable restart and exact-cleanup controls.
- Plan 473-13 can now repair the remaining deterministic-ID, gateway error-normalization, and provider-stream closure warnings without inheriting an unsafe cleanup state machine.
- Plan 473-14 must regenerate source-bound evidence; this summary does not mark Phase 473 independently verified or complete.

## Self-Check: PASSED

- All three modified files exist and both task commits are present.
- Every task acceptance selector, plan regression, full suite, Ruff, and diff check passed.
- Cleanup completion is conditionally unreachable without all three durable progress markers.
- No external system was called and no private storage coordinate was added to a public model or job summary.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
