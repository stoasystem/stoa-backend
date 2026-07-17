---
phase: 473-student-content-privacy-and-practice-integrity
plan: 24
subsystem: document-security
tags: [ooxml, opc, pdf, xml-expat, multiprocessing, parser-isolation]

requires:
  - phase: 473-19
    provides: Exact provider absence and cleanup convergence for immutable attachments
provides:
  - Semantic passive OPC admission shared by validation and extraction
  - Event-driven DTD, entity, external relationship, and active-content refusal
  - Spawn-isolated extraction with bounded input, output, CPU, memory, and wall time
  - Exact immutable tuple and detected-type revalidation before AI context production
affects: [473-21, 473-35, 479-provider-integration, 480-deployed-observability]

tech-stack:
  added: []
  patterns: [semantic package proof, closed XML event parsing, spawn-isolated parser, exact immutable revalidation]

key-files:
  created:
    - src/stoa/services/document_parser_worker.py
    - tests/test_phase473_document_boundary.py
  modified:
    - src/stoa/services/file_validation_service.py
    - src/stoa/services/document_extraction_service.py
    - src/stoa/services/attachment_service.py
    - tests/test_attachment_security.py
    - tests/test_conversations.py

key-decisions:
  - "OOXML identity is established by one canonical member graph, exact content-type override, and exact office-document relationship; extension and MIME only select the expected contract."
  - "All relationship and content-type XML crosses an Expat event boundary that rejects DTD/entity declarations and resolves internal targets relative to their source part while refusing external or escaping targets."
  - "Document text is produced only in a spawn worker with closed typed IPC, CPU/memory/wall fences, and parent-owned termination; Darwin uses a resident-set watchdog when RLIMIT_AS is unavailable."
  - "Extraction rechecks the exact key/version request, response ETag and length, SHA-256, filename/detected MIME, and semantic package facts before returning bounded text."

patterns-established:
  - "Semantic package proof: canonical Unicode/case identities and one exact OPC graph precede all document use."
  - "Closed parser boundary: child diagnostics and tracebacks are discarded; callers receive only bounded text or an allowlisted category."

requirements-completed: [V9PRIV-01, V9PRIV-02]

duration: 24 min
completed: 2026-07-17
---

# Phase 473 Plan 24: Semantic document validation and parser resource isolation Summary

**Supported PDF, DOCX, PPTX, XLSX, TXT, and MD attachments now cross semantic type proof and a resource-isolated parser before any bounded text can enter student AI context.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-17T18:32:36Z
- **Completed:** 2026-07-17T18:56:39Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Replaced extension/root heuristics with exact OPC content-type, package relationship, main-part, canonical-member, compression, CRC, and passive-content validation.
- Made external relationships and DTD/entity content fail through decoded XML parser events across UTF-8/UTF-16, namespace, quoting, whitespace, case, and character-reference variants.
- Added spawn-isolated parsing with pre-read input bounds, bounded IPC, decoded output/page/slide/sheet/cell limits, CPU/address-space limits, a Darwin resident-set fallback, wall deadlines, and forced cleanup.
- Revalidated exact immutable response ETag/length, SHA-256, filename/MIME, and semantic document facts before extraction; provider bodies close on every exit.
- Preserved JPEG/PNG-only OCR support and existing 10 MiB image/50 MiB document quotas without adding a dependency.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing semantic-container and parser-budget tests** - `62de2be` (test, RED: 32 failed and 10 passed; pytest exit 1)
2. **Task 2: Implement one semantic passive OPC and PDF admission contract** - `b94e851` (feat, GREEN)
3. **Task 3: Isolate bounded extraction and reassert immutable admission facts** - `41e5065` (feat, GREEN)

## Files Created/Modified

- `src/stoa/services/document_parser_worker.py` - Spawn worker, resource fences, bounded IPC, typed results, timeout termination, and Darwin memory watchdog.
- `src/stoa/services/file_validation_service.py` - Canonical OPC graph, safe XML event parser, relationship resolution, archive/CRC limits, and stable admission mapping.
- `src/stoa/services/document_extraction_service.py` - Shared semantic revalidation and safe XML member parsing before allowlisted extraction.
- `src/stoa/services/attachment_service.py` - Exact immutable response/byte/type revalidation and isolated parser integration with deterministic body closure.
- `tests/test_phase473_document_boundary.py` - Hostile OOXML/PDF/XML/archive/resource/worker and immutable-tuple matrix.
- `tests/test_attachment_security.py` - Semantically valid inherited document fixtures and exact immutable response metadata.
- `tests/test_conversations.py` - Isolated parser and exact response-metadata integration expectations.

## Decisions Made

- OPC relationships are resolved relative to the owning source part, so valid internal `../` targets remain supported while package-root escapes, absolute paths, URI schemes, and external target modes fail closed.
- Macro-enabled content types, VBA, ActiveX, OLE, embeddings, external links, macro sheets, hybrid roots, encrypted members, unsupported compression, and Unicode/case collisions share category-only rejection semantics.
- Unsupported resource-limit setup does not silently run unbounded. Linux/Unix uses `RLIMIT_CPU` and `RLIMIT_AS`; Darwin retains the CPU limit and installs an equivalent resident-set watchdog because its kernel rejects `RLIMIT_AS` changes.
- Worker stdout, stderr, exception text, tracebacks, paths, provider details, and document content never cross IPC.

## Verification

- RED gate: **32 failed, 10 passed** and the exact wrapper confirmed pytest exit status **1** before implementation.
- Task 2 semantic admission/extraction gate: **62 passed, 202 deselected** after all implementation existed.
- Task 3 worker/resource/immutable gate: **66 passed, 198 deselected**.
- Complete hostile document, inherited attachment-security, and conversation suites: **309 passed**.
- Repository-wide suite: **1676 passed, 2 failed**; both failures are unrelated Plan 473-26 tests whose fixed `2026-07-17T16:00:00Z` assignment expired against the real route clock. Recorded in `deferred-items.md`; no authorization code was changed.
- Targeted Ruff: **passed**.
- `git diff --check`: **passed**.
- Parser-process leak check: **passed** (no `stoa-document-parser` process remained).
- Fixed-string production-source privacy canary denial: **passed**.
- Real provider body/pool behavior: **NOT RUN** (Phase 479).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the RED CRC fixture to mutate stored CRC fields**
- **Found during:** Task 2 (semantic passive admission)
- **Issue:** The original byte flip altered a deflate payload without deterministically producing a CRC mismatch, so the named CRC case could remain readable.
- **Fix:** Corrupted both local and central-directory CRC fields for the first member.
- **Files modified:** `tests/test_phase473_document_boundary.py`
- **Verification:** The CRC case deterministically returns `upload_invalid` and the semantic gate passes.
- **Committed in:** `b94e851`

**2. [Rule 3 - Blocking] Added a Darwin memory-limit fallback**
- **Found during:** Task 3 (isolated parser worker)
- **Issue:** macOS reports `RLIMIT_AS` but rejects setting it, which correctly closed the worker as unavailable and blocked successful bounded parsing.
- **Fix:** Retained `RLIMIT_CPU` and added a child resident-set watchdog on Darwin; other unsupported platforms still fail closed.
- **Files modified:** `src/stoa/services/document_parser_worker.py`, `tests/test_phase473_document_boundary.py`
- **Verification:** Spawn parsing, configured resource fences, decoded limits, timeout termination, and no-orphan tests pass.
- **Committed in:** `41e5065`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking platform issue)
**Impact on plan:** Both fixes were necessary to make the named CRC and cross-platform resource contracts deterministic; neither broadened supported formats or exposed parser diagnostics.

## Issues Encountered

- The full repository suite exposed two out-of-scope Plan 473-26 clock-dependent failures after a hard-coded one-hour assignment expired during the day. Focused Plan 473-24 gates and all touched integration suites pass; remediation is recorded in `deferred-items.md`.

## User Setup Required

None - no external service configuration or new dependency is required.

## Known Stubs

None.

## Next Phase Readiness

- Plan 473-21 can consume one closed text-or-category parser result without invoking AI on incomplete context.
- Real provider body/pool behavior remains explicitly unclaimed for Phase 479.
- The unrelated Plan 473-26 fixed-clock test should be repaired before the phase-wide full-suite evidence gate.

## Self-Check: PASSED

- All created and modified key files exist.
- Task commits `62de2be`, `b94e851`, and `41e5065` exist in repository history in RED/GREEN/GREEN order.
- Every Plan 473-24 acceptance gate, targeted static check, privacy denial, and process-lifecycle check passes.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
