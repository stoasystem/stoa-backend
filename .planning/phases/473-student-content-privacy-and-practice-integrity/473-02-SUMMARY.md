---
phase: 473-student-content-privacy-and-practice-integrity
plan: 02
subsystem: upload-security
tags: [s3, dynamodb, pillow, pypdf, validation, quota, privacy]

requires:
  - phase: 473-01
    provides: Opaque attachment contracts, safe errors, and authoritative tier storage limits
provides:
  - Owner-bound 30-minute upload intents with constrained presigned POST policies
  - Bounded JPEG/PNG/PDF/OOXML/text structural validation
  - Conditional upload lifecycle and atomic quota/association transaction primitives
  - Authoritative HEAD/read finalize flow with provider-redacted recovery
affects: [473-03, 473-04, 473-07, 478-mobile]

tech-stack:
  added: [Pillow, pypdf]
  patterns:
    - Opaque owner records separate public upload IDs from private object coordinates
    - Conditional status/version/expiry transitions precede every validation mutation
    - Provider metadata and bytes are bounded and validated before durable state

key-files:
  created:
    - src/stoa/services/file_validation_service.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
  modified:
    - src/stoa/routers/files.py
    - src/stoa/security/authorization.py
    - src/stoa/security/route_inventory.py
    - tests/test_files.py
    - tests/test_attachment_security.py

key-decisions:
  - "Upload ownership is established only by the verified student Actor and a private intent record; client fields never establish owner or storage coordinates."
  - "Only a conditional pending_upload-to-validating transition may read storage, and only verified immutable bytes may transition to validated."
  - "First durable attachment transactions charge exact content length once; saved attachment reuse contains no storage usage mutation."

patterns-established:
  - "Validation failures carry only a stable AttachmentErrorCode category, never filenames, bytes, keys, or parser/provider diagnostics."
  - "Missing and foreign opaque upload IDs are concealed before S3 access and share one public projection."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 12 min
completed: 2026-07-16
---

# Phase 473 Plan 02: Upload intent, validation, quota and lifecycle core Summary

**Owner-bound constrained POST intents now cross authoritative S3 metadata, bounded byte validation, and conditional DynamoDB lifecycle/quota boundaries without exposing private storage coordinates.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-16T10:22:15Z
- **Completed:** 2026-07-16T10:33:57Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments

- Locked JPEG/PNG/PDF/DOCX/PPTX/XLSX/TXT/MD validation with byte, MIME, magic, dimension, page, archive, compression, path, encryption, and UTF-8 controls.
- Added private upload/attachment/storage record keys, versioned owner/status/expiry transitions, and atomic first-charge versus zero-charge reuse transaction builders.
- Replaced key-returning presigned PUT with student-only opaque presigned POST intents and a finalize route that performs owner concealment, HEAD, bounded read, immutable-byte checks, and terminal/retry-safe transitions.
- Extended executable route inventory with an explicit upload resource type and regenerated checked authorization evidence.

## Task Commits

1. **Task 1: Implement bounded byte, image and OOXML validators** - `1ac9ee6` (feat)
2. **Task 2: Implement upload-intent repository, state machine and quota primitives** - `cf70387` (feat)
3. **Task 3: Migrate file routes to constrained POST and authoritative finalize** - `35e0316` (feat)
4. **Correctness follow-up: Serialize attachment transactions for low-level DynamoDB clients** - `fcfcc49` (fix)

## Files Created/Modified

- `src/stoa/services/file_validation_service.py` - Pure bounded structural validators and category-only failures.
- `src/stoa/db/repositories/attachment_repo.py` - Conditional lifecycle operations and atomic quota/association transaction builders.
- `src/stoa/services/attachment_service.py` - Student ownership, intent issuance, finalize orchestration, and entitlement storage limits.
- `src/stoa/routers/files.py` - Opaque presigned POST and finalize HTTP contracts with server correlation.
- `src/stoa/security/authorization.py`, `src/stoa/security/route_inventory.py` - Executable upload resource inventory.
- `tests/test_files.py`, `tests/test_attachment_security.py` - Supported/adversarial byte, owner, policy, finalize, quota, and redaction coverage.
- `pyproject.toml`, `uv.lock`, `requirements.txt` - Locked Pillow and pypdf runtime dependencies.
- `docs/security/route-authorization-inventory.json` - Regenerated source-bound route projection.

## Decisions Made

- A presigned POST policy and its stored intent use the same server-generated key, exact declared type, maximum byte range, and 1800-second expiry.
- Finalize never trusts request metadata: S3 HEAD length/type/ETag and a bounded object read are authoritative.
- Temporary provider failures release `validating` only within the original expiry; file failures are terminal `invalid`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added upload resource authorization inventory vocabulary**
- **Found during:** Task 3 route inventory gate
- **Issue:** The Phase 472 closed inventory did not yet recognize `uploadId`, so the new identifier route could not be represented as an executable Actor-owned operation.
- **Fix:** Added `ResourceType.UPLOAD`, exact `uploadId` compatibility, and an executable finalize dependency specification; regenerated checked JSON.
- **Files modified:** `src/stoa/security/authorization.py`, `src/stoa/security/route_inventory.py`, `src/stoa/routers/files.py`, `docs/security/route-authorization-inventory.json`
- **Verification:** `tests/test_route_authorization_inventory.py`: 27 passed.
- **Committed in:** `35e0316`

**2. [Rule 1 - Bug] Serialized low-level DynamoDB transaction inputs**
- **Found during:** Plan acceptance review after Task 3
- **Issue:** High-level fake transactions were compatible, but production `table.meta.client` requires DynamoDB AttributeValue serialization.
- **Fix:** Added TypeSerializer projection for Put, Update, ConditionCheck, keys, items, names, and condition values.
- **Files modified:** `src/stoa/db/repositories/attachment_repo.py`
- **Verification:** Focused repository/transaction tests and the full suite pass.
- **Committed in:** `fcfcc49`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug). **Impact:** Both fixes preserve the locked authorization and production transaction boundaries without scope expansion.

## Issues Encountered

- Sandboxed `uv` cache access and git index writes required the existing approved escalation path; dependency resolution and all hooks completed normally without bypass.

## User Setup Required

None - no external service configuration required.

## Verification

- Plan files/attachment, dependency-hash, and route-inventory matrix: **70 passed**.
- Full backend suite: **1163 passed** (prior baseline 1143; no regression).
- Ruff on all changed Python files: PASS.
- `git diff --check`: PASS.
- No ambient AWS or network access was used by tests.

## Next Phase Readiness

- Plans 473-03 and 473-04 can consume only validated owner intents and reuse atomic first-charge/reuse transaction primitives.
- Cleanup remains Plan 473-07; invalid and expired records are already unusable synchronously.

## Self-Check: PASSED

- All three created key files exist.
- All four implementation commits are present.
- Every task verification, plan-level verification, route inventory gate, dependency hash test, and full regression suite passes.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
