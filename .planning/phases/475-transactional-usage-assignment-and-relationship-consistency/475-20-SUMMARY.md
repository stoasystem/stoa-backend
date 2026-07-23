---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 20
subsystem: database
tags: [dynamodb, provider-effects, compensation, idempotency, reconciliation]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 03
    provides: preview-bound exact-once question allowance and ledger reversal
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 18
    provides: versioned OCR and AI provider-effect evidence
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 19
    provides: strict owner-bound question replay classification
provides:
  - production-reachable terminal question proof from closed non-retryable evidence
  - exact-version effect, command, and question terminalization transaction
  - opaque-coordinate bounded compensation and stable create-new-submission replay
affects: [478-question-processing, V9DATA-01, CR-07]

tech-stack:
  added: []
  patterns: [closed terminal evidence promotion, opaque-coordinate direct reconciliation, exact-once reversal replay]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/jobs/reconcile_question_submissions.py
    - src/stoa/routers/questions.py
    - tests/test_phase475_question_effect_recovery.py
    - tests/test_phase475_question_reconciliation.py
    - tests/test_phase475_question_state_cas.py

key-decisions:
  - "Only closed invalid attachment/object evidence and AI response-cleanup failure can produce terminal proof; timeout, throttle, malformed dependency response, unknown outcome, and broad exceptions remain recoverable."
  - "Terminal proof advances the exact effect, command, and question versions in one account-fenced transaction before compensation receives only the opaque command digest."
  - "Terminal replay returns one stable create_new_submission action only after the existing four-row compensation is durably committed or strongly reconciled."

patterns-established:
  - "Terminal producer: terminal_rejected effect -> account-fenced effect/command/question CAS -> terminal_proven effect and terminal_failed command."
  - "Terminal handoff: exact owner plus opaque command digest -> bounded reconciliation apply -> stable coordinate-free resubmit outcome."

requirements-completed: [V9DATA-01]

duration: 16h 37m (multi-session)
completed: 2026-07-23
---

# Phase 475 Plan 20: Production-Reachable Terminal Question Compensation Summary

**Closed provider evidence now terminalizes a question through exact version conditions, reverses its allowance and ledger event once, and replays a stable resubmit action without changing reusable attachment or storage state.**

## Performance

- **Duration:** 16h 37m across an interrupted multi-session execution
- **Started:** 2026-07-22T15:40:19Z
- **Completed:** 2026-07-23T08:17:28Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added `QuestionTerminalFailureDisposition` and one production writer that requires a closed `terminal_rejected` effect, exact owner/digest/fingerprint/generation, and exact effect/command/question states and versions.
- Promoted terminal proof in one account-fenced transaction, incrementing the effect, command, and question versions while persisting coordinate-free code/time and the opaque effect identity.
- Routed proven terminal work directly into the existing bounded preview/apply reconciler using only student identity and the opaque command digest.
- Strengthened compensation conditions over command owner/schema/digest/generation/proof, question allowed state/proof/version, counter count, and ledger identity while retaining one deterministic reversal identity.
- Returned one stable `409` `create_new_submission` action after compensation, including committed-response-loss replay with no second provider call or write.
- Proved malformed dependency responses remain `provider_outcome_unknown`, keep the command processing, and do not reverse counter or ledger usage.
- Preserved attachment, association, object, and attachment-storage rows byte-for-byte across terminal transition, reversal, response loss, and replay.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing production terminal compensation proof** - `fde58af` (test)
2. **RED refinement: Exclude malformed dependency evidence** - `2a5abdb` (test)
3. **GREEN: Prove and compensate terminal question failures** - `b34c72f` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Closed terminal disposition/result, exact effect-command-question proof transaction, strict replay proof requirements, and stronger reversal conditions.
- `src/stoa/jobs/reconcile_question_submissions.py` - Single-coordinate production apply helper with the existing opaque bounded contract.
- `src/stoa/routers/questions.py` - Closed failure classification, terminal proof handoff, stable resubmit projection, and replay convergence.
- `tests/test_phase475_question_effect_recovery.py` - Real route failure, response-loss replay, reusable-row retention, and malformed-dependency no-refund proof.
- `tests/test_phase475_question_reconciliation.py` - Terminal boundary fixtures updated to the production proof/version contract.
- `tests/test_phase475_question_state_cas.py` - Closed direct-question-writer registry entry for the new versioned terminal producer.

## Decisions Made

- OCR `invalid_attachment` and `invalid_object` are closed durable terminal facts; OCR malformed provider responses remain unknown and cannot refund quota.
- AI `response_cleanup_failed` is the only current AI terminal fact; `malformed_response`, timeout, throttle, and broad exceptions remain recoverable.
- The question remains `pending` during proof production but receives the same proof and an incremented version; only the exact compensation transaction changes it to `submission_failed`.
- Public terminal replay is emitted only after bounded reconciliation reports the stored coordinate as committed with no remaining action.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Registered the new terminal producer in the closed question-writer inventory**
- **Found during:** Necessary question-state CAS regression after GREEN
- **Issue:** The Plan 475-17 source-backed registry rejected the new direct versioned question update until its reviewed writer name was explicitly registered.
- **Fix:** Added `prove_terminal_question_failure` to the exact repository writer allowlist.
- **Files modified:** `tests/test_phase475_question_state_cas.py`
- **Verification:** The 41-node admission/state-CAS/route regression and the 90-node combined necessary regression both pass.
- **Committed in:** `b34c72f`

---

**Total deviations:** 1 auto-fixed (1 blocking test registry update).
**Impact on plan:** The change preserves the existing closed-writer safety boundary and adds no new production behavior beyond the planned terminal CAS.

## Issues Encountered

- Execution crossed an interrupted session boundary; the committed RED gates and uncommitted GREEN work were preserved and resumed without reset, rewrite, branch, or worktree changes.
- Targeted mypy reports 12 inherited diagnostics in the previously existing effect/job/router code. New terminal-proof changed lines introduce no mypy diagnostic; the plan's pytest and Ruff gates are clean.

## Verification

- Exact plan gate: 49 passed across effect recovery, reconciliation, and strict replay; Ruff passed all five planned source/test paths.
- Necessary regression: 90 passed across effect recovery, reconciliation, replay, admission, question state CAS, and inherited question routes.
- Acceptance nodes: 5 passed for production terminal proof, malformed dependency no-refund, concurrent exact-once reversal, four transaction-boundary zero-partial-write behavior, and the closed question-writer registry.
- `git diff --check`: passed.
- No real provider, production resource, external system, dependency install, branch, or worktree was used.

## User Setup Required

None - no dependency, credential, schema deployment, external service, or provider execution is required.

## Known Stubs

None. Empty collections and optional values in touched paths are bounded runtime defaults, result accumulators, or absent optional provider state rather than placeholders.

## Next Phase Readiness

- CR-07 and D-03 are closed locally through the production route and real repository transaction boundary.
- Phase 478 can render `question_submission_terminal_failed` as a create-new-submission action while reusing the retained opaque attachment identity.
- Phase-level aggregate verification may now include the production terminal writer and response-loss replay nodes.

## Self-Check: PASSED

- All six modified implementation/test files and this summary exist.
- RED commits `fde58af` and `2a5abdb` precede GREEN commit `b34c72f`; all three commits exist.
- GREEN contains exactly the six intended plan/deviation files, with no deletions and none of the five user-owned parallel paths.
- Exact plan verification, necessary regression, acceptance nodes, Ruff, stub scan, and diff check pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-23*
