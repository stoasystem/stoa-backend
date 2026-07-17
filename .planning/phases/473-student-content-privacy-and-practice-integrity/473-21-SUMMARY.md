---
phase: 473-student-content-privacy-and-practice-integrity
plan: 21
subsystem: conversation-integrity
tags: [dynamodb-consistent-read, replay, immutable-attachments, ai-lease, bedrock]

# Dependency graph
requires:
  - phase: 473-20
    provides: Typed durable conversation commands and deterministic message identities
  - phase: 473-24
    provides: Bounded semantic document parsing and closed extraction categories
provides:
  - Exact complete attachment and anchored history replay snapshots
  - Typed all-or-nothing attachment extraction outcomes
  - Deadline-bounded AI invocation with lease-generation completion fencing
  - Equivalent fail-closed behavior for regular and SSE message transports
affects: [473-35, 473-verification, conversation-api]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Consistent exhaustive reads with exact-set validation
    - Fingerprinted immutable history snapshots
    - Typed context disposition at provider/parser boundaries
    - Lease-generation conditional completion

key-files:
  created:
    - tests/test_phase473_conversation_replay.py
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/routers/conversations.py
    - src/stoa/services/attachment_service.py
    - src/stoa/services/ai_service.py
    - tests/test_conversations.py
    - tests/test_attachment_security.py
    - tests/test_learning_expansion.py
    - tests/test_phase473_document_boundary.py
    - tests/test_phase473_message_command.py

key-decisions:
  - "Persist exact ordered history message IDs plus a canonical fingerprint; ignore later messages and retry when any anchored row is missing or changed."
  - "Accept replay attachments only as a complete ordered set of owner-bound active attachment.v1 rows with exact immutable coordinates, checksums, lengths, and source fingerprints."
  - "Cap AI invocation at 90 seconds, close every provider body, renew the lease after invocation, and condition completion on the same lease attempt and unexpired generation."

patterns-established:
  - "Replay snapshot: commands carry deterministic attachment identities and an ordered, fingerprinted history anchor used by fresh and resumed execution."
  - "Closed extraction: READY, RETRYABLE, and INVALID are data-bearing dispositions; prompt marker strings are forbidden."
  - "Stale-worker fence: model output is accepted only after lease renewal and a conditional completion transaction validates owner, attempt, and expiry."

requirements-completed: [V9PRIV-02]

# Metrics
duration: 22min
completed: 2026-07-17
---

# Phase 473 Plan 21: Exact Conversation Replay and Bounded AI Execution Summary

**Consistent exact-set attachment reads, fingerprinted anchored history, typed extraction, and lease-fenced Bedrock execution now make fresh and resumed conversation sends reproduce the same private context.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-07-17T19:40:25Z
- **Completed:** 2026-07-17T20:01:58Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added a 440-line lower-boundary replay/fault matrix covering DynamoDB pagination and BatchGet faults, malformed immutable attachment rows, S3 and parser failures, AI timeouts, lease takeover, conditional completion, and regular/SSE parity.
- Replaced partial or moving replay inputs with consistent, paginated, bounded loaders that validate exact ordered attachments and the persisted history message identities and fingerprint.
- Replaced prompt-marker recovery and generic successful fallbacks with typed closed extraction results; incomplete private context invokes no AI and freezes no assistant result.
- Bounded AI SDK retries and timeouts below the 120-second lease, closed response bodies deterministically, renewed the lease after invocation, and rejected stale completion attempts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing complete-replay and lease fault tests** - `08492ca` (test)
2. **Task 2: Load complete exact attachments and anchored history** - `1e1f41b` (feat)
3. **Task 3: Make extraction and AI execution typed, bounded, and fenced** - `7b48467` (fix)
4. **Regression compatibility: Align inherited contract fixtures** - `f6279c8` (test)

## Files Created/Modified

- `tests/test_phase473_conversation_replay.py` - Exact replay, provider-body, parser, AI deadline, lease, takeover, and transport fault matrix.
- `src/stoa/db/repositories/attachment_repo.py` - Consistent bounded BatchGet validation and lease-attempt/expiry completion conditions.
- `src/stoa/routers/conversations.py` - Anchored history snapshots, exact replay validation, typed extraction routing, retry outcomes, lease renewal, and regular/SSE shared execution.
- `src/stoa/services/attachment_service.py` - Exact immutable-record checks and READY/RETRYABLE/INVALID all-or-nothing extraction.
- `src/stoa/services/ai_service.py` - Deadline-aware Bedrock invocation, bounded SDK retries/timeouts, strict response validation, and deterministic body cleanup.
- `tests/test_conversations.py` - Fresh/replay command fixtures and fail-closed conversation coverage.
- `tests/test_attachment_security.py` - Typed extraction and provider cleanup expectations.
- `tests/test_learning_expansion.py` - Closable Bedrock response-body fixture.
- `tests/test_phase473_document_boundary.py` - Typed retryable immutable-byte mismatch contract.
- `tests/test_phase473_message_command.py` - Exact BatchGet coordinates and deterministic durable replay identity fixtures.

## Decisions Made

- Persist and validate a canonical history fingerprint in addition to the exact ordered message IDs. IDs prevent moving-window drift; the fingerprint detects changed content under an existing identity.
- Treat extra, duplicate, missing, foreign, inactive, or structurally malformed attachment rows as closed conflicts, while incomplete provider reads remain retryable without exposing coordinates.
- Use a 90-second application deadline under the 120-second AI lease, configure one SDK attempt, then renew and conditionally complete using the same lease owner and attempt. This prevents an old worker from committing after takeover.
- Require provider response bodies to be closable. Cleanup failure is retryable when no stronger deterministic document failure already exists.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Implemented shared Task 3 safeguards during Task 2 GREEN**
- **Found during:** Task 2 (Load complete exact attachments and anchored history)
- **Issue:** The prescribed Task 2 command contains two `-k` options. Pytest applies the last expression to the entire invocation, and the replay test filename itself matches `replay`, selecting shared Task 3 cases before Task 3 begins.
- **Fix:** Implemented the shared typed extraction and lease-fencing production prerequisites needed by the mandatory Task 2 gate, while retaining Task 3-specific transport hardening for its own commit.
- **Files modified:** `src/stoa/routers/conversations.py`, `src/stoa/services/attachment_service.py`, `src/stoa/services/ai_service.py`
- **Verification:** Prescribed Task 2 gate passed with 48 tests.
- **Committed in:** `1e1f41b`

**2. [Rule 1 - Bug] Updated inherited fixtures for the stricter closed contracts**
- **Found during:** Task 3 repository-wide verification
- **Issue:** Five inherited tests still supplied non-closable AI bodies, expected private marker strings, omitted exact BatchGet keys, or constructed replay commands without deterministic v2 snapshot fields.
- **Fix:** Made the fixtures represent real provider and persisted record shapes, and asserted the typed retryable result instead of a prompt marker.
- **Files modified:** `tests/test_learning_expansion.py`, `tests/test_phase473_document_boundary.py`, `tests/test_phase473_message_command.py`
- **Verification:** The five regressions pass and the full repository suite passes with 1,718 tests.
- **Committed in:** `f6279c8`

---

**Total deviations:** 2 auto-fixed (1 blocking issue, 1 compatibility bug)
**Impact on plan:** Both changes were required to exercise the specified exact, typed, fail-closed contracts. No product scope was added.

## Issues Encountered

- Context7 was unavailable in the environment. Version-specific Botocore configuration semantics were checked against the official Botocore documentation before setting `connect_timeout`, `read_timeout`, and `retries.total_max_attempts`.

## Known Stubs

None. Empty values in the touched production paths are bounded initial state or the intentional no-context payload of a typed RETRYABLE/INVALID extraction result; none flow to a successful assistant response.

## Verification

- Prescribed Task 2 gate: 48 passed, 37 deselected.
- Prescribed Task 3 gate: 46 passed, 259 deselected.
- Complete affected conversation/attachment suites: 305 passed.
- Full repository suite: 1,718 passed.
- Ruff on all touched production and test files: passed.
- Diff whitespace and forbidden prompt-marker/fallback scans: passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Exact replay and bounded AI execution are ready for Phase 473 verification and downstream privacy/integrity plans.
- No blockers remain.

## Self-Check: PASSED

All declared key files exist and commits `08492ca`, `1e1f41b`, `7b48467`, and `f6279c8` are present in repository history.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
