---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 16
subsystem: jobs
tags: [sha256, reconciliation, cli, lambda, privacy]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 15
    provides: student-bound opaque question command digest and strict repository validation
provides:
  - commandDigest-only reconciliation CLI and Lambda coordinate contract
  - pre-repository rejection of malformed, raw-looking, or unknown operational input
  - closed reconciliation output containing only opaque identities and bounded evidence
affects: [475-44-coverage-registry, V9DATA-01, CR-08]

tech-stack:
  added: []
  patterns: [redacted argparse failures, validate-all-before-effects, closed Lambda field sets]

key-files:
  created: []
  modified:
    - src/stoa/jobs/reconcile_question_submissions.py
    - tests/test_phase475_question_reconciliation.py

key-decisions:
  - "The operational job owns a command_digest coordinate model while the repository keeps its existing internal parameter name; only a validated lowercase 64-hex value crosses that boundary."
  - "CLI and Lambda parsing fail with one static coordinate-free error, and every supplied coordinate is validated before the first repository call."

patterns-established:
  - "Opaque operational coordinate: bounded student ID plus validated command digest, with no question, period, or caller-key override."
  - "Closed reconciliation projection: disposition, opaque command/question IDs, versions, evidence digest, proposed action, and mutation count only."

requirements-completed: [V9DATA-01]

duration: 6 min
completed: 2026-07-22
---

# Phase 475 Plan 16: Opaque Reconciliation Coordinate Summary

**Question reconciliation now accepts only bounded student IDs plus opaque command digests across CLI and Lambda, rejecting private or malformed coordinates before repository access and returning a closed redacted result.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-22T09:52:10Z
- **Completed:** 2026-07-22T09:58:03Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Replaced the public reconciliation `idempotencyKey`/`--idempotency-key` contract with `commandDigest`/`--command-digest`.
- Added strict lowercase 64-hex digest validation, bounded student identity validation, closed Lambda field sets, and static errors that never echo rejected values.
- Validated the entire bounded input before repository access, preserving preview-by-default execution without adding discovery or scans.
- Kept output limited to the closed disposition, opaque command/question identities, versions, evidence digest, proposed action, and mutation count.
- Proved raw caller text, question/answer content, object keys, and provider VersionIds never appear in job output.

## Task Commits

Each TDD gate and the directly required privacy proof was committed atomically:

1. **RED: Add failing opaque reconciliation contract tests** - `f185dac` (test)
2. **GREEN: Make reconciliation coordinates opaque** - `bf6131e` (feat)
3. **Privacy regression: Strengthen closed-output proof** - `4ff2572` (test)

## Files Created/Modified

- `src/stoa/jobs/reconcile_question_submissions.py` - Job-local opaque coordinate model, strict CLI/Lambda parsing, pre-access validation, and closed result projection.
- `tests/test_phase475_question_reconciliation.py` - CLI, Lambda, invalid-input, preview/apply, replay, and output privacy proof.

## Decisions Made

- Kept the repository's existing internal `idempotency_key` keyword unchanged because Plan 475-15 already validates it as an opaque digest; the job boundary exposes only `command_digest`.
- Rejected unknown Lambda fields and invalid list/limit/mode values as one static error rather than skipping malformed coordinates or partially executing a batch.
- Removed optional question and quota-period operational overrides so the durable command digest remains the sole lookup coordinate after student identity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Extended output privacy assertions to every named sensitive class**
- **Found during:** Task 1 final acceptance review
- **Issue:** The inherited test explicitly excluded question and answer canaries but did not name raw caller text, object keys, or VersionIds.
- **Fix:** Added direct assertions that all three additional canary classes are absent from preview output.
- **Files modified:** `tests/test_phase475_question_reconciliation.py`
- **Verification:** The exact plan pytest selector passes 7 tests and Ruff passes both planned files.
- **Committed in:** `4ff2572`

---

**Total deviations:** 1 auto-fixed (1 missing critical privacy proof).
**Impact on plan:** Test-only strengthening directly closes the planned CR-08 non-disclosure requirement with no product scope expansion.

## Issues Encountered

- The sandbox denied `.git/index.lock` creation for normal staging. The same individually scoped files were staged and committed with approved repository permission; hooks ran normally and no verification was bypassed.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_question_reconciliation.py -k 'cli or lambda or privacy or preview or replay'` - 7 passed, 6 deselected.
- `.venv/bin/ruff check src/stoa/jobs/reconcile_question_submissions.py tests/test_phase475_question_reconciliation.py` - passed.
- Source contract scan - no public `idempotencyKey` or `--idempotency-key` remains in the job; help exposes `--command-digest` and no question/period override.
- `git diff --check` - passed.

## User Setup Required

None - no dependency, credential, migration, service, or deployment change is required.

## Known Stubs

None.

## Next Phase Readiness

- CR-08 is closed across the request, durable storage, reconciliation input, and operational output boundaries.
- Plan 475-44 can register the dynamic raw-canary CLI/Lambda/output proof for the final source-bound coverage inventory.

## Self-Check: PASSED

- Both planned files exist and contain the committed implementation/test changes.
- RED commit `f185dac`, GREEN commit `bf6131e`, and privacy-proof commit `4ff2572` exist with no tracked deletions.
- Every task acceptance criterion, the exact plan verification command, CLI contract scan, stub scan, Ruff, and diff check pass.
- The only remaining worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
