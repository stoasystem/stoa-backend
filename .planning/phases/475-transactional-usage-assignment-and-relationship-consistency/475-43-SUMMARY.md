---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 43
subsystem: testing
tags: [git, evidence, source-snapshot, fail-closed, tdd]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 42
    provides: fail-closed candidate evidence and exact runtime inventory
provides:
  - exhaustive NUL-delimited Git name-status source inventory
  - deterministic blob evidence for added, modified, deleted, renamed, and copied paths
  - fail-closed path, status, blob, absence, ordering, and cardinality validation
affects: [475-44, 475-45, V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08]

tech-stack:
  added: []
  patterns: [exact NUL-delimited Git inventory, positive tree-absence proof, deterministic snapshot cardinality]

key-files:
  created: []
  modified:
    - scripts/verify_phase475.py
    - tests/test_phase475_evidence_verifier.py

key-decisions:
  - "Source evidence accepts only exact A, M, D, R<similarity>, and C<similarity> name-status records; malformed, ambiguous, duplicate, or unsupported records fail closed."
  - "Deletion and rename absence is established by a successful literal-path ls-tree query, while every required base or candidate blob must be readable and hashed."
  - "Snapshot rows preserve one normalized inventory identity and deterministic path/status/source ordering; missing, extra, duplicate, or reordered rows invalidate evidence."

patterns-established:
  - "Git command failures and malformed output produce static coordinate-free evidence errors rather than raw diagnostics or partial snapshots."
  - "Rename/copy evidence binds source path, destination path, similarity, base blob, and candidate blob in one deterministic row."

requirements-completed: [V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08]

duration: 8 min
completed: 2026-07-23
---

# Phase 475 Plan 43: Exhaustive Source Snapshot Summary

**Phase 475 evidence now classifies every changed path exactly once from a strict Git name-status inventory and fails closed on malformed status, unreadable blobs, unproved absence, or snapshot cardinality drift.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-23T09:24:44Z
- **Completed:** 2026-07-23T09:32:12Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Replaced the lossy `--name-only` loop and silent blob-read skip with exact NUL-delimited `--name-status` parsing for added, modified, deleted, renamed, and copied paths.
- Bound added/modified paths to candidate blob hashes, deleted paths to positive candidate absence plus base blob hashes, and rename/copy rows to both endpoints and required blobs.
- Rejected Git command failure, stderr, malformed UTF-8, truncated fields, unknown statuses, invalid similarity, ambiguous pairs, duplicate paths, unreadable blobs, unexpected presence, and missing/extra/duplicate/reordered snapshot rows.
- Added 19 focused source-snapshot adversarial cases, including the exact plan acceptance node, while leaving coverage registries unchanged.

## Task Commits

The single TDD task was committed through separate RED and GREEN gates:

1. **RED: failing exhaustive source snapshot contract** - `458ac1a` (test)
2. **GREEN: exhaustive fail-closed source snapshot** - `84de8cf` (feat)

No refactor commit was needed; the GREEN implementation is already scoped to the single evidence transformation.

## Files Created/Modified

- `scripts/verify_phase475.py` - Strict source inventory parsing, blob/absence proof, normalized row construction, and one-to-one validation.
- `tests/test_phase475_evidence_verifier.py` - All-status, malformed inventory, blob failure, absence failure, cardinality drift, and ordering coverage.

## Decisions Made

- Used `git diff --name-status -z --find-renames --find-copies` so path delimiters are unambiguous and rename/copy endpoints remain explicit.
- Used a successful literal-path `git ls-tree` query to prove candidate absence; a generic failed blob read is never accepted as absence.
- Rejected unsupported type-change or ambiguous pair status instead of inventing incomplete evidence semantics.
- Kept error messages static and coordinate-free so public verification cannot expose paths or raw Git diagnostics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected SDK progress percentage**
- **Found during:** Plan metadata close-out
- **Issue:** `state.update-progress` returned the correct 68% for 137/201 completed plans but persisted 20% in `STATE.md`.
- **Fix:** Preserved the SDK-recorded plan count and corrected only the persisted percentage to the returned 68%.
- **Files modified:** `.planning/STATE.md`
- **Verification:** `STATE.md` now records Plan 44/45, 137/201 completed plans, and 68%; `ROADMAP.md` independently records 43/45 Phase 475 summaries.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** The correction prevents false project progress metadata and does not change source-snapshot behavior or evidence coverage.

## Issues Encountered

- The first optional real-candidate probe used an incomplete `importlib` loader and failed before calling verifier logic. Registering the temporary module in `sys.modules`, matching the test loader, fixed the probe; the rerun validated all 150 inventory and snapshot rows one-to-one.

## Verification

- Exact plan node: `1 passed`.
- Snapshot adversarial selection: `19 passed, 25 deselected`.
- Complete evidence verifier: `44 passed`.
- Ruff over both changed files: passed.
- Real candidate `84de8cfc0d6fecd084472da47087198f0716bde6`: 150 inventory rows, 150 snapshot rows, exact validation passed, deterministic ordering true.
- `git diff --check`: passed.
- Normal commit hooks were not bypassed.
- Neither task commit deleted a tracked file.

## Acceptance Criteria

- **PASS — No changed path can silently disappear:** required blob reads and positive absence probes fail closed; row cardinality must equal inventory cardinality.
- **PASS — Rows are one-to-one and deterministic:** duplicate targets and missing, extra, duplicate, or reordered identities are rejected.
- **PASS — Deletions bind base and absence:** every deleted row contains `candidate_absent: true` plus exact base byte count and SHA-256.
- **PASS — Unsupported/malformed status fails closed:** adversarial unknown, truncated, invalid similarity, duplicate, ambiguous, and malformed UTF-8 inventories are rejected.

## User Setup Required

None - no dependency, credential, provider, deployment, schema, or external configuration change is required.

## Known Stubs

None. Empty collections in the modified files are bounded accumulators or test bookkeeping; no user-visible data source is unwired.

## Next Phase Readiness

- Plan 475-44 can close the lower-boundary replay evidence gap against a source snapshot that cannot omit changed files.
- No coverage registry was modified, and WR-03 remains isolated from the remaining gap plans.

## Self-Check: PASSED

- Both modified files and this summary exist.
- Commits `458ac1a` and `84de8cf` exist in current history and delete no tracked files.
- Exact acceptance node, all snapshot adversarial cases, the complete verifier module, Ruff, real-candidate cardinality, and diff integrity passed.
- No new endpoint, authorization path, dependency, schema, or unplanned trust boundary was introduced.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-23*
