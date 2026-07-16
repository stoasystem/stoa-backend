---
phase: 473-student-content-privacy-and-practice-integrity
plan: 09
subsystem: attachment-transaction-security
tags: [dynamodb, transactions, privacy, quota, stable-errors, atomicity]

requires:
  - phase: 473-08
    provides: Opaque chunk gateway, immutable attachment tuples, and pinned transaction inputs
provides:
  - Closed operation-index attachment transaction outcomes
  - Stable quota, concealed-resource, and retryable-dependency public mappings
  - Category-only DynamoDB cancellation parsing without provider diagnostics
  - Fresh and reused question/message zero-effect cancellation matrices
affects: [473-10, 473-11, 475-transaction-consistency, 478-mobile-uploads]

tech-stack:
  added: []
  patterns:
    - Semantic transaction descriptors shared by fake and serialized DynamoDB paths
    - Closed internal outcomes projected to stable redacted attachment errors

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - tests/test_attachment_security.py
    - tests/test_questions.py
    - tests/test_conversations.py

key-decisions:
  - "Only a conditional failure at the named storage quota operation may produce quota_exceeded; every owner, status, attachment, association, message, or question condition remains concealed."
  - "Transaction cancellation parsing consumes only the ordered Code fields; provider messages, items, keys, owner IDs, coordinates, and exception text are discarded at the repository boundary."
  - "Transaction conflict, throughput, throttling, malformed cancellation reasons, and unclassified client failures converge on one retryable_dependency outcome."

patterns-established:
  - "Semantic index boundary: builders label each atomic operation before fake execution or low-level AttributeValue serialization."
  - "Privacy-safe failure precedence: any resource conditional conflict conceals existence even if a quota condition is also reported."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 8 min
completed: 2026-07-16
---

# Phase 473 Plan 09: Stable transaction-cancellation taxonomy Summary

**Question and conversation attachment transactions now preserve all-or-nothing writes while returning quota recovery, concealed not-found, or redacted retry guidance from semantic operation indices and cancellation codes only.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-16T15:41:48Z
- **Completed:** 2026-07-16T15:49:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `TransactionOperation` descriptors and a closed `AttachmentTransactionOutcome` taxonomy to the exact question/message transaction builders without changing their DynamoDB conditions or atomic grouping.
- Classified only the named storage condition as quota exhaustion; concealed every resource condition and mapped conflict, throttling, dependency, missing, malformed, and unclassified cancellations to one retryable category.
- Removed raw cancellation diagnostics from the repository exception boundary and proved identical high-level fake and serialized low-level classification.
- Added fresh/reused question/message cancellation matrices proving no upload consumption, attachment/association/ref/storage/resource, parser/OCR, or AI state survives an injected failure.
- Preserved safe public error bodies and recovery contracts: delete-or-upgrade for quota, retry-later for dependency failure, and select/upload-again for concealed conflicts.

## Task Commits

Each task was committed atomically with hooks enabled:

1. **Task 1: Add operation-index and category-only repository outcomes** - `dc902f7` (feat)
2. **Task 2: Map stable public codes and prove zero-effect quota/dependency races** - `537b07b` (fix)

**Plan metadata:** committed with this summary and tracking update.

## Files Created/Modified

- `src/stoa/db/repositories/attachment_repo.py` - Semantic operation descriptors, closed transaction outcomes, code-only cancellation classification, and shared serialization indices.
- `src/stoa/services/attachment_service.py` - Exhaustive internal-outcome to stable public attachment-error mapping.
- `tests/test_attachment_security.py` - Operation-index, malformed/dependency, redaction, immutable-state, and fresh/reuse matrices.
- `tests/test_questions.py` - Quota-race route projection, reservation release, response redaction, and no-AI control.
- `tests/test_conversations.py` - Retryable cancellation route projection with no message, extraction, usage-event, or AI effect.

## Decisions Made

- Resource concealment has precedence when multiple conditional failures are reported, preventing a quota response from becoming an owner/status existence oracle.
- A missing or misaligned cancellation-reason array is never guessed; it becomes a redacted retryable dependency outcome.
- Existing non-question/message lifecycle transactions retain their prior repository conflict behavior; the new semantic classifier is limited to builders with named operation indices.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The sandbox denied the first Git index lock creation. The same scoped staging and commits were rerun through the approved Git path; hooks remained enabled and were not bypassed.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 transaction classification/redaction filter: **31 passed, 62 deselected**.
- Task 2 stable-error/zero-effect filter: **14 passed, 115 deselected**.
- Plan files/attachment/question/conversation matrix: **135 passed**.
- Full Phase 473 validation matrix: **275 passed**.
- Full repository suite: **1,277 passed** (requested Plan 08 baseline: 1,243; +34 cancellation controls).
- Targeted Ruff and `git diff --check`: PASS.
- Route/inventory generation was not required because no route, model, dependency, or authorization metadata changed.

## Next Phase Readiness

- Plan 473-10 can extend the semantic descriptor vocabulary for command/quota idempotency operations and reuse `retryable_dependency` for claim/concurrency recovery.
- Plan 473-11 remains pending; Phase 473 is intentionally still in progress and must not be marked complete.

## Self-Check: PASSED

- Both task commits exist and all five named modified files are present.
- Every task acceptance filter, plan verification, Phase 473 matrix, static gate, and full repository suite passed.
- Cancellation exceptions and public responses contain no provider diagnostic, private key, owner, immutable coordinate, or seeded canary.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
