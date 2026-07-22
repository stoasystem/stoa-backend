---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 14
subsystem: api
tags: [fastapi, pydantic, idempotency, validation, question-submission]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 02
    provides: atomic question route admission and durable replay projection
provides:
  - required bounded caller-owned question submission identity
  - redacted effect-free validation for missing, malformed, and unexpected request input
  - byte-identical valid caller key forwarding without UUID-derived fallback
affects: [475-15-question-identity-privacy, 475-19-question-replay-integrity, V9DATA-01]

tech-stack:
  added: []
  patterns: [route-local redacted validation, required caller-owned replay identity, validation-before-effects]

key-files:
  created: []
  modified:
    - src/stoa/models/question.py
    - src/stoa/routers/questions.py
    - tests/test_phase475_question_replay.py
    - tests/test_questions.py

key-decisions:
  - "Question submission accepts only a required 8..200-character nonblank idempotencyKey and preserves every valid caller byte; no UUID-derived fallback remains."
  - "The POST /questions route alone redacts request-validation details into a fixed code/message/correlationId response so malformed content cannot be echoed."

patterns-established:
  - "Submission validation: Pydantic establishes the required alias and bounds before the endpoint body, while a route-local APIRoute projects only safe validation metadata."

requirements-completed: [V9DATA-01]

duration: 9 min
completed: 2026-07-22
---

# Phase 475 Plan 14: Required Question Submission Identity Summary

**Question POSTs now require a caller-retained replay identity, reject malformed identity input before every application effect, and never derive the logical operation from a fresh server UUID.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-22T07:17:19Z
- **Completed:** 2026-07-22T07:26:16Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Made JSON `idempotencyKey` the only accepted, required public alias with the existing 8..200 bound plus explicit whitespace-only rejection.
- Removed the `question_id`/UUID fallback and forward valid caller keys byte-for-byte into command replay and admission.
- Added a submission-specific redacted 422 envelope containing only a stable code, safe message, and server-owned correlation ID.
- Added public-boundary proof that missing, null, blank, short, long, and extra input performs zero profile, UUID, command, attachment, admission, ledger, question, OCR, or AI work.
- Preserved all inherited OCR, attachment, quota, pending, and failure-path tests under the required-key contract.

## Task Commits

Each TDD gate and directly affected regression update was committed atomically:

1. **RED: Add failing question identity contract tests** - `d24c332` (test)
2. **GREEN: Require durable question submission identity** - `9512f58` (feat)
3. **Regression: Align inherited question request fixtures** - `2b934b8` (test)

## Files Created/Modified

- `src/stoa/models/question.py` - Required nonblank aliased idempotency field and closed invalid-identity error code.
- `src/stoa/routers/questions.py` - Byte-preserving identity use, removed UUID fallback, and route-local redacted validation response.
- `tests/test_phase475_question_replay.py` - Effect-free invalid-input matrix and exact-key forwarding proof.
- `tests/test_questions.py` - Existing question submission scenarios updated with stable caller-owned keys.

## Decisions Made

- Preserved leading and trailing bytes on otherwise valid keys. Blank detection uses a non-mutating whitespace check; normalization must not change the caller's durable identity.
- Scoped the custom validation projection to `POST /questions`, avoiding a behavior change for unrelated question routes while preventing FastAPI/Pydantic validation details from echoing untrusted input.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated inherited question request fixtures for the required identity contract**
- **Found during:** Task 1 expanded question-route regression
- **Issue:** Seven existing OCR, attachment, quota, and failure-path tests still submitted requests under the removed optional-key contract and therefore stopped at the new 422 boundary.
- **Fix:** Added distinct stable caller-owned `idempotencyKey` values to those existing request fixtures without changing their product assertions.
- **Files modified:** `tests/test_questions.py`
- **Verification:** `tests/test_phase475_question_replay.py` plus `tests/test_questions.py` passes 35 tests; targeted Ruff passes.
- **Committed in:** `2b934b8`

---

**Total deviations:** 1 auto-fixed (1 missing critical regression update).
**Impact on plan:** The additional test-only change preserves directly affected route coverage and adds no product scope.

## Issues Encountered

- The first route-local wrapper composition used an empty nested router, which FastAPI rejects. Registering the same endpoint with `route_class_override` preserved the exact `/questions` path and OpenAPI model while scoping validation redaction correctly.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_question_replay.py -k 'idempotency or lost_response or missing'` - 8 passed.
- `.venv/bin/ruff check src/stoa/models/question.py src/stoa/routers/questions.py tests/test_phase475_question_replay.py` - passed.
- `.venv/bin/python -m pytest -q tests/test_phase475_question_replay.py tests/test_questions.py` - 35 passed.
- `.venv/bin/python -m pytest -q tests/test_route_authorization_inventory.py` - 29 passed.
- Expanded Ruff over all four modified files - passed.
- Source inspection confirms `body.idempotency_key` is assigned before `question_id`, with no `build_question_idempotency_key` call in `submit_question`.

## User Setup Required

None - no dependency, credential, service, or deployment changes are required.

## Known Stubs

None.

## Next Phase Readiness

- Ready for Plan 475-15 to replace the raw caller key at durable repository coordinates with its opaque privacy-safe identity.
- Plans 475-17 through 475-20 can rely on every accepted question command having a reproducible caller identity.

## Self-Check: PASSED

- All four modified source/test files exist.
- Commits `d24c332`, `9512f58`, and `2b934b8` exist in repository history with no tracked deletions.
- Every acceptance criterion, plan verification command, affected question regression, route authorization inventory, Ruff gate, and diff check passes.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
