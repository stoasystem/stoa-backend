---
phase: 473-student-content-privacy-and-practice-integrity
plan: 40
subsystem: security-evidence
tags: [pytest, junit, immutable-candidate, privacy, sha256, evidence]

# Dependency graph
requires:
  - phase: 473-39
    provides: Source-sealed 66-read/232-write inventories and exact lower selectors for five final findings
  - phase: 473-36-through-473-38
    provides: Lease-fenced deletion, crash-safe delivery intents, and authoritative private delivery
provides:
  - Four dedicated strict final-gap gates and one exact lower-bound coverage registry
  - Fresh 21-gate immutable capture with independently recomputed receipts and inventory joins
  - Exact four-document evidence publication bound to one clean candidate
affects: [phase-473-verification, V9PRIV-02, D-10, D-16, D-17, phase-479, phase-480]

# Tech tracking
tech-stack:
  added: []
  patterns: [candidate-blob snapshot, strict lower-node registry, non-circular publication manifest]

key-files:
  created: []
  modified:
    - scripts/verify_phase473_evidence.py
    - tests/test_phase473_evidence_verifier.py
    - docs/security/phase-473-evidence-results.json
    - docs/security/phase-473-evidence.md
    - docs/security/phase-473-evidence-manifest.json
    - .planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md

key-decisions:
  - "CR-01, CR-02, WR-01, WR-02, and WR-03 count only through exact observed runtime nodes joined to both checked finding registries and declared lower fakes."
  - "V9PRIV-02 and D-10/D-16/D-17 retain inventory coverage and additionally require the exact deletion, crash-recovery, and delivery-denial nodes."
  - "Candidate snapshots are recomputed from immutable candidate Git blobs, so post-publication verification cannot accidentally hash child-worktree bytes."

patterns-established:
  - "Final-gap receipt: dedicated focused gate plus combined inherited regression, strict node phases, and zero skip/XFAIL/XPASS tolerance."
  - "Publication recovery: any post-commit mismatch invalidates the candidate and every receipt; fix, commit a new candidate, and rerun the full registry from gate one."

requirements-completed: [V9PRIV-02]

# Metrics
duration: 21min
completed: 2026-07-18
---

# Phase 473 Plan 40: Immutable Evidence And Aggregate Re-verification Summary

**A 21-gate capture on candidate `b43c71b` records 2,009 strict full-suite nodes, exact five-finding lower-bound matrices, 66-read/232-write inventory joins, and a hash-reproducible four-document publication**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-18T16:22:58Z
- **Completed:** 2026-07-18T16:43:48Z
- **Tasks:** 3
- **Files modified:** 6 implementation/evidence files plus this summary

## Accomplishments

- Added dedicated strict gates for deletion-claim fencing, delivery-intent recovery, private-delivery fencing, and their exact inherited combined regression.
- Bound five review findings, ten verifier gap truths, ten claim-fence nodes, seven delivery-scope nodes, and nine crash-state nodes to exact runtime selectors, lower fakes, observed conditions, and checked inventory rows.
- Captured 21 gates on immutable candidate `b43c71bdebf948e1ced024e309af1cfd5b4d5b50`: 14 deletion-claim, 10 delivery-recovery, 12 private-delivery, 109 combined final-gap, 939 deep Phase 473, 455 inherited Phase 473, 636 Phase 472, and 2,009 full-suite nodes.
- Reproduced 66 strict read boundaries, 232 private writes, all 17 deletion branches, three retained-policy classes, V9PRIV-01/02/03, and D-01 through D-22 with zero failures, errors, skips, XFAIL, XPASS, or privacy matches.
- Published `5da6936095c2b5647a8f992c280d371837f35b0f` as the clean single direct four-file child, with independently recomputed artifact hashes and byte counts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing evidence-registry and five-finding coverage contracts** — `f5e5cec` (test, RED)
2. **Task 2: Implement strict final-gap gates and immutable capture verification** — `d7d0d5d` (feat, GREEN), `9b44494` (fix, publication rendering)
3. **Task 3: Capture one clean candidate, publish checked evidence, and expose re-verification** — `b43c71b` (fix, immutable snapshot), `5da6936` (docs, final publication)

The earlier publication `46adfca` was invalidated and never reused after its post-commit capture verification exposed candidate/worktree snapshot drift.

## Files Created/Modified

- `scripts/verify_phase473_evidence.py` — Four final-gap gates, exact finding/truth/node coverage, candidate-blob snapshots, strict publication cardinality, and complete human evidence matrices.
- `tests/test_phase473_evidence_verifier.py` — Fixture-driven missing-node, stale-registry, duplicate, source-string substitution, renderer, and post-publication candidate-snapshot regressions.
- `docs/security/phase-473-evidence-results.json` — Canonical 21 receipts, exact nodes/counts/argv/hashes, coverage joins, inventory metadata, privacy facts, and external NOT RUN obligations.
- `docs/security/phase-473-evidence.md` — Human-readable raw receipt integrity plus deletion, delivery, crash, requirement, decision, finding, and external-boundary evidence.
- `docs/security/phase-473-evidence-manifest.json` — Non-circular candidate binding and SHA-256/byte counts for results, evidence, and validation only.
- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md` — Candidate-bound local validation with exact gate counts and honest external scope.

## Decisions Made

- Required every final-gap semantic fact through a named lower runtime node; collection, source text, or a broad high-level test cannot substitute.
- Kept the two checked finding registries as independent inputs and rejected ID, selector, lower-fake, assertion, or required-semantics disagreement.
- Preserved real S3, deployed cleanup/IaC, and production/deployed logs as exact NOT RUN obligations owned by Phases 479/480.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added explicit final-gap publication matrices**

- **Found during:** Task 3 pre-candidate audit
- **Issue:** The inherited renderer enforced the new coverage in JSON but did not explicitly publish the required deletion, crash, legacy/malformed/global delivery, provider-counter, raw hash, or UTC-bound matrices in the human evidence.
- **Fix:** Added raw receipt integrity, exact lower-fake matrices, inventory seals, and required lower nodes for V9PRIV-02 and D-10/D-16/D-17, with a renderer regression.
- **Files modified:** `scripts/verify_phase473_evidence.py`, `tests/test_phase473_evidence_verifier.py`
- **Verification:** 69 verifier tests and targeted Ruff passed before the first candidate was frozen.
- **Committed in:** `9b44494`

**2. [Rule 1 - Bug] Recomputed candidate snapshots from immutable Git blobs**

- **Found during:** Task 3 decisive post-commit `verify-capture`
- **Issue:** Candidate snapshot metadata was recomputed from the publication child's worktree, so changed publication bytes caused `checked result drift` even though the candidate itself was immutable.
- **Fix:** Read every snapshot byte from `git show <candidate>:<path>` and added a regression that advances to a changed direct child while preserving the candidate hash/byte result.
- **Files modified:** `scripts/verify_phase473_evidence.py`, `tests/test_phase473_evidence_verifier.py`
- **Verification:** 70 verifier tests and Ruff passed; a completely new 21-gate capture then passed two extra verifications and the decisive post-publication clean check.
- **Committed in:** `b43c71b`

---

**Total deviations:** 2 auto-fixed (1 missing critical publication contract, 1 verifier bug)
**Impact on plan:** Both changes were necessary for truthful, reproducible publication. The failed candidate `9b444949` and publication `46adfca` were invalidated; no receipt was reused.

## Verification

- **RED:** 27 failed, 41 passed; pytest exited exactly `1` with no collection/import error.
- **GREEN:** 70 verifier contract tests passed; targeted Ruff passed.
- **Focused strict gates:** 14 deletion-claim, 10 delivery-recovery, 12 private-delivery, and 109 combined final-gap nodes passed.
- **Broad strict gates:** 939 deep Phase 473, 455 inherited Phase 473, 636 Phase 472, and 2,009 full-suite nodes passed.
- **Forbidden outcomes:** 0 failures, 0 errors, 0 skips, 0 XFAIL, 0 XPASS, and 0 privacy matches across every receipt.
- **Coverage:** 5 findings, 10 gap truths, 10 claim-fence nodes, 7 delivery-scope nodes, 9 crash-state nodes, 66 reads, 232 writes, 17 branches, 3 retained classes, 3 requirements, and 22 decisions.
- **Publication:** candidate `b43c71bdebf948e1ced024e309af1cfd5b4d5b50`; direct child `5da6936095c2b5647a8f992c280d371837f35b0f`; exact four-path diff, clean tree, `verify-capture`, clean `verify-publication`, and `git diff --check` passed.
- **Manifest artifacts:** results 3,386,828 bytes / `92a57bf50ac70b61d6845a0d8bf4d2b2386f12528db6edec91a7820a6cba2480`; evidence 41,629 bytes / `92a93375f0e43570a4fa87ccc211552e6cdfa5cb0a97d034c96572ba91ed3aa4`; validation 1,497 bytes / `3ed930417db14cbad81e8a0901c56e812fd67e5bc3f4a17270ce7bddea01cb69`.

## Issues Encountered

- The repository `gsd-tools` shim was not on `PATH`; state operations use the installed Node CLI entrypoint.
- One diagnostic byte-count loop used zsh's reserved `path` variable and lost command lookup after all decisive gates had already passed. The exact verification was immediately rerun under `bash -lc` with a neutral variable name and passed fully.

## Authentication Gates

None.

## Known Stubs

None. Empty lists/dictionaries in the verifier and fixtures are deterministic accumulators or negative states; no evidence or application path is unwired.

## User Setup Required

None - no package installation, provider credentials, deployment, external mutation, or production access was used.

## Next Phase Readiness

- Phase 473 has a clean local evidence publication ready for independent aggregate verification; this execution does not mark the phase complete.
- Real S3 remains owned by Phase 479, while deployed cleanup/IaC and production/deployed logs remain owned by Phase 480.

## TDD Gate Compliance

- RED commit: `f5e5cec`
- GREEN commit: `d7d0d5d`
- Pre-candidate publication rendering: `9b44494`
- Candidate snapshot correction: `b43c71b`
- Final publication: `5da6936`

## Self-Check: PASSED

- All six declared implementation/evidence artifacts and this summary exist.
- Task commits `f5e5cec`, `d7d0d5d`, `9b44494`, `b43c71b`, and `5da6936` exist in repository history.
- The final publication was verified as the clean exact four-file direct child of candidate `b43c71b` before plan metadata was added.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
