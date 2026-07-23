---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 42
subsystem: testing
tags: [mypy, evidence, fail-closed, subprocess, source-binding]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plans: 14-41
    provides: functional gap closure and candidate runtime type cleanup
provides:
  - fail-closed unfiltered MYPY-PHASE475 evidence gate
  - exact ordered 22-file candidate runtime inventory enforcement
  - adversarial subprocess, completion-summary, and registry-drift coverage
affects: [475-43, 475-44, 475-45, V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08]

tech-stack:
  added: []
  patterns: [strict subprocess disposition, private raw artifact with public hashes, exact ordered inventory]

key-files:
  created: []
  modified:
    - scripts/verify_phase475.py
    - tests/test_phase475_evidence_verifier.py
    - src/stoa/services/teacher_dispatch_service.py
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/jobs/reconcile_question_submissions.py

key-decisions:
  - "MYPY-PHASE475 passes only when one exact-inventory mypy execution exits zero, emits no stderr or diagnostics, and reports the exact source-file count."
  - "Missing, extra, duplicate, or reordered runtime paths are registry drift and are rejected before evidence acceptance."
  - "Raw mypy output remains in the private capture tree; public receipts contain only safe counts, byte length, and SHA-256 bindings."

patterns-established:
  - "Static-analysis evidence treats timeout, execution failure, malformed UTF-8, truncated output, unexpected summaries, and every nonzero exit as FAIL."
  - "A public PASS receipt independently revalidates exact candidate files, argv hash, raw-output metadata, zero diagnostics, and zero exit status."

requirements-completed: [V9DATA-01, V9DATA-02, V9DATA-03, V9DATA-04, V9DATA-05, V9DATA-06, V9DATA-07, V9DATA-08]

duration: 17 min
completed: 2026-07-23
---

# Phase 475 Plan 42: Fail-Closed Mypy Evidence Summary

**Unfiltered Phase 475 mypy evidence now requires one genuine zero-exit, zero-diagnostic execution over the exact ordered 22-file candidate inventory, with private raw output bound by public-safe hashes.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-23T09:02:29Z
- **Completed:** 2026-07-23T09:19:35Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Removed changed-line forgiveness and renamed the gate to unfiltered `MYPY-PHASE475` semantics.
- Made every nonzero exit, ordinary diagnostic, empty output, execution exception, timeout, malformed text, stderr emission, truncated/unexpected summary, and summary-count mismatch fail closed.
- Required exact ordered equality with the candidate-derived runtime inventory, rejecting missing, extra, duplicate, and reordered paths before invoking mypy.
- Captured raw mypy output only in the private capture tree while binding public evidence to safe counts, byte length, and SHA-256 values.
- Proved a real 22-file candidate run with exit code 0, zero diagnostics, and an exact 22-source completion summary.

## Task Commits

TDD and blocking type closure were committed atomically:

1. **RED: adversarial fail-closed contract** - `12e8df0` (test)
2. **GREEN: fail-closed mypy evidence implementation** - `958d810` (fix)
3. **Blocking runtime type closure: teacher dispatch** - `3dd6657` (fix)
4. **Blocking runtime type closure: question effects** - `540f559` (fix)
5. **Blocking runtime type closure: reconciliation CLI** - `88b1bd7` (fix)

## Files Created/Modified

- `scripts/verify_phase475.py` - Exact-inventory, timeout-bounded, strict-summary mypy execution and independently verified receipt binding.
- `tests/test_phase475_evidence_verifier.py` - Adversarial outcome and registry-drift coverage plus updated unfiltered evidence rendering contract.
- `src/stoa/services/teacher_dispatch_service.py` - Runtime capability and row-shape narrowing needed for the exact candidate type gate.
- `src/stoa/db/repositories/question_submission_repo.py` - Effect-kind and persisted integer/mapping narrowing needed for zero-diagnostic evidence.
- `src/stoa/jobs/reconcile_question_submissions.py` - `argparse.ArgumentParser.error` override aligned with its `Never` return contract.

## Decisions Made

- Used the mypy process exit status and a strict full-output success grammar together; neither parser silence nor exit status alone can authorize PASS.
- Preserved the candidate-derived sorted inventory as the canonical order and compared caller input without sorting, so reordering cannot be normalized into acceptance.
- Kept diagnostic text out of public analysis. The raw private artifact is verified through its independently recorded byte length and SHA-256.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Closed 14 inherited diagnostics preventing genuine zero-exit evidence**
- **Found during:** Task 1 final real-inventory acceptance
- **Issue:** The exact candidate contained 14 diagnostics across teacher dispatch, question effect persistence, and reconciliation CLI typing. The new fail-closed gate correctly refused PASS.
- **Fix:** Narrowed the three existing runtime boundaries without exclusions, ignores, casts, dependency changes, mypy configuration changes, or business-semantic changes.
- **Files modified:** `src/stoa/services/teacher_dispatch_service.py`, `src/stoa/db/repositories/question_submission_repo.py`, `src/stoa/jobs/reconcile_question_submissions.py`
- **Verification:** Real 22-file mypy returned `status=PASS`, `tool_exit_code=0`, `diagnostic_count=0`, and `completion_source_count=22`; 69 directly relevant regressions passed.
- **Committed in:** `3dd6657`, `540f559`, `88b1bd7`

**2. [Rule 1 - Bug] Corrected stale SDK plan position and progress percentage**
- **Found during:** Plan metadata close-out
- **Issue:** `state.advance-plan` incremented a stale Plan 27 position to 28 despite 42 summaries on disk, and `state.update-progress` reported 68% while persisting 20%.
- **Fix:** Retained the SDK-recorded 136/201 completed count while correcting the next plan to 43/45 and the persisted percentage to the SDK-reported 68%.
- **Files modified:** `.planning/STATE.md`
- **Verification:** `ROADMAP.md` independently reports 42/45 Phase 475 plans and `STATE.md` records Plan 43 with 136/201 completed plans at 68%.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 2 auto-fixed (1 blocking issue, 1 metadata bug).
**Impact on plan:** The runtime narrowing was required for genuine unfiltered zero-diagnostic acceptance, and the metadata correction prevents false execution position/progress; neither introduces evidence forgiveness.

## Issues Encountered

- The first honest post-GREEN run failed with 14 diagnostics and the plan paused without SUMMARY or state advancement. After the three scoped upstream fixes landed, the same unchanged fail-closed gate passed the exact 22-file inventory.
- Git index writes required repository metadata permission; all commits used individually scoped staging and normal hooks.

## Verification

- Exact fail-closed command: PASS with exit 0, 0 diagnostics, 22 completion sources, and exact ordered 22-file inventory.
- Adversarial verifier module: 25 passed.
- Directly affected question-effect, reconciliation, replay, teacher-dispatch, and teacher-reply regressions: 69 passed with one third-party deprecation warning.
- Ruff over all 22 runtime files plus verifier and verifier tests: passed.
- `git diff --check`: passed.
- No task commit deleted a tracked file.

## User Setup Required

None - no dependency, credential, provider, deployment, schema, or external configuration change is required.

## Known Stubs

None. Empty collections in the modified files are bounded accumulators, validated defaults, or test bookkeeping; no user-visible data source is unwired.

## Next Phase Readiness

- Plans 475-43 through 475-45 can consume a fail-closed, source-bound `MYPY-PHASE475` gate.
- A tool failure or any future candidate diagnostic will now stop evidence publication instead of being rendered as PASS.

## Self-Check: PASSED

- All five modified files and this summary exist.
- Commits `12e8df0`, `958d810`, `3dd6657`, `540f559`, and `88b1bd7` exist in current history.
- Exact mypy, adversarial verifier, relevant regressions, Ruff, diff integrity, deletion scan, stub scan, and threat-boundary review passed.
- No new endpoint, authorization path, dependency, schema, or unplanned trust boundary was introduced.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-23*
