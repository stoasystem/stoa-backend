---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 01
subsystem: database
tags: [dynamodb, transactions, idempotency, quota, usage-ledger]

requires:
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: active account fences, prepared attachment transactions, and privacy-safe durable command patterns
provides:
  - durable payload-bound question-submission command
  - one capped transaction for quota, ledger, question, and prepared attachment effects
  - typed replay, mismatch, quota, and retryable admission outcomes
affects: [475-02-question-route-replay, 475-03-question-reconciliation, V9DATA-01]

tech-stack:
  added: []
  patterns: [length-prefixed canonical fingerprints, strong-read ambiguity reconciliation, single-item-target DynamoDB transactions]

key-files:
  created:
    - src/stoa/db/repositories/question_submission_repo.py
    - tests/test_phase475_question_admission.py
  modified:
    - src/stoa/services/usage_ledger_service.py

key-decisions:
  - "Question idempotency uses a durable application command with a domain-separated, length-prefixed payload fingerprint; DynamoDB client tokens are not the source of truth."
  - "Prepared attachment operations are folded into the admission transaction after duplicate account-fence and question-put actions are removed, preserving DynamoDB's one-action-per-item rule."
  - "Ambiguous writes are reconciled by a strong command read; quota exhaustion is returned only from durable counter evidence."

patterns-established:
  - "Question admission outcome: ADMITTED owns new downstream work; RESUME projects the original durable command; mismatch, quota, and dependency outcomes remain typed."
  - "Usage ledger items can be built without persistence and committed inside a wider domain transaction."

requirements-completed: [V9DATA-01]

duration: 9 min
completed: 2026-07-21
---

# Phase 475 Plan 01: Atomic Question Admission Summary

**A durable question command now commits one capped quota charge, privacy-safe ledger event, initial question, and any prepared attachment effects as a single replayable DynamoDB transaction.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-21T21:19:14Z
- **Completed:** 2026-07-21T21:28:10Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added exact payload binding over normalized subject, exact original/corrected UTF-8 bytes, and ordered opaque attachment identities.
- Added one duplicate-target-safe transaction containing the active account fence, durable command, capped counter update, ledger event, initial question, and prepared attachment mutations.
- Added strong-read recovery so contention and commit-then-timeout replay the original command while changed payloads, durable quota exhaustion, and dependency failures remain distinct.
- Added deterministic lower-boundary tests for transaction shape, concurrency, changed-payload rejection, ambiguous transport, pre-commit failure, full quota, and privacy-safe metadata.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement the atomic question-admission command** - `e34dc2a` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Durable command identity, fingerprinting, transaction construction, strong reads, and typed admission outcomes.
- `src/stoa/services/usage_ledger_service.py` - Pure privacy-safe question usage event builder while preserving the existing sequential writer compatibility path.
- `tests/test_phase475_question_admission.py` - Transaction-shape, concurrency, timeout ambiguity, quota, mismatch, and privacy proof.

## Decisions Made

- Used a domain-separated length-prefixed SHA-256 fingerprint so field boundaries, missing corrected text, Unicode bytes, and attachment order cannot collapse into the same logical payload.
- Kept the transaction builder compatible with the existing prepared attachment operation list and removed only its duplicate account-fence and question-put operations.
- Required a strong durable command read before returning replay or mismatch and after any transaction exception; no provider message, item, or coordinate reaches the typed result.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The combined targeted mypy run exposed five pre-existing `object`-to-`int` narrowing errors in unchanged usage reconciliation code. The new repository passes mypy independently; the unrelated baseline is recorded in `deferred-items.md` and was not broadened into this plan.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_question_admission.py` — 8 passed.
- `.venv/bin/ruff check src/stoa/db/repositories/question_submission_repo.py src/stoa/services/usage_ledger_service.py tests/test_phase475_question_admission.py` — passed.
- `.venv/bin/python -m pytest -q tests/test_phase475_question_admission.py tests/test_usage_ledger.py` — 20 passed, one existing Starlette deprecation warning.
- `.venv/bin/mypy src/stoa/db/repositories/question_submission_repo.py` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 475-02 to route real question submissions through `admit_question_submission()` and project durable processing/replay outcomes.
- Plan 475-03 can extend the persisted command version/state for bounded reconciliation and exact terminal compensation.

## Self-Check: PASSED

- Both created files and the modified usage service exist in the working tree.
- Task commit `e34dc2a` exists and contains exactly the three planned implementation/test files.
- All plan acceptance criteria and focused verification commands pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
