---
phase: 473-student-content-privacy-and-practice-integrity
plan: 28
subsystem: security-testing
tags: [pytest, junit, evidence, privacy, sha256, immutable-candidate]

# Dependency graph
requires:
  - phase: 473-27
    provides: Source-bound read-boundary inventory composed with the Plan 35 private-store seal
  - phase: 473-18-through-473-35
    provides: Final provider, replay, retention, parser, practice, and account-deletion closure
provides:
  - Strict pytest skip/XFAIL/XPASS denial with deterministic node manifests
  - Machine-checked immutable gate receipts and exact inventory-to-node coverage
  - Exact four-document evidence publication with reproducible non-circular hashes
affects: [phase-473-verification, V9PRIV, phase-479, phase-480]

# Tech tracking
tech-stack:
  added: []
  patterns: [closed argv registry, raw JUnit/node receipts, immutable candidate capture, non-circular publication manifest]

key-files:
  created:
    - scripts/phase473_pytest_guard.py
    - scripts/verify_phase473_evidence.py
    - tests/test_phase473_evidence_verifier.py
    - tests/fixtures/phase473_evidence_denylist.txt
    - docs/security/phase-473-evidence-results.json
  modified:
    - docs/security/phase-473-evidence.md
    - docs/security/phase-473-evidence-manifest.json
    - .planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md

key-decisions:
  - "A gate counts only when its raw log, JUnit, node manifest, exact argv, source state, and privacy facts independently reproduce."
  - "Any failed capture or publication check invalidates the complete observation set and requires a new candidate plus a full registry rerun."
  - "Real S3, deployed scheduler/IaC, and production logs remain exact NOT RUN obligations owned by Phases 479/480."

patterns-established:
  - "Strict pytest receipt: every setup/call/teardown report contributes to one deterministic node outcome; skip, XFAIL, and XPASS are fatal."
  - "Evidence publication: results, evidence, and validation are hashed by a manifest that never hashes itself; the commit is an exact direct four-path child."

requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]

# Metrics
duration: 26min
completed: 2026-07-18
---

# Phase 473 Plan 28: Checked Immutable Evidence Capture and Publication Summary

**Strict 1,923-node local verification with raw machine receipts, exact 49-read/226-write/17-branch coverage, zero privacy matches, and a reproducible four-document child of one immutable candidate**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-18T11:12:57Z
- **Completed:** 2026-07-18T11:38:52Z
- **Tasks:** 3
- **Files modified:** 10 implementation/evidence files plus this summary

## Accomplishments

- Added an opt-in pytest plugin that records deterministic setup/call/teardown outcomes and makes every skip, expected failure, or unexpected pass fatal.
- Captured 17 closed gates on immutable candidate `cf3549ad799843fd91bb7494064a02d57227c953`, including 889 deep Phase 473 nodes, 455 inherited Phase 473 nodes, 636 Phase 472 regression nodes, and the 1,923-node full suite.
- Bound every receipt to exact argv, UTC bounds, clean pre/post candidate state, raw log/JUnit/node bytes and SHA-256, recomputed counts, and the fixed denylist with zero matches.
- Mapped V9PRIV-01/02/03, D-01 through D-22, 49 read boundaries, 226 private-write rows, all 17 deletion branches, and 3 retained-policy classes exactly once to observed nodes.
- Published `7a866e6` as the clean direct four-document child; every manifest hash reproduces and real provider/deployment/production checks remain separate NOT RUN obligations.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the failing evidence-protocol contract** — `2a9f441` (test, RED)
2. **Task 2: Implement strict outcomes and source-bound capture/verification** — `dd24017` (feat, GREEN)
3. **Task 3: Seal candidate, capture, and publish exact evidence** — `259a56c` (fix), `cf3549a` (fix), `7a866e6` (docs)

## Files Created/Modified

- `scripts/phase473_pytest_guard.py` — Strict opt-in pytest report aggregation and deterministic node-manifest writer.
- `scripts/verify_phase473_evidence.py` — Closed registry runner, receipt verifier, coverage derivation, evidence renderer, and dirty/clean publication checker.
- `tests/test_phase473_evidence_verifier.py` — Fixture-driven receipt, outcome, coverage, privacy, and git-publication contract.
- `tests/fixtures/phase473_evidence_denylist.txt` — Fixed privacy-denial seed set bound into every receipt.
- `docs/security/phase-473-evidence-results.json` — Canonical checked gate receipts, raw artifact metadata, exact coverage, source snapshot, and external obligations.
- `docs/security/phase-473-evidence.md` — Human-readable gate, requirement, decision, finding, boundary, and external-limit evidence derived from results.
- `docs/security/phase-473-evidence-manifest.json` — Schema-v2 candidate binding and hashes for results/evidence/validation only.
- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VALIDATION.md` — Source-bound final local validation and external limitations.
- `src/stoa/jobs/teacher_escalation.py` — Removed one pre-existing extra EOF blank line that blocked the exact phase diff gate.
- `tests/test_phase473_notification_deletion.py` — Removed one pre-existing extra EOF blank line that blocked the exact phase diff gate.

## Decisions Made

- Used the latest commit changing `473-17-SUMMARY.md` as the mechanically resolved pre-closure phase base and required it to be an ancestor of every candidate.
- Treated the strict node manifest as the XFAIL/XPASS authority and cross-checked its total/failure/error/skip counts against JUnit rather than parsing console prose.
- Kept raw capture outside the repository under `/tmp/phase473-evidence/<candidate>/`; only independently verified canonical results were published.
- Distinguished purgeable exact absence from legal-retention-blocked material and provider accepted/delivered/acceptance-unknown copies outside backend purge authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cleared phase-wide diff hygiene failures**
- **Found during:** Task 3 first immutable capture
- **Issue:** `git diff --check <phaseBaseSha> <candidateSha>` found verifier trailing whitespace plus pre-existing extra EOF blank lines in two earlier Phase 473 files.
- **Fix:** Removed only the whitespace/EOF bytes; no behavior changed.
- **Files modified:** `scripts/verify_phase473_evidence.py`, `src/stoa/jobs/teacher_escalation.py`, `tests/test_phase473_notification_deletion.py`
- **Verification:** Focused pytest/Ruff passed and the exact phase diff gate passed on the new candidate.
- **Committed in:** `259a56c`

**2. [Rule 1 - Bug] Preserved the first porcelain status prefix**
- **Found during:** Task 3 dirty-publication verification
- **Issue:** Generic stdout `.strip()` removed the leading space from the first `git status --porcelain` row, producing a false four-path mismatch.
- **Fix:** Removed only trailing newlines and added a tracked four-document dirty-draft regression test.
- **Files modified:** `scripts/verify_phase473_evidence.py`, `tests/test_phase473_evidence_verifier.py`
- **Verification:** 32 focused tests and Ruff passed; dirty and clean publication checks then passed.
- **Committed in:** `cf3549a`

---

**Total deviations:** 2 auto-fixed (1 blocking hygiene issue, 1 verifier bug)
**Impact on plan:** Both fixes were necessary to make the prescribed gates truthful; neither changed application behavior or external scope.

## Issues Encountered

- The first capture stopped at the exact phase diff gate and was discarded.
- The second capture passed all 17 gates, but its publication draft exposed the porcelain-prefix bug; those results were also discarded. The complete registry was rerun from gate 1 on candidate `cf3549a`, as required.

## Authentication Gates

None.

## Known Stubs

None. Occurrences of “placeholder” in the results JSON are observed negative-test node IDs, not application or evidence stubs.

## User Setup Required

None - no external service configuration, provider call, deployment action, or production mutation was used.

## Next Phase Readiness

- Phase 473 now has source-bound local proof for V9PRIV-01/02/03 and every checked privacy boundary; independent aggregate verification can assess phase completion.
- Phase 479 still owns real S3 multipart/versioning and deployed cleanup scheduler/IaC evidence.
- Phase 480 still owns production/deployed log evidence.

## Self-Check: PASSED

- All implementation, test, fixture, evidence, validation, and summary artifacts exist.
- Task commits `2a9f441`, `dd24017`, `259a56c`, `cf3549a`, and `7a866e6` exist in repository history.
- Publication `7a866e6` is the exact four-path child of candidate `cf3549a`; all manifest hashes and byte sizes reproduce.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
