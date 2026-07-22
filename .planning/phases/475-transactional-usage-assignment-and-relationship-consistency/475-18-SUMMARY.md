---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 18
subsystem: database
tags: [dynamodb, provider-effects, idempotency, recovery, ocr, ai]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 15
    provides: opaque versioned question-submission commands and owner generation
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 17
    provides: owner/status/version CAS contract for question rows
provides:
  - durable versioned OCR and AI effect intents with strict private result receipts
  - conditional effect/question/command completion with strong-read loss reconciliation
  - source-real provider-success/local-failure recovery matrix
affects: [475-question-reconciliation, 478-question-processing, V9DATA-01, CR-01, WR-04]

tech-stack:
  added: []
  patterns: [intent-before-provider, receipt-before-projection, strong-read ambiguous-commit reconciliation]

key-files:
  created:
    - tests/test_phase475_question_effect_recovery.py
  modified:
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/routers/questions.py
    - tests/test_phase475_question_replay.py
    - tests/test_phase475_question_state_cas.py
    - tests/test_questions.py

key-decisions:
  - "Effect identity binds the opaque command digest, fingerprint, question, student, account-fence generation, and closed OCR/AI kind; command and question versions remain conditional completion coordinates."
  - "Only a durable result_ready receipt may be projected automatically; provider_inflight and provider_outcome_unknown never authorize another provider invocation."
  - "OCR completion advances both command and question versions while leaving the command processing; AI completion advances both again and terminalizes the command as completed."

patterns-established:
  - "Provider effect lifecycle: inflight intent -> bounded private result_ready receipt -> atomic completed projection."
  - "Ambiguous completion: strongly reread effect, command, and question and recognize success only when every N+1 coordinate and original result field matches."

requirements-completed: [V9DATA-01]

duration: 21 min
completed: 2026-07-22
---

# Phase 475 Plan 18: Durable Question Provider Effect Recovery Summary

**OCR and AI successes now survive local write failure through exact private receipts and converge by one conditional question/command transaction without another provider call.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-22T14:03:25Z
- **Completed:** 2026-07-22T14:24:52Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added deterministic, versioned OCR/AI effect rows bound to command digest, payload fingerprint, question, owner, account generation, effect kind, and observed command/question versions.
- Added strict 64 KiB JSON result receipts with closed OCR/AI shapes, exact digest validation, and rejection of malformed, foreign, or stale receipts before mutation.
- Added a four-operation completion transaction that checks the active owner fence and exact effect/question/command coordinates, projects the original result, marks the effect complete, and increments question and command versions once.
- Distinguished pre-provider dependency failure, provider inflight, terminal rejection, unknown provider outcome, ambiguous result receipt, completion dependency failure, and committed-response loss as closed dispositions.
- Replaced the mocked lost-response proof with a real repository-operation fake covering pre-commit failure, commit-before-timeout, conditional/stale loss, unknown and inflight replay, and both OCR and AI recovery.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing question effect recovery proof** - `abf19eb` (test)
2. **GREEN: Recover durable question provider effects** - `250767a` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Effect kinds/dispositions, deterministic identity, intent/result transitions, strict receipt validation, and conditional completion reconciliation.
- `src/stoa/routers/questions.py` - OCR/AI intent-before-provider orchestration and receipt-only replay recovery.
- `tests/test_phase475_question_effect_recovery.py` - Real admission/effect/completion transaction fake and seven boundary-recovery proofs.
- `tests/test_phase475_question_replay.py` - Removed the superseded monkeypatched lost-response proof.
- `tests/test_phase475_question_state_cas.py` - Registered the effect completion transaction as the question writer replacing route-level provider CAS.
- `tests/test_questions.py` - Migrated directly affected route fixtures from the retired mutation seam to the typed effect seam.

## Decisions Made

- Private provider results remain only on effect rows; the public question receives them only through the exact conditional completion transaction.
- Result receipt ambiguity is safe to continue only after a strong read finds the same canonical result and digest; absence or mismatch closes the effect as unknown.
- A replay may complete a ready receipt, but it never begins or reinvokes a provider for an existing inflight/unknown effect.
- Topic-seed derivation failure does not discard an otherwise valid AI result; the durable receipt preserves the validated AI response with an empty derived seed list.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migrated inherited question fixtures and writer registry to the effect seam**
- **Found during:** Task 1 GREEN regression verification
- **Issue:** Three route tests returned mocked admitted results without the newly required durable command coordinate, and the Plan 475-17 writer registry still required `submit_question` to call the retired route-level `mutate_question` path.
- **Fix:** Added typed effect lifecycle fakes only to the inherited route fixture, supplied the production-shaped command result, and registered `complete_question_effect` as the repository question writer.
- **Files modified:** `tests/test_questions.py`, `tests/test_phase475_question_state_cas.py`
- **Verification:** The necessary question/state/reconciliation regression passes 43 tests; the exact plan gate passes 30 tests.
- **Committed in:** `250767a`

---

**Total deviations:** 1 auto-fixed (1 blocking fixture migration).
**Impact on plan:** Test-only compatibility keeps inherited behavior coverage on the new durable seam; no production feature or architectural scope was added.

## Issues Encountered

- The sandbox denied normal `.git/index.lock` creation. Files were staged individually with repository approval; normal hooks ran and no verification was bypassed.
- The first GREEN run exposed an over-strict generation comparison in the new transaction fake; the fake was corrected to distinguish account-fence `generation` from command/effect `account_fence_generation` before any production conclusion was accepted.

## Verification

- Exact plan gate: 30 passed across effect recovery, route replay, and real admission; Ruff passed all planned files.
- Necessary regression gate: 43 passed across question routes, question state CAS, and question reconciliation.
- Acceptance criteria: durable bound receipts, zero-call replay, exact committed-timeout reconciliation, inflight/unknown no-reinvoke, and real repository operation execution all PASS.
- Foreign, stale, and malformed receipt rejection: PASS with zero completion writes.
- `git diff --check`: passed.

## User Setup Required

None - no dependency, credential, schema deployment, external service, or provider execution is required.

## Known Stubs

None. Empty collections and optional values in the modified production paths are bounded runtime defaults or safe derived-data fallbacks, not placeholder provider results.

## Next Phase Readiness

- CR-01 and WR-04 are closed locally through the real persistence boundary.
- Question reconciliation and Phase 478 can rely on completed commands or durable pending/unknown states without repeating OCR or AI effects.
- No real provider, production, or external-system claim was made.

## Self-Check: PASSED

- All six created/modified implementation and test files plus this summary exist.
- RED commit `abf19eb` precedes GREEN commit `250767a`; both exist and contain only the individually staged plan files.
- Exact plan verification, necessary regression, Ruff, stub scan, deletion scan, and commit isolation all pass.
- The only remaining non-planning worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
