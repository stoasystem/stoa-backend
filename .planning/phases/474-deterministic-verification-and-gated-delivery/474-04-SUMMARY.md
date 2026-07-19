---
phase: 474-deterministic-verification-and-gated-delivery
plan: 04
subsystem: release-verification
tags: [python, git-blobs, provenance, ancestry, fail-closed]

requires:
  - phase: 474-01
    provides: execution-derived candidate identity and source-bound release preflight
  - phase: 473
    provides: direct publication commit with four immutable checked evidence artifacts
provides:
  - explicit candidate/publication commit reverification from later clean metadata descendants
  - immutable Git blob OID and byte equality checks for every Phase 473 publication artifact
  - fail-closed ancestry, publication-shape, worktree, manifest, and missing-blob validation
affects: [474-release-manifest, 474-provenance, phase-473-closeout]

tech-stack:
  added: []
  patterns: [explicit full commit identity, immutable Git object reads, synthetic history tamper matrix]

key-files:
  created: []
  modified:
    - scripts/verify_phase473_evidence.py
    - tests/test_phase473_evidence_verifier.py

key-decisions:
  - "Phase 473 reverification accepts only explicit full lowercase candidate and publication commit SHAs; refs, abbreviations, branch names, and dirty drafts are rejected."
  - "The publication must have exactly one parent equal to the candidate, and current HEAD must descend from that publication without changing any of its four artifact blobs."
  - "Publication artifact truth comes only from Git blob OIDs and cat-file bytes; the mutable worktree is used solely for the fail-closed cleanliness check."

patterns-established:
  - "Later-HEAD provenance: metadata descendants remain eligible only when all publication blob OIDs and bytes are identical."
  - "Synthetic Git histories exercise direct, non-direct, merge, sideways, extra-path, missing-blob, dirty, inferred-ref, and tampered-manifest outcomes."

requirements-completed: [V9QUAL-07]

duration: 6 min
completed: 2026-07-19
---

# Phase 474 Plan 04: Later-HEAD Phase 473 Publication Reverification Summary

**Explicit Phase 473 candidate/publication commits now reverify from clean later metadata HEADs using immutable Git blob identities and bytes rather than mutable checkout artifacts.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-19T07:07:36Z
- **Completed:** 2026-07-19T07:13:22Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Replaced inferred direct-HEAD and dirty-draft publication checks with required explicit `--candidate` and `--publication` commit identities.
- Enforced one-parent direct publication ancestry, exact four-path publication shape, clean later worktree state, and current-HEAD descent from the publication.
- Read publication and later-HEAD artifacts through Git object storage, comparing both blob OIDs and bytes before validating manifest hashes, candidate bindings, coverage, obligations, and privacy claims.
- Added synthetic repositories that accept metadata-only descendants and reject later mutation, missing blobs, extra publication paths, merge/sideways/non-direct histories, inferred refs, dirty worktrees, and manifest hash/cardinality ambiguity.
- Reverified the real Phase 473 candidate `b43c71bdebf948e1ced024e309af1cfd5b4d5b50` and publication `5da6936095c2b5647a8f992c280d371837f35b0f` from the current clean later HEAD.
- Preserved all external S3, deployed infrastructure, production log, deployment, smoke, and rollback activity as exact `NOT RUN`; no provider or production operation was performed.

## Task Commits

The task followed the required RED/GREEN TDD sequence:

1. **Task 1 RED: specify immutable publication reverification** - `9d24c9f` (test)
2. **Task 1 GREEN: verify immutable publication commits** - `aa0d97e` (feat)

## Files Created/Modified

- `scripts/verify_phase473_evidence.py` - Explicit commit validation, ancestry and exact-path checks, immutable Git blob reads, later-HEAD equality, and revised CLI contract.
- `tests/test_phase473_evidence_verifier.py` - Synthetic publication histories covering the accepted later-metadata case and all required ambiguity/tamper failures.

## Decisions Made

- Removed dirty publication-draft verification because mutable worktree bytes cannot establish publication identity.
- Required full lowercase 40-character Git commit SHAs and verified each resolves to exactly the supplied commit, preventing planning-time abbreviations, branch names, or implicit `HEAD` from becoming candidate identity.
- Discovered the validation artifact path from the publication tree itself, so path selection does not depend on later worktree contents.
- Required both blob-OID equality and byte equality between the publication and current HEAD for all four artifacts before semantic evidence checks run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Repaired malformed post-plan metadata output**
- **Found during:** Plan closeout after the task and SUMMARY commits passed
- **Issue:** The roadmap updater replaced the Phase 474 name and dependency columns with a malformed row, and the tracking updater persisted `20%` despite computing 65/142 summaries as `46%`.
- **Fix:** Restored the canonical Phase 474 roadmap row at `3/80`, persisted the computed `46%`, and checked only the completed V9QUAL-07 requirement checkbox.
- **Files modified:** `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/REQUIREMENTS.md`
- **Verification:** Planning diffs preserve the phase name/dependencies, record exactly three completed Phase 474 summaries, retain Plan 474-03 as unexecuted, and advance the sequential completion counter from 3 to 4.
- **Committed in:** final tracking closeout commit

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** Closeout metadata was corrected without changing verifier behavior, claiming Plan 474-03, or expanding operational authority.

## Issues Encountered

- The managed filesystem initially denied Git index writes. Required normal commits were retried with repository write approval; no hook was bypassed and no Git state was reset, checked out, stashed, or destructively cleaned.
- Plan 474-04 executed before Plan 474-03 by explicit orchestrator assignment. `STATE.md` uses its `Plan: N of 80` field as a sequential completion-count/next-position counter, so it advanced from 3 to 4 while `474-03-SUMMARY.md` remains absent and Plan 474-03 remains unexecuted.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase473_evidence_verifier.py` — 75 passed.
- `.venv/bin/ruff check scripts/verify_phase473_evidence.py tests/test_phase473_evidence_verifier.py` — all checks passed.
- `.venv/bin/python scripts/verify_phase473_evidence.py verify-publication --candidate b43c71bdebf948e1ced024e309af1cfd5b4d5b50 --publication 5da6936095c2b5647a8f992c280d371837f35b0f` — passed from the current clean later HEAD.
- `git diff --check` passed.

## Next Phase Readiness

- Later release-manifest and provenance plans can consume an independently reverified Phase 473 publication without pinning verification to the publication HEAD itself.
- V9QUAL-07 is complete locally; broader Phase 474 deterministic gate, staging, and delivery work remains owned by later plans.
- Production infrastructure, deploy, smoke, and rollback remain exact `NOT RUN` pending separate explicit operational authority.

## Self-Check: PASSED

- Both modified key files exist.
- RED commit `9d24c9f` and GREEN commit `aa0d97e` exist in Git history in the required order.
- The real explicit candidate/publication pair reverifies from the current clean metadata descendant.
- Tests, Ruff, diff checks, stub scan, and threat-surface scan pass; no new endpoint, authorization path, file-system trust boundary, schema, provider call, or production operation was introduced.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
