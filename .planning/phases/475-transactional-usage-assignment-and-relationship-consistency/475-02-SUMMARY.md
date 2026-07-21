---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 02
subsystem: api
tags: [fastapi, dynamodb, idempotency, question-submission, attachments]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 01
    provides: durable payload-bound question admission and atomic quota/ledger/question/attachment transaction
provides:
  - question route backed exclusively by the atomic admission command
  - durable pending and original-result replay projection
  - structured payload-mismatch, quota, and retryable admission actions
affects: [475-03-question-reconciliation, 478-web-question-processing, V9DATA-01]

tech-stack:
  added: []
  patterns: [durable-command preflight replay, admitted-owner provider effects, coordinate-free structured recovery actions]

key-files:
  created:
    - tests/test_phase475_question_replay.py
  modified:
    - src/stoa/models/question.py
    - src/stoa/routers/questions.py
    - tests/test_questions.py

key-decisions:
  - "Only the ADMITTED disposition owns OCR and AI effects; RESUME projects the strongly persisted original question without reserving an attachment or invoking a provider again."
  - "Question admission failures use closed coordinate-free codes and explicit client actions: create a new submission, wait for quota reset, or retry the same submission identity."
  - "The initial pending question and coordinate-free attachment summary remain returnable even when later OCR, AI, or attachment-summary reads fail."

patterns-established:
  - "Route admission: fingerprint and preflight durable replay, reserve/prepare once, atomically admit, then run OCR/AI only for the new owner."
  - "Post-admission provider failure returns the durable pending question rather than a false terminal failure."

requirements-completed: [V9DATA-01]

duration: 10 min
completed: 2026-07-21
---

# Phase 475 Plan 02: Atomic Question Route Replay Summary

**Question submission now exposes one durable pending/original result while atomic admission prevents retries from duplicating quota, ledger, attachment, OCR, or AI effects.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-21T23:17:36Z
- **Completed:** 2026-07-21T23:27:42Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Removed the route's independent daily-counter, usage-ledger, question-put, and attachment-commit sequence and replaced it with Plan 475-01's single atomic admission command.
- Added durable command preflight and strong persisted-question projection so same-key replay returns the original question without another attachment reservation, OCR call, AI call, quota charge, or ledger event.
- Added explicit pending processing projection plus structured 409 mismatch, 429 quota, and 503 retry-same-submission responses.
- Moved OCR/AI after durable admission and preserved a queryable pending question when either provider fails.
- Preserved owner authorization, attachment coordinate concealment, exact subject/content fingerprinting, and privacy-safe ledger construction across the route migration.

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate the question route to atomic admission and safe replay** - `f8e951e` (feat)

## Files Created/Modified

- `src/stoa/models/question.py` - Added submission-failed lifecycle vocabulary and closed question-admission error codes.
- `src/stoa/routers/questions.py` - Atomic admission orchestration, replay projection, prepared attachment operations, structured errors, and admitted-owner OCR/AI execution.
- `tests/test_questions.py` - Migrated inherited quota, ledger, OCR, attachment, mismatch, and failure assertions to the atomic route contract.
- `tests/test_phase475_question_replay.py` - Lost-response replay, changed-payload, quota, dependency, pending-state, and provider-effect proof.

## Decisions Made

- Used the durable command as the pre-reservation replay boundary; an unreadable command dependency returns a safe 503 before attachment mutation.
- Kept `pending` as the public processing state and added `submission_failed` for Plan 475-03's proven-terminal convergence path.
- Returned coordinate-free prepared attachment metadata directly for the admitted response and treated a later summary-read outage as non-fatal to question replay.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Targeted mypy reports three pre-existing `object` narrowing errors in unchanged teacher-escalation/feedback sections of `src/stoa/routers/questions.py` (lines 563, 569, and 616 after this edit). New admission and replay code introduces no mypy errors.

## Verification

- Plan verification command — 252 passed across question, replay, and attachment security nodes; Ruff passed all planned files.
- Expanded route/admission/authorization regression — 336 passed across students, questions, replay, attachment security, lower-boundary admission, usage ledger, and student authorization.
- Acceptance node gate — 5 passed for lost-response replay, mismatch, quota, dependency stop-before-reservation, and durable pending projection.
- Legacy sequence guard — no `record_daily_question_usage`, `record_question_usage_event`, `put_question`, or `commit_question_with_attachment` call remains in `submit_question`.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 475-03 to reconcile durable processing commands and perform proven-terminal allowance/ledger reversal without deleting reusable attachments.
- Phase 478 can render the existing `pending` state as the selected Web processing experience and use the structured recovery actions.

## Known Stubs

None.

## Self-Check: PASSED

- All four created/modified files exist in the working tree.
- Task commit `f8e951e` exists and contains exactly the four planned implementation/test files with no deletions.
- Every task acceptance criterion and the complete automated verification command pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-21*
