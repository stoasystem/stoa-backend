---
phase: 473-student-content-privacy-and-practice-integrity
plan: 03
subsystem: conversation-attachments
tags: [dynamodb, s3, pypdf, ooxml, privacy, retention, bedrock]

requires:
  - phase: 473-02
    provides: Validated owner upload intents, immutable private coordinates, and quota transactions
provides:
  - Atomic fresh/reused attachment binding for regular and streaming conversation messages
  - Safe durable attachment summaries in message responses and conversation history
  - Bounded passive PDF, DOCX, PPTX, XLSX, TXT, and MD extraction for AI-only context
  - Reference-counted conversation release and idempotent student purge hooks
affects: [473-04, 473-07, 478-mobile, account-closure]

tech-stack:
  added: []
  patterns:
    - One preflight and transaction path shared by regular and streaming message sends
    - Deletion-pending tombstones separate last-reference release from idempotent object deletion
    - Allowlisted passive OOXML extraction with category-only parser failures

key-files:
  created:
    - src/stoa/services/document_extraction_service.py
  modified:
    - src/stoa/models/attachment.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/routers/conversations.py
    - src/stoa/services/ai_service.py
    - src/stoa/security/authorization.py
    - src/stoa/security/route_inventory.py
    - docs/security/route-authorization-inventory.json
    - tests/test_conversations.py
    - tests/test_attachment_security.py

key-decisions:
  - "A message, fresh upload consumption, durable attachment, associations, and one aggregate storage charge commit in one DynamoDB transaction."
  - "Saved attachment reuse increments only its durable reference count and creates an association; it never changes storage bytes."
  - "Last-reference deletion first creates a non-reusable deletion-pending tombstone, then deletes S3 bytes and decrements quota in a retry-safe finalize transaction."
  - "Extracted text is silently sanitized and passed only as bounded model context; public history stores attachment IDs and safe metadata only."

patterns-established:
  - "Conversation attachment command: resolve the complete owner list before rate, message, quota, or AI effects, then conditionally recheck every member in one transaction."
  - "Parser boundary: read only allowlisted passive document parts, reject macros/external relationships/entities/encryption/limits, and discard exception detail."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 18 min
completed: 2026-07-16
---

# Phase 473 Plan 03: Durable conversation attachment history and reuse Summary

**Conversation files now persist as owner-scoped reusable resources, reach AI through bounded passive extraction, and survive or release storage according to durable reference count without leaking private coordinates or content.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-16T10:55:00Z
- **Completed:** 2026-07-16T11:13:12Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Replaced inert string attachment IDs with bounded typed fresh-upload/saved-attachment references and one shared regular/stream binding command.
- Added atomic message, upload-consumption, durable attachment, association, reference-count, and aggregate quota operations; reuse creates no new bytes or quota charge.
- Added safe attachment summaries to send, stream, and history projections while retaining object coordinates and extracted content exclusively server-side.
- Added bounded passive PDF/OOXML/text extraction, silent prompt sanitization, reference-aware conversation release, and idempotent account-closure purge hooks.

## Task Commits

1. **Task 1: Bind fresh and saved attachments atomically to conversation messages** - `ff8209a` (feat)
2. **Task 2: Add bounded document extraction and reference-aware retention hooks** - `53b3d89` (feat)
3. **Acceptance follow-up: Inventory nested attachment authorization** - `36d1a3d` (fix)

## Files Created/Modified

- `src/stoa/services/document_extraction_service.py` - Passive bounded document extractors with stable safe failure categories.
- `src/stoa/db/repositories/attachment_repo.py` - Message binding, reference counting, release tombstone, and quota finalize transactions.
- `src/stoa/services/attachment_service.py` - Owner preflight, binding, safe summaries, AI context, conversation release, and student purge orchestration.
- `src/stoa/routers/conversations.py` - Typed attachment commands, regular/stream parity, safe history summaries, and AI-only context wiring.
- `src/stoa/services/ai_service.py` - Silent bounded sanitization and isolated attachment prompt context.
- `src/stoa/models/attachment.py` - Stable typed reference identity for duplicate rejection.
- `src/stoa/security/authorization.py`, `src/stoa/security/route_inventory.py` - Closed attachment resource vocabulary and nested identifier compatibility.
- `docs/security/route-authorization-inventory.json` - Regenerated executable route projection.
- `tests/test_conversations.py`, `tests/test_attachment_security.py` - Fresh/reuse/foreign/quota/stream/history/parser/retention/purge/redaction controls.

## Decisions Made

- The complete reference list is owner-resolved before rate limiting; the transaction conditionally rechecks every upload or saved attachment before the first durable effect.
- Storage capacity is preflighted for zero-effect quota rejection and conditionally enforced again in the same transaction as new-byte charging.
- Streaming emits the same serialized student attachment summary as the regular response before assistant deltas.
- Images remain supported durable attachments but yield the stable internal `no_extractable_text` category instead of invoking OCR through the document parser.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added nested attachment authorization inventory vocabulary**
- **Found during:** Plan-level Phase 473 authorization gate
- **Issue:** The new typed body exposed `uploadId`, but conversation send dependencies described only the conversation resource, causing the closed executable route inventory to fail.
- **Fix:** Added the attachment resource type, exact `attachmentId` compatibility, and one executable attachment-command dependency that performs the real owner preflight and declares upload/attachment specs; regenerated checked evidence.
- **Files modified:** `src/stoa/security/authorization.py`, `src/stoa/security/route_inventory.py`, `src/stoa/routers/conversations.py`, `docs/security/route-authorization-inventory.json`
- **Verification:** Full Phase 473 matrix: 187 passed; route inventory subset: 34 passed.
- **Committed in:** `36d1a3d`

---

**Total deviations:** 1 auto-fixed (1 missing critical). **Impact:** Preserved the Phase 472 fail-closed route inventory while making nested opaque references executable and source-bound; no authorization broadening.

## Issues Encountered

- The first broader phase run failed only the route-inventory checks above; all runtime conversation and attachment tests were already green. The missing executable metadata was added and every affected gate passed on rerun.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 focused conversation/attachment gate: **50 passed**.
- Task 2 focused parser/retention gate: **57 passed**.
- Full Phase 473 route/privacy matrix: **187 passed**.
- Full backend suite: **1189 passed** (requested baseline 1176 plus 13 new tests).
- Ruff on all changed Python files: PASS.
- `git diff --check`: PASS.
- No ambient AWS, provider, or network access was used by tests.

## Next Phase Readiness

- Plan 473-04 can consume the same owner-preflight and immutable attachment records for question OCR without accepting raw storage coordinates.
- Plan 473-07 can reuse the deletion-pending and owner-query patterns for abandoned/invalid upload cleanup.
- Account closure has an explicit `purge_student_attachments(student_id)` hook; no public account workflow was added because none exists in this repository.

## Self-Check: PASSED

- The extraction service and every named service operation exist on disk.
- All three implementation/follow-up commits are present in repository history.
- Both task acceptance gates, plan-level verification, Phase 473 matrix, and full repository suite pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
