---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 13
subsystem: testing
tags: [evidence, pytest, concurrency, dynamodb, release-gate, source-binding]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plans: [01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12]
    provides: atomic question, takeover, relationship, rate, practice, delivery, profile-CAS, and deletion-replay contracts
  - phase: 474-deterministic-verification-and-gated-delivery
    provides: fixed full-backend pytest argv, strict node accounting, fixed clock/seed, credential denial, and socket-denied execution contract
provides:
  - source-bound Phase 475 focused, inherited, static-analysis, and complete-suite evidence
  - closed exact coverage of V9DATA-01 through V9DATA-08, D-01 through D-16, five audit findings, and three Phase 473 follow-ups
  - privacy-safe immutable publication with explicit live AWS/provider/deployment NOT RUN obligations
affects: [476-billing-recovery, 478-web-role-journeys, 481-milestone-audit, V9DATA]

tech-stack:
  added: []
  patterns: [direct-child evidence publication, opaque parametrized node identities, candidate-diff mypy gate, Phase-474 strict full-suite extension]

key-files:
  created:
    - scripts/verify_phase475.py
    - tests/test_phase475_evidence_verifier.py
    - docs/security/phase-475-evidence-results.json
    - docs/security/phase-475-evidence.md
  modified:
    - src/stoa/db/repositories/account_deletion_repo.py

key-decisions:
  - "Evidence candidate cc709c17a9ff4cbec4c3aabf51660f52e571b5dc is immutable; publication 370562a is its exact two-file direct child and later metadata may only descend without changing either blob."
  - "The Phase 475 aggregate reuses Phase 474's fixed full-backend pytest prefix and strict accounting, while explicitly avoiding any claim that a local run replaces the historical fresh two-environment Linux/cross-repository release receipt."
  - "Parametrized node values are replaced with deterministic opaque IDs before logs, JUnit, node manifests, or public evidence can expose submitted answers or identities."
  - "Mypy executes against every Phase 475 runtime file and blocks diagnostics on candidate-changed lines; 178 pre-candidate diagnostics remain explicitly disclosed rather than suppressed or called zero."

patterns-established:
  - "Evidence capture: require one clean explicit candidate before every gate, preserve exact argv/UTC/exit/artifact hashes, then publish only checked redacted projections."
  - "Publication verification: infer one shared evidence commit from both canonical paths, require it to be the candidate's direct child, and compare immutable Git blobs at later HEAD."

requirements-completed: [V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08]

duration: 15 min
completed: 2026-07-22
---

# Phase 475 Plan 13: Integrated Source-Bound Evidence Gate Summary

**One immutable candidate now carries 2,466-node strict full-suite proof plus exact lower-boundary coverage for every Phase 475 requirement, decision, finding, and inherited follow-up without overclaiming live systems.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-22T01:37:35Z
- **Completed:** 2026-07-22T01:52:50Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `capture`, `verify-capture`, and `verify-publication` commands that bind every observation to clean candidate `cc709c17a9ff4cbec4c3aabf51660f52e571b5dc` and reject argv, result, count, artifact, source, coverage, privacy, or publication drift.
- Passed 2,466/2,466 nodes through the Phase 474 strict complete-backend extension, with zero failed, error, skipped, xfail, or xpass outcomes under a fixed clock/seed, denied ambient AWS credentials, and socket denial.
- Passed eight focused/inherited gates covering 22 question, 9 takeover, 25 relationship, 7 rate, 9 mistake, 24 delivery, 49 deletion, and 327 authorization/privacy regression nodes.
- Closed V9DATA-01 through V9DATA-08, D-01 through D-16, DATA-001, BUG-002, DATA-003, BUG-006, BUG-004, and the three named Phase 473 follow-ups against exact observed lower-boundary nodes.
- Published deterministic opaque parametrized node IDs and zero-match scans over 20 forbidden fixture values, so no raw answer, teacher identity, storage coordinate, provider diagnostic, or identity hash appears in checked evidence.
- Ran Ruff over all 21 Phase 475 runtime files plus the verifier/tests and ran mypy over the complete runtime inventory, yielding zero Phase 475 changed-line diagnostics while disclosing 178 older diagnostics.
- Preserved real AWS, provider effects, deployment, and production smoke as three exact `NOT RUN` obligations owned by later infrastructure/operations phases.

## Task Commits

Each task was committed atomically around the immutable candidate boundary:

1. **Task 1 implementation and adversarial verifier tests** - `cc709c1` (feat)
2. **Task 1 source-bound evidence publication** - `370562a` (docs)

**Plan metadata:** recorded by the final documentation commit

## Files Created/Modified

- `scripts/verify_phase475.py` - Closed gate registry, strict pytest plugin, source/receipt/privacy/coverage verification, candidate-diff mypy gate, rendering, and immutable publication verification.
- `tests/test_phase475_evidence_verifier.py` - Adversarial drift, lower-node deletion, source-string substitution, formal-entry, mypy-lineage, redaction, and publication mutation tests.
- `docs/security/phase-475-evidence-results.json` - Exact machine-readable argv, UTC, artifact hashes, safe node manifests, result counts, source snapshot, coverage, static-analysis, and NOT RUN receipts.
- `docs/security/phase-475-evidence.md` - Human-readable checked requirement, decision, finding, follow-up, gate, privacy, static-analysis, and external-obligation evidence.
- `src/stoa/db/repositories/account_deletion_repo.py` - Narrow `Any` annotation for the Phase 475 scrub retry table target so the changed-line mypy gate reflects its callable table contract.

## Decisions Made

- Kept the implementation/test commit separate from evidence so all expensive observations bind to a source candidate that cannot change while capture runs.
- Made the evidence publication commit the exact direct child of that candidate and restricted it to the two planned evidence paths; the verifier reads immutable Git blobs and remains valid from later metadata HEADs.
- Reused the fixed Phase 474 backend suite argv and strict manifest semantics, but labeled the result a local candidate extension rather than a replacement for Phase 474's already sealed fresh Linux/cross-repository evidence.
- Used deterministic opaque parameter IDs in every evidence pytest run. Exact node identity and collection hashes remain checkable without publishing parameter content.
- Defined targeted mypy as candidate-diff enforcement across the complete Phase 475 runtime inventory: the tool runs on every file, any diagnostic on a changed line fails, and unchanged baseline diagnostics remain visible in the receipt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed the scrub retry table's changed-line type contract**

- **Found during:** Task 1 (Capture and verify complete Phase 475 source-bound evidence)
- **Issue:** The complete Phase 475 mypy inventory found one diagnostic on the Plan 475-08 retry line because `get_table()` is intentionally typed as `object`, leaving `target.get_item()` unavailable to static analysis even though the runtime table contract is required there.
- **Fix:** Annotated only the local scrub retry target as `Any`, matching the repository's existing injected-table contract without changing behavior or suppressing any diagnostic globally.
- **Files modified:** `src/stoa/db/repositories/account_deletion_repo.py`
- **Verification:** The real locale-writer/scrub race and inherited claim-fencing suites pass; candidate-diff mypy now reports zero diagnostics on all Phase 475 changed lines.
- **Committed in:** `cc709c1`

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** The one-line type correction was required for the plan's explicit every-runtime-file targeted mypy gate and did not alter the deletion concurrency protocol.

## Issues Encountered

- The workspace sandbox denied direct `.git/index.lock` creation. Both scoped commits were rerun with approved repository permission; all normal hooks ran and no verification was bypassed.
- Full mypy still returns 178 diagnostics on lines predating Phase 475 across the analyzed runtime files. The evidence neither suppresses nor calls these zero; it proves that Phase 475 added none on its changed lines.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_evidence_verifier.py` — 25 passed.
- `.venv/bin/python scripts/verify_phase475.py verify-publication` — passed from clean publication HEAD.
- Phase 475 focused gates — 145 exact nodes passed across question, takeover, relationship, rate, mistake, delivery, and deletion modules.
- Inherited authorization/privacy gate — 327 exact nodes passed.
- Phase 474 strict full-backend extension — 2,466 passed, zero failed/error/skipped/xfail/xpass.
- Ruff — passed all 21 Phase 475 runtime files, verifier, and verifier tests.
- Candidate-diff mypy — 21 runtime files checked, zero changed-line diagnostics, 178 pre-candidate diagnostics disclosed.
- Raw/public privacy scan — zero matches across 20 forbidden values.
- `git diff --check` — passed.

## User Setup Required

None - no package installation, credentials, external provider call, deployment, or production mutation was used.

## Known Stubs

None. Empty collections in the verifier and tests are bounded accumulators or intentional negative fixtures; every evidence surface is wired to captured data.

## Next Phase Readiness

- Phase 475's complete local consistency/concurrency contract is ready for Phase 476 billing recovery and Phase 478 real Web journeys.
- Live DynamoDB/provider effects and deployment/production smoke remain exact `NOT RUN`; Phases 479 and 480 retain those obligations.
- The 178 inherited pre-candidate mypy diagnostics remain visible baseline debt and are not represented as Phase 475 failures or fixes.

## Self-Check: PASSED

- All six implementation, test, evidence, and summary files exist.
- Task commit `cc709c1` and evidence publication commit `370562a` exist in repository history.
- Publication verification passed from the clean evidence-publication HEAD; the final metadata commit is verified separately below as a descendant that preserves the immutable evidence blobs.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
