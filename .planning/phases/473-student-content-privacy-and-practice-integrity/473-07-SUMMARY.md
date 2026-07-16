---
phase: 473-student-content-privacy-and-practice-integrity
plan: 07
subsystem: privacy-evidence
tags: [dynamodb, s3, cleanup, privacy, openapi, authorization, evidence]

requires:
  - phase: 473-02
    provides: Owner upload lifecycle, content validation, quota, and conditional transaction primitives
  - phase: 473-03
    provides: Durable conversation attachment retention, reuse, and deletion tombstones
  - phase: 473-04
    provides: Atomic question attachment consumption and owner-resolved OCR
  - phase: 473-05
    provides: Answer-free previews and durable attempt-gated results
  - phase: 473-06
    provides: Assignment-scoped teacher and global admin answer reads
provides:
  - Bounded idempotent terminal and expired unconsumed upload cleanup
  - Conditional cleanup claims with resumable durable-reference scans
  - Source-bound Phase 473 privacy, practice, route, OpenAPI, and full-suite evidence
  - Honest NOT RUN boundaries for real S3 and external cleanup scheduling
affects: [475-data-consistency, 476-billing-recovery, 478-mobile-journeys, 479-infrastructure, 480-observability]

tech-stack:
  added: []
  patterns:
    - Non-consumable cleanup tombstone before provider deletion
    - Bounded resumable reference scan before destructive object cleanup
    - Source/test digest evidence with private canary denylist

key-files:
  created:
    - src/stoa/jobs/upload_cleanup.py
    - docs/security/phase-473-evidence.md
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/jobs/__init__.py
    - tests/test_attachment_security.py
    - .planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md

key-decisions:
  - "Cleanup can claim only invalid, explicitly expired, cleanup-pending, or past-expiry unconsumed intent states; consuming and consumed states are never eligible."
  - "A cleanup claim makes the upload non-consumable before a bounded resumable durable-reference scan and S3 deletion; provider failure retains the retry tombstone."
  - "Final Phase 473 evidence is bound to the tested production SHA, test digests, and deterministic route inventory while real S3 and external schedule/IaC checks remain NOT RUN."

patterns-established:
  - "Cleanup safety: versioned conditional claim, consistent re-read, durable-reference proof, idempotent provider delete, conditional completion."
  - "Evidence privacy: exact local commands and digests are published while seeded private values remain only in fixtures and a temporary denylist."

requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]

duration: 16 min
completed: 2026-07-16
---

# Phase 473 Plan 07: Cleanup, combined privacy gate and source-bound evidence Summary

**Expired, invalid, and abandoned upload intents now converge through bounded retry-safe cleanup, and all Phase 473 ownership, lifecycle, practice, authorization, OpenAPI, and redaction contracts close under one source-bound gate.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-16T11:45:00Z
- **Completed:** 2026-07-16T12:01:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added a bounded cleanup handler and service that conditionally claims only terminal or past-expiry unconsumed upload intents, consistently rechecks their version, and never deletes active, consuming, consumed, or durable-referenced resources.
- Added resumable bounded durable-reference scans, durable attachment markers, non-consumable cleanup tombstones, idempotent object deletion, safe retry after provider failure, and coordinate-free category summaries.
- Published redacted evidence mapping SEC-003, SEC-005, BUG-001, V9PRIV-01/02/03, and D-01 through D-22 to exact passing commands, source/test digests, deterministic route/OpenAPI contracts, and later-phase boundaries.
- Closed validation observations with a 230-test combined gate, 635-test inherited authorization gate, byte-stable 222-operation inventory, and a 1232-test zero-failure full-suite JUnit observation.

## Task Commits

Each task was committed atomically with hooks enabled:

1. **Task 1: Implement bounded idempotent expired and invalid upload cleanup** - `671612b` (feat)
2. **Task 2: Run combined Phase 473 security gate and publish redacted evidence** - `8e64ee0` (docs)

## Files Created/Modified

- `src/stoa/jobs/upload_cleanup.py` - Bounded scheduled handler, safe summary contract, opaque continuation, and cleanup orchestration.
- `src/stoa/db/repositories/attachment_repo.py` - Candidate paging, versioned cleanup claims, resumable reference scans, protected/completed transitions, and durable attachment markers.
- `src/stoa/services/attachment_service.py` - Consistent recheck, durable protection, retry-safe provider deletion, and cleanup completion service.
- `src/stoa/jobs/__init__.py` - Explicit cleanup job exports.
- `tests/test_attachment_security.py` - Expired/invalid/abandoned, active/consuming/consumed/durable, retry, idempotency, bounded work, and redaction controls.
- `docs/security/phase-473-evidence.md` - Source-bound combined evidence, D-01–D-22 matrix, full-suite delta, privacy scan, and external NOT RUN rows.
- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md` - Completed per-task observations and validation sign-off.

## Decisions Made

- Cleanup eligibility is a closed server-owned status/expiry condition. It cannot be selected by an owner or caller and cannot include a consuming or consumed resource.
- Durable reference discovery is deliberately bounded and resumable across invocations. An incomplete scan defers deletion; a discovered reference permanently blocks transient cleanup without restoring usability.
- S3 deletion precedes conditional cleanup completion. A provider or completion-write failure leaves `cleanup_pending`, so a later idempotent delete retry cannot revive a validated upload or expose coordinates.
- External S3 policy behavior and deployed schedule/IaC are not inferred from local fakes and remain explicit Phase 479/480 evidence gaps.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The terminal renderer did not retain the full quiet-suite footer, so the required full-suite observation was also emitted as complete JUnit XML. The report contains 1232 tests with zero failures, errors, or skips and is the result recorded in evidence.

## User Setup Required

None - no external service configuration required. Real non-production S3 and deployed schedule checks require separate approval and remain NOT RUN.

## Verification

- Cleanup acceptance filter: **6 passed, 47 deselected**.
- Full attachment security module: **53 passed**.
- Exact combined Phase 473 matrix: **230 passed**.
- Inherited Phase 472 authorization regression: **635 passed**.
- Route inventory generated twice, byte-compared with checked JSON, and `--check` passed; **222 operations**, SHA-256 `2d072ad391724100647b1d7a9862660730a0b358268cf37b65481fba727253b3`.
- Full backend JUnit observation: **1232 tests, 0 failures, 0 errors, 0 skipped**, +3 cleanup tests over the supplied 1229 baseline.
- Evidence private-canary denylist: PASS with no matches.
- Ruff on changed Python files and `git diff --check`: PASS.

## Next Phase Readiness

- Phase 475 can build broader quota/ledger/question, attempt analytics, assignment-write, and relationship consistency on the now-closed attachment and practice privacy boundaries.
- Phase 476 retains billing and paid-entitlement recovery; Phase 478 can consume opaque upload/attachment and attempt-result contracts in real mobile journeys.
- Phase 479 must supply authoritative cleanup schedule/IaC and real S3 lifecycle evidence; Phase 480 retains production redaction, observability, pagination, deployment, and rollback evidence.

## Self-Check: PASSED

- Both task commits exist, every named created file exists, and the working implementation passes the cleanup, combined, inherited authorization, deterministic inventory, canary, static, and full-suite gates above.
- Evidence binds the tested production source and test artifacts without publishing seeded private values or claiming unavailable external verification.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
