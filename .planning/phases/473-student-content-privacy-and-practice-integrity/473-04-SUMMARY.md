---
phase: 473-student-content-privacy-and-practice-integrity
plan: 04
subsystem: question-attachment-privacy
tags: [dynamodb, rekognition, ocr, attachments, idempotency, privacy]

requires:
  - phase: 473-02
    provides: Validated owner upload intents, private immutable coordinates, and quota transactions
  - phase: 473-03
    provides: Durable saved attachments, safe summaries, reuse, and reference-aware retention
provides:
  - Opaque upload-or-saved-attachment question request contract without caller-selected storage coordinates
  - Exclusive fresh-upload reservation and atomic question, association, consumption, attachment, and storage transaction
  - Zero-byte-charge saved owner image reuse with conditional reference accounting
  - Resolved-attachment-only OCR boundary with safe transient release and terminal invalidation
  - Keyless and raw-OCR-free question responses plus executable nested authorization inventory
affects: [473-07, 475-question-convergence, 478-mobile]

tech-stack:
  added: []
  patterns:
    - Fresh question images transition validated-to-consuming before OCR and commit only in the question transaction
    - OCR accepts one internal active JPEG/PNG attachment record rather than bucket/key arguments
    - Public question projections rebuild only safe attachment summaries from opaque attachment IDs

key-files:
  created: []
  modified:
    - src/stoa/models/question.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/services/ocr_service.py
    - src/stoa/routers/questions.py
    - tests/test_questions.py
    - tests/test_attachment_security.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Question idempotency binds the original opaque upload or saved-attachment identity, never a bucket or object key."
  - "Fresh upload reservation precedes quota and OCR effects; consumption, durable attachment, association, first-byte charge, and question persistence share one conditional transaction."
  - "Saved owner JPEG/PNG reuse increments only the logical reference count and creates a question association, with no storage-byte mutation."
  - "OCR provider coordinates and raw detected text remain private; public responses expose only safe attachment summary and bounded OCR metadata."

patterns-established:
  - "Question attachment command: idempotency check, owner/state/type reservation, quota, resolved OCR, privacy-safe ledger boundary, then conditional question transaction."
  - "OCR recovery: transient provider failures release a fresh reservation within its original expiry; terminal object/content failures make the resource non-reusable."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 14 min
completed: 2026-07-16
---

# Phase 473 Plan 04: Atomic question attachment consumption and OCR privacy Summary

**Question OCR now accepts only an owner-resolved active JPEG/PNG, while fresh upload consumption and saved-image association commit conditionally with the question and expose only opaque safe metadata.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-16T11:15:00Z
- **Completed:** 2026-07-16T11:28:57Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Removed `image_s3_key` and all bucket/object-key inputs from the public question request and response models, replacing them with exactly one optional opaque `uploadId` or `attachmentId` reference.
- Added conditional fresh-upload reservation plus one DynamoDB transaction covering upload consumption, durable attachment creation, question association, first storage charge, and question persistence.
- Added active saved-owner JPEG/PNG reuse that conditionally increments its logical reference without duplicating bytes or changing storage usage.
- Replaced the bucket/key OCR API with a resolved internal attachment boundary; transient failures release the reservation and terminal object failures invalidate the resource through stable redacted errors.
- Kept raw OCR text available only to private question/AI processing while public create/get responses expose safe attachment summaries and bounded OCR metadata.

## Task Commits

1. **Task 1: Replace question S3-key input with atomic attachment transaction** - `f35f714` (feat)
2. **Task 2: Route OCR through resolved private attachment and preserve safe responses** - `e86ddae` (feat)
3. **Acceptance follow-up: Regenerate nested attachment authorization evidence** - `eb73d69` (fix)

## Files Created/Modified

- `src/stoa/models/question.py` - Opaque attachment input and safe attachment-summary response contract.
- `src/stoa/db/repositories/attachment_repo.py` - Question reservation, release/invalidation, association, reuse, and atomic transaction builders.
- `src/stoa/db/repositories/question_repo.py` - Canonical question transaction-item builder.
- `src/stoa/services/attachment_service.py` - Owner/type/status resolution, fresh reservation, saved reuse, rollback, invalidation, and atomic commit orchestration.
- `src/stoa/services/ocr_service.py` - Resolved-attachment-only OCR boundary with closed safe failure categories.
- `src/stoa/routers/questions.py` - Idempotency-safe attachment flow, private OCR use, structured error mapping, and safe response projection.
- `tests/test_questions.py`, `tests/test_attachment_security.py` - OpenAPI, ownership, type, expiry, reuse, quota, transaction, OCR spy/failure, idempotency, and redaction matrix.
- `docs/security/route-authorization-inventory.json` - Runtime-identical nested `uploadId`/`attachmentId` authorization projection.

## Decisions Made

- Preserve the existing daily question counter and ledger ordering and explicitly leave all-side-effect convergence to Phase 475; this plan makes only the attachment/question boundary atomic.
- Reserve fresh uploads before the existing quota counter so a missing, foreign, expired, invalid, non-image, or already-consumed resource cannot cause counter, OCR, association, or question effects.
- Store the original opaque attachment command identity privately for exact idempotent retry comparison; a different attachment under the same idempotency key returns a safe conflict before mutation.
- Keep the student-visible question content as the submitted or corrected text; OCR text may enrich the private AI input but is never echoed through `QuestionResponse`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Regenerated executable nested attachment authorization evidence**
- **Found during:** Plan-level Phase 473 matrix after Task 2
- **Issue:** Runtime and OpenAPI correctly described question-body `uploadId`/`attachmentId` authorization, but the checked JSON still contained the pre-migration question projection.
- **Fix:** Regenerated the deterministic route authorization inventory from the registered application.
- **Files modified:** `docs/security/route-authorization-inventory.json`
- **Verification:** Route inventory plus focused question/attachment gate: 99 passed; full Phase 473 matrix: 198 passed.
- **Committed in:** `eb73d69`

---

**Total deviations:** 1 auto-fixed (1 missing critical). **Impact:** The fix preserves the Phase 472 fail-closed executable inventory without broadening authorization or changing runtime behavior.

## Issues Encountered

- The first combined Phase 473 run failed only because the checked authorization inventory had not yet been regenerated; runtime behavior and focused privacy tests were already green. Regeneration resolved the mismatch.
- The standard tracking helpers counted 5/7 summaries correctly but rewrote the curated milestone name/progress and collapsed the Phase 473 roadmap row columns; the exact existing milestone metadata and roadmap shape were restored while retaining the new counts, Plan 6 position, metrics, decisions, and session record.

## User Setup Required

None - no external service configuration required.

## Verification

- Focused question/attachment suite: **72 passed**.
- Plan task filters for attachment/idempotency/transactions and OCR/ownership/redaction: **52 passed** and **13 passed** respectively.
- Full Phase 473 privacy/practice/authorization matrix: **198 passed**.
- Full backend suite: **1200 passed** (prior baseline 1189 plus 11 new tests).
- Ruff on all changed Python files: PASS.
- Python compileall and `git diff --check`: PASS.
- No ambient AWS, provider, or network access was used by tests.

## Next Phase Readiness

- Plan 473-07 can include the question path in the combined upload cleanup and privacy evidence gate.
- Phase 475 still owns daily counter, usage-ledger, and question all-side-effect convergence; this plan neither claims nor weakens that deferred boundary.
- Phase 478 mobile can submit only opaque upload/saved-attachment references and render safe attachment summaries.

## Self-Check: PASSED

- Every named modified file exists and all three Plan 473-04 implementation/follow-up commits are present.
- Both task acceptance gates, the complete Phase 473 matrix, the full repository suite, static checks, and public contract redaction checks pass.
- No known stubs or unplanned threat surfaces remain in the modified files.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
