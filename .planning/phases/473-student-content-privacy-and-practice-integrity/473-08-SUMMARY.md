---
phase: 473-student-content-privacy-and-practice-integrity
plan: 08
subsystem: immutable-upload-security
tags: [fastapi, s3, dynamodb, multipart, checksum, privacy, versioning]

requires:
  - phase: 473-07
    provides: Owner upload lifecycle, bounded cleanup, durable attachment retention, OCR isolation, and source-bound privacy evidence
provides:
  - Opaque authenticated upload intent, exact-size chunk, and completion routes without provider coordinates
  - Checksum-bound fenced multipart part ledger with replay and split-failure reconciliation
  - Bounded seekable validation and same-stream promotion to fresh server-only immutable versions
  - Version/checksum-bound OCR, extraction, association, release, purge, and cleanup operations
affects: [473-09, 473-10, 473-11, 478-mobile-uploads, 479-storage-infrastructure]

tech-stack:
  added: []
  patterns:
    - Conditional checksum-and-length part claim before every provider mutation
    - One bounded spool is the validation and immutable-promotion source of truth
    - Exact key-plus-VersionId coordinates for all reads, references, and deletion

key-files:
  created: []
  modified:
    - src/stoa/models/attachment.py
    - src/stoa/security/attachment_errors.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/file_validation_service.py
    - src/stoa/services/attachment_service.py
    - src/stoa/services/document_extraction_service.py
    - src/stoa/services/ocr_service.py
    - src/stoa/routers/files.py
    - tests/test_files.py
    - tests/test_attachment_security.py
    - tests/test_questions.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Public upload APIs expose only opaque intent/chunk state and never a URL, POST field, bucket, key, multipart ID, ETag, version ID, or provider name."
  - "Every provider UploadPart is preceded by a conditional checksum/length claim with a bounded lease and one fenced takeover; replay adopts only a matching server-listed part."
  - "Validation and promotion share one bounded spool, and every durable consumer uses the promoted immutable key, VersionId, ETag, SHA-256, and length tuple."

patterns-established:
  - "Opaque gateway: issue privately, accept exact 5 MiB non-final chunks, assemble from server-held ETags, and return coordinate-free receipts."
  - "Immutable bytes: read one staging version, incrementally hash and validate it, promote the rewound stream once, persist its exact tuple, then delete only the recorded staging version."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 22 min
completed: 2026-07-16
---

# Phase 473 Plan 08: Opaque upload gateway and immutable-byte promotion Summary

**Authenticated bounded chunks now converge through checksum-fenced multipart state, while the exact bytes validated in a 1 MiB-memory spool are promoted to a fresh server-only version consumed by every attachment path.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-07-16T15:16:25Z
- **Completed:** 2026-07-16T15:37:55Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Removed `/files/presign`, `/files/{upload_id}/finalize`, presigned POST generation, and public URL/field contracts; added Actor-owned intent, exact chunk, and completion routes.
- Added a private multipart ledger whose `uploading` checksum/length claim and fence precede provider mutation, with different-byte conflict, same-byte replay, listed-part adoption, and terminal abort behavior.
- Added exact 5 MiB non-final chunk and declared-remainder enforcement, expected-plus-one reads, 10 MiB image/50 MiB document ceilings, incremental SHA-256, and closed spooled temporaries.
- Read one recorded staging VersionId into a bounded spool, validated that stream, promoted the same rewound bytes to a fresh server-only immutable version, and stored its exact length/SHA/ETag/version tuple.
- Migrated durable association, Rekognition, extraction, last-reference release, purge, expired cleanup, multipart abort, rollback, and deletion to exact immutable or staging version coordinates.
- Regenerated the route authorization inventory twice and proved byte-identical runtime, checked JSON, and OpenAPI projections for the identifier-bearing gateway routes.

## Task Commits

Each task was committed atomically with hooks enabled:

1. **Task 1: Replace direct S3 POST fields with an authenticated chunk gateway and safe issuance ordering** - `22adae4` (feat)
2. **Task 2: Promote exact validated bytes and pin every OCR, extraction, and association consumer** - `be8e7ab` (feat)
3. **Acceptance follow-up: Prove synchronized chunk fencing and provider/repository split recovery** - `839829a` (test)

**Plan metadata:** committed with this summary and tracking update.

## Files Created/Modified

- `src/stoa/models/attachment.py` - Coordinate-free gateway intent, chunk receipt, and completion allowlists.
- `src/stoa/security/attachment_errors.py` - Stable checksum-conflict contract while preserving the closed retry-safe error registry.
- `src/stoa/db/repositories/attachment_repo.py` - Issuance transitions, fenced part claims, private receipts, assembly, immutable tuple persistence, and version-aware cleanup/reference discovery.
- `src/stoa/services/attachment_service.py` - Bounded gateway streaming, replay reconciliation, exact-version validation/promotion, immutable association/extraction/retention, and cleanup orchestration.
- `src/stoa/services/file_validation_service.py` - Seekable-stream validators that avoid a 50 MiB in-memory bytes object.
- `src/stoa/services/document_extraction_service.py` - Seekable bounded document extraction.
- `src/stoa/services/ocr_service.py` - Rekognition requests pinned to immutable object version.
- `src/stoa/routers/files.py` - Actor-owned `/intents`, `/chunks/{part_number}`, and `/complete` routes.
- `tests/test_files.py`, `tests/test_attachment_security.py`, `tests/test_questions.py` - Contract, issuance, fencing, replay, spool, overwrite, version, OCR, cleanup, and deletion adversarial controls.
- `docs/security/route-authorization-inventory.json` - Regenerated deterministic gateway route projection.

## Decisions Made

- A staging coordinate is a server-only multipart implementation detail. It is never a durable attachment coordinate and never crosses the public response boundary.
- A second writer cannot call the provider until it owns the matching checksum/length fence; a different checksum conflicts before mutation, while a matching lost response is adopted only from server-listed checksum/length evidence.
- Fresh random immutable keys plus required VersionIds are the durable identity. Raw-key matching and key-only deletion are invalid even when a newer object version has the same key and byte length.
- The 1 MiB spool may roll to bounded temporary storage, but validation, hashing, and promotion never construct a 50 MiB Python bytes object.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Approved non-production real-S3 versioning/policy evidence remains explicitly NOT RUN and is still owned by the later infrastructure/evidence gates.

## Verification

- Task 1 focused gateway/fencing/inventory filter: **39 passed, 57 deselected**.
- Task 2 focused immutable/version/spool/OCR/extraction filter: **20 passed, 75 deselected**.
- Plan-touched files/attachments/questions/conversations/inventory matrix: **130 passed**.
- Full Phase 473 validation matrix: **241 passed**.
- Full repository suite: **exit 0; 1,243 tests collected**, up from the supplied 1,232-test baseline.
- Route inventory generated twice, byte-compared with checked JSON, and `scripts/generate_route_authorization_inventory.py --check`: PASS.
- Targeted Ruff and `git diff --check`: PASS.

## Next Phase Readiness

- Plan 473-09 can map transaction cancellation indices onto stable quota, dependency, and concealed-resource outcomes using the new upload/part operations.
- Plans 473-10 and 473-11 remain pending; Phase 473 is intentionally still in progress and must not be marked complete.
- External versioned-bucket policy behavior remains honestly NOT RUN until an approved non-production environment is available.

## Self-Check: PASSED

- All three production/test commits exist and every named modified file is present.
- Every task acceptance filter, plan verification, Phase 473 matrix, deterministic inventory check, static check, and full repository run passed.
- Public APIs contain no provider coordinate contract, and source consumers/deleters use exact immutable tuples rather than key-only matching.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
