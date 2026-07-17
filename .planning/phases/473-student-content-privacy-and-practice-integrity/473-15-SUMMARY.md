---
phase: 473-student-content-privacy-and-practice-integrity
plan: 15
subsystem: storage-security
tags: [privacy, uploads, s3, dynamodb, cleanup, recovery]

requires:
  - phase: 473-12
    provides: Crash-safe fenced upload recovery and exact-target cleanup
  - phase: 473-14
    provides: Immutable-source privacy evidence and retained cleanup gates
provides:
  - Strict nonblank string invariants for provider UploadId, VersionId, and ETag success coordinates
  - Recovery-fence preservation across malformed provider success and restart reconciliation
  - Candidate-local cleanup isolation with deterministic redacted retryable outcomes
affects: [473-16, 473-17, V9PRIV-02, phase-479-infrastructure]

tech-stack:
  added: []
  patterns:
    - Validate provider coordinates before every fence-removing persistence transition
    - Contain candidate-local cleanup failures while preserving global listing failure semantics

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/jobs/upload_cleanup.py
    - tests/test_attachment_security.py
    - tests/test_files.py

key-decisions:
  - "Provider success coordinates must be nonblank strings before any lifecycle transition can remove a recovery fence; malformed success retains exact recovery identity."
  - "Unexpected candidate-local cleanup failures become coordinate-free retryable outcomes, while failure to list the global candidate page still propagates."

patterns-established:
  - "Strict provider success: never coerce identifiers or ETags, and validate again at repository boundaries."
  - "Truthful cleanup isolation: one candidate cannot starve later bounded work or manufacture cleanup completion."

requirements-completed: [V9PRIV-02]
duration: 15 min
completed: 2026-07-17
---

# Phase 473 Plan 15: Provider-coordinate invariants and isolated cleanup recovery Summary

**Strict provider-coordinate validation now preserves exact recovery fences after malformed storage success, while scheduled cleanup contains each candidate failure and continues bounded work without leaking diagnostics.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-17T08:24:06Z
- **Completed:** 2026-07-17T08:39:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Rejected absent, non-string, empty, and whitespace-only multipart, staging-version, immutable-version, and ETag coordinates before any fence-removing service or repository transition.
- Preserved staging issuance, assembly, promotion, and cleanup recovery identity when provider success is malformed, including restart recovery and exact-target absence/deletion truth.
- Isolated repository, provider, malformed-response, and unexpected failures per cleanup candidate so later candidates still converge with deterministic coordinate-free counts and continuation.
- Added adversarial route, repository, restart, no-false-completion, and first-candidate-fails/later-candidate-converges regression coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: Reject malformed provider success without removing recovery fences** — `b68d1be` (fix)
2. **Task 2: Isolate cleanup candidates and preserve deterministic retry truth** — `a04b8bd` (fix)

## Files Created/Modified

- `src/stoa/db/repositories/attachment_repo.py` — rejects invalid provider coordinates before multipart, staging-version, immutable-version, and compatibility-alias persistence transitions.
- `src/stoa/services/attachment_service.py` — applies strict coordinate validation at provider success boundaries and keeps unverified exact-key versions retryable.
- `src/stoa/jobs/upload_cleanup.py` — contains candidate-local exceptions, preserves opaque continuation, and leaves global listing failures visible.
- `tests/test_attachment_security.py` — covers malformed coordinates, retained fences, restart cleanup truth, direct repository guards, and multi-candidate isolation.
- `tests/test_files.py` — verifies the stable redacted gateway error contract for malformed provider success.

## Decisions Made

- Required provider coordinates are accepted only as nonblank strings; coercion is forbidden because it can turn malformed dependency output into durable lifecycle truth.
- Exact-key version enumeration that returns only malformed/unverifiable version rows is retryable, not proof of absence, so cleanup cannot complete falsely.
- The cleanup job owns a final exception boundary around each selected candidate, but candidate-page listing remains outside that boundary so global scan failure is never reported as successful empty work.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The Wave 0 regressions failed before implementation as intended and passed after both task changes.

## Verification

- Provider-coordinate and retained-fence selector: 68 passed, 160 deselected.
- Cleanup isolation and retry-truth selector: 13 passed, 192 deselected.
- Broader files, attachment security, questions, and conversations suite: 282 passed.
- Targeted Ruff and `git diff --check`: passed.

## Known Stubs

None. Stub-pattern matches were existing initializations, compatibility defaults, or test fixtures and do not leave this plan's behavior unwired.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CR-009 and WR-009 are locally closed with executable regression coverage; Plan 473-16 can verify the remaining independent privacy boundary.
- Real S3 and deployed scheduler evidence remains explicitly Phase 479-owned and was not claimed by this local plan.

## Self-Check: PASSED

- Both task commits exist in repository history and all five modified implementation/test files plus this summary exist on disk.
- The two targeted selectors, 282-test broader suite, targeted Ruff, and diff-hygiene gate all passed on the committed implementation.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
