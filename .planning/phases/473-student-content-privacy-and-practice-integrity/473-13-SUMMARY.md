---
phase: 473-student-content-privacy-and-practice-integrity
plan: 13
subsystem: private-upload-gateway
tags: [privacy, idempotency, structured-errors, s3, resource-lifetime]

requires:
  - phase: 473-10
    provides: Replayable regular/SSE conversation commands and deterministic effects
  - phase: 473-12
    provides: Fenced provider recovery and exact immutable cleanup
provides:
  - Exact command-derived durable IDs for fresh conversation attachments
  - Exhaustive redacted dependency translation across the upload gateway
  - Deterministic exact-version provider-body closure on every read exit
affects: [473-14, phase-473-verification, conversation-replay, private-uploads]

tech-stack:
  added: []
  patterns:
    - Closed service-boundary translation for repository and provider failures
    - Explicit finally-owned provider response body lifetime

key-files:
  created: []
  modified:
    - src/stoa/routers/conversations.py
    - src/stoa/routers/files.py
    - src/stoa/services/attachment_service.py
    - tests/test_attachment_security.py
    - tests/test_conversations.py
    - tests/test_files.py

key-decisions:
  - "Command-derived fresh attachment IDs are immutable inputs with exact pre-effect cardinality checks; bound IDs use a separate output accumulator."
  - "Typed conditional conflicts remain concealed as upload_not_found, while dependency, malformed response, and unknown provider-success persistence outcomes use one retryable upload_service_unavailable contract."
  - "Validation and extraction bind one exact-version provider Body and close that same object in finally; close failure never replaces the stable primary outcome."

patterns-established:
  - "Gateway normalization: preserve AttachmentDecisionError, conceal resource conflicts, and erase dependency diagnostics with from None."
  - "Provider resource ownership: bind once, finish bounded reading/parsing, and close exactly once in finally."

requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]
duration: 36 min
completed: 2026-07-16
---

# Phase 473 Plan 13: Gateway and replay robustness Summary

**Conversation retries now reuse exact command-derived attachment identities, every upload gateway dependency failure projects one redacted recovery contract, and exact-version provider streams close deterministically on all exits.**

## Performance

- **Duration:** 36 min
- **Started:** 2026-07-16T20:33:00Z
- **Completed:** 2026-07-16T21:09:27Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Preserved exact command-derived fresh attachment IDs through persistence, association keys, lost-response retries, and synchronized command execution; saved reuse consumes no fresh ID and cardinality failures occur before effects.
- Centralized repository/provider translation across lookup, chunk claim and replay polling, provider reconciliation, part listing, assembly, completion persistence, validation, promotion, and recovery while preserving concealed conditional conflicts.
- Added bounded `Retry-After: 30` only to retryable upload outages; public bodies remain limited to stable code, friendly message, and server correlation ID.
- Bound validation and conversation extraction to one exact-version provider body and closed it exactly once in `finally` across success, oversize, length/checksum mismatch, validator/parser failure, provider-read failure, and close failure.
- Added route-level typed/generic dependency and malformed-provider matrices with owner, key, version, multipart, provider, and exception canary deny controls.

## Task Commits

1. **Task 1: Repair deterministic attachment identity and exhaustively normalize gateway failures** — `4b38bd9` (fix)
2. **Task 2: Close exact-version provider bodies on every exit and prove resource safety** — `7ff2288` (test)

## Files Created/Modified

- `src/stoa/routers/conversations.py` — passes exact deterministic fresh IDs into the shared regular/SSE command persistence path.
- `src/stoa/routers/files.py` — adds a bounded retry header only for the stable temporary upload outage.
- `src/stoa/services/attachment_service.py` — closed gateway translator, deterministic binding, malformed-response validation, and exact provider-body lifetime handling.
- `tests/test_attachment_security.py` — exact durable key, replay, cardinality, validation close, read failure, and close failure controls.
- `tests/test_conversations.py` — synchronized command-derived ID assertion and extraction close-on-every-exit matrix.
- `tests/test_files.py` — route-level dependency, malformed provider, redaction, Retry-After, and concealed conflict matrices.

## Verification

- Task 1 replay/gateway selector: **44 passed, 135 deselected**.
- Task 2 provider-body selector: **13 passed, 144 deselected**.
- Files/attachments/questions/conversations regression: **202 passed**.
- Full repository suite: **1,344 passed in 44.51s**.
- Targeted Ruff for all Plan 12/13 Python files: **PASS**.
- `git diff --check`: **PASS**.
- Real S3 connection-pool behavior: **NOT RUN**; no external provider or production mutation was performed.

## Decisions Made

- A false persistence result after a successful provider mutation remains a retryable unknown split outcome; typed stale/owner/version conflicts continue to use the concealed 404 contract.
- Malformed repository/provider values are dependency errors, not public diagnostics or raw 500 responses.
- Provider `close()` is best-effort cleanup: it is invoked exactly once but cannot replace validation, extraction, or stable dependency results.

## Deviations from Plan

None - plan executed exactly as written. Execution resumed and audited the valid uncommitted work left by an interrupted executor before completing the missing adversarial coverage.

## Issues Encountered

- The sandboxed full-suite process stopped when macOS process monitoring was unavailable. Re-running the identical suite with approved non-sandbox process access completed successfully with 1,344 passing tests.

## User Setup Required

None - no external service configuration required and no production/provider mutation was performed.

## Next Phase Readiness

- WR-006, WR-007, and WR-008 are closed locally with implementation and adversarial tests; CR-007 cleanup behavior remains covered by the retained Plan 12 regression.
- Plan 473-14 can now lock the remediated source SHA, run the exhaustive D-01 through D-22 and privacy evidence gates, and publish final source-bound evidence.

## Self-Check: PASSED

- Both task commits are present and all six modified files exist.
- Every task acceptance selector, plan regression, full suite, Ruff, and diff check passed.
- Public error responses remain coordinate-free and close exceptions do not alter the stable outcome.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
