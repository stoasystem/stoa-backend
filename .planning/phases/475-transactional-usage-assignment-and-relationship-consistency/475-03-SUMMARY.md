---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 03
subsystem: database
tags: [dynamodb, reconciliation, idempotency, compensation, question-submission]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 01
    provides: atomic question admission command, capped quota counter, ledger event, and initial question
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 02
    provides: durable processing/original-result replay through the real question route
provides:
  - bounded write-free reconciliation preview for current and historical question coordinates
  - preview-bound apply with changed-row refusal and exact durable-result recovery
  - one-time terminal allowance and ledger reversal that preserves durable attachments and storage usage
affects: [475-13-integrated-evidence, 478-web-question-processing, V9DATA-01]

tech-stack:
  added: []
  patterns: [strong-read evidence digest, conditional four-row compensation, explicit-coordinate preview-first job]

key-files:
  created:
    - src/stoa/jobs/reconcile_question_submissions.py
    - tests/test_phase475_question_reconciliation.py
  modified:
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/services/usage_ledger_service.py

key-decisions:
  - "Reconciliation accepts only explicit bounded student/idempotency coordinates; it never performs an unbounded table scan."
  - "Unknown legacy counter-plus-ledger state without a question remains report-only because privacy-safe ledger evidence cannot reconstruct question content."
  - "Terminal reversal retains the ledger's original audit quantity while status=reversed removes it from active consumption totals; attachments and storage rows are excluded from the transaction."

patterns-established:
  - "Preview/apply: bind the proposed action to strong whole-row evidence digests and exact command/question versions, then refuse changed evidence."
  - "Terminal compensation: condition command, question, counter, and ledger facts in one transaction with one deterministic reversal identity."

requirements-completed: [V9DATA-01]

duration: 26 min
completed: 2026-07-22
---

# Phase 475 Plan 03: Question Reconciliation And Exact Compensation Summary

**Bounded question reconciliation now recovers durable results and reverses proven terminal admissions exactly once without deleting reusable attachments or refunding storage quota.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-22T00:29:00Z
- **Completed:** 2026-07-22T00:55:43Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added a closed reconciliation taxonomy for committed, recoverable processing, historical counter-plus-ledger partial, proven terminal, conflicting, changed, and dependency-retry evidence.
- Added pure preview and conditional apply functions that expose only opaque command/question identities, versions, evidence digest, and proposed action.
- Recovered processing commands to completed only when the exact durable question result remains present; pending work remains recoverable rather than falsely terminal.
- Added a four-row terminal transaction that marks command/question failure, decrements the exact question counter once, and marks the original ledger event reversed under one deterministic reversal identity.
- Kept attachment, association, object, and storage-counter rows entirely outside compensation and proved their byte-identical preservation.
- Added a CLI/Lambda job with preview as the default, explicit `--apply`, bounded coordinate input, and no table-wide discovery.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement idempotent question reconciliation and terminal reversal** - `aea93ed` (fix)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Reconciliation dispositions, evidence-bound preview/apply, durable-result recovery, and atomic terminal reversal.
- `src/stoa/services/usage_ledger_service.py` - Explicit active question-ledger status, reversed-event exclusion from active usage totals, and semantic terminal-reversal entrypoint.
- `src/stoa/jobs/reconcile_question_submissions.py` - Bounded preview/apply job, Lambda handler, and explicit CLI mode/coordinate contract.
- `tests/test_phase475_question_reconciliation.py` - Historical partial, zero-write preview, changed evidence, replay, attachment retention, every transaction boundary, barrier concurrency, and lost-response proof.

## Decisions Made

- Used strong whole-row SHA-256 evidence digests for the preview token while keeping private question/result bytes out of every public job result.
- Required explicit durable terminal proof fields before compensation; a broad dependency exception or merely pending question never restores allowance.
- Preserved the ledger event's original `quantity=1` for audit evidence and changed active reconciliation to ignore only rows durably marked `reversed`.
- Classified legacy counter-plus-ledger-without-question evidence as report-only because recreating private question content from a privacy-safe ledger would require guessing.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The workspace sandbox denied the first `.git/index.lock` creation. The same individually scoped files were staged and committed with approved repository permission; normal hooks ran and no verification was bypassed.

## Verification

- Exact plan command — 21 passed across reconciliation and usage-ledger tests; Ruff passed all planned repository/job/test files.
- Expanded question regression — 57 passed across reconciliation, atomic admission, route replay, legacy question routes, and usage ledger.
- Targeted mypy — no issues in `question_submission_repo.py` or `reconcile_question_submissions.py`.
- CLI contract — module help proves preview default plus explicit mutually exclusive `--preview`/`--apply` modes and exact coordinate arguments.
- `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 475-13 can bind the historical partial, changed-preview, terminal reversal, four-boundary failure, concurrency, and lost-response nodes into integrated V9DATA-01 evidence.
- Phase 478 can render pending processing and terminal resubmit guidance while reusing the durable attachment identity.

## Known Stubs

None.

## Self-Check: PASSED

- All four planned created/modified files exist in the working tree.
- Task commit `aea93ed` exists and contains exactly the four intended implementation/test files with no deletions.
- Every acceptance criterion, the exact plan verification command, expanded regression, Ruff, targeted mypy, CLI contract, and diff check pass.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
