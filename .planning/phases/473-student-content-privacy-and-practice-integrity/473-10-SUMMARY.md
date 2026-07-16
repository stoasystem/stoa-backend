---
phase: 473-student-content-privacy-and-practice-integrity
plan: 10
subsystem: conversation-command-privacy
tags: [dynamodb, idempotency, sha256, concurrency, ai-lease, telemetry, privacy]

requires:
  - phase: 473-09
    provides: Stable category-only attachment transaction outcomes and zero-effect cancellation mapping
provides:
  - Versioned canonical conversation request fingerprints and exact original-result replay
  - Atomic message-command, chat quota-operation, and daily-counter claims
  - Deterministic message/attachment effects with fenced expiring AI ownership
  - Allowlisted category/class/size/correlation-only telemetry across AI, title, OCR-fed question, conversation, and replay paths
affects: [473-11, 475-quota-ledger, 478-mobile-conversations]

tech-stack:
  added: []
  patterns:
    - Read-only Stage A replay and fingerprint comparison before owner attachment preflight
    - Domain-separated length-prefixed SHA-256 command identity
    - Atomic command/quota claim followed by deterministic message transaction and fenced AI completion
    - Closed private telemetry categories with no content/provider diagnostic interpolation

key-files:
  created:
    - src/stoa/security/private_telemetry.py
  modified:
    - src/stoa/security/attachment_errors.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/services/ai_service.py
    - src/stoa/routers/conversations.py
    - src/stoa/routers/questions.py
    - tests/test_attachment_security.py
    - tests/test_conversations.py
    - tests/test_questions.py

key-decisions:
  - "Conversation idempotency is a versioned domain-separated SHA-256 over exact UTF-8 content and ordered typed opaque identities; no normalization, trimming, or delimiter grammar is permitted."
  - "A message command, unique quota-operation row, and exact daily counter value are claimed in one conditional transaction; deterministic downstream IDs make later effects replay-safe."
  - "Only the active fenced AI lease owner may atomically persist the assistant message and completed public result; duplicates poll a bounded 20x50 ms and replay that result."
  - "Private-flow telemetry is one closed helper limited to event category, exception class, numeric sizes/counts, and server-owned correlation identifiers."

patterns-established:
  - "Two-stage command execution: completed replay bypasses attachment resolution, while a brand-new command performs complete zero-write owner/status/capacity preflight before claim."
  - "Private canary gate: seed independent student, OCR, extracted, model, title, exception, coordinate, and provider values and deny all of them from captured records."

requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]

duration: 21 min
completed: 2026-07-16
---

# Phase 473 Plan 10: Conversation replay convergence and private telemetry Summary

**Exact regular and SSE retries now converge through one durable command/quota claim and fenced AI result, while content and provider diagnostics are excluded from every exercised private-flow log.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-16T15:49:50Z
- **Completed:** 2026-07-16T16:10:39Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Added required bounded `idempotencyKey` validation and a process-stable `stoa.conversation.send.v1` fingerprint over exact UTF-8 content plus ordered upload/saved identities.
- Replaced eager attachment resolution with Stage A command lookup/replay before Stage B owner/status/capacity preflight, so completed retries survive consumed fresh uploads and mismatches fail before lookup.
- Added an atomic command/quota-operation/daily-counter claim, deterministic student/assistant/fresh-attachment IDs, message-command transaction fencing, idempotent usage recording, and expiring AI lease takeover/terminal state.
- Unified regular and streaming execution around the same stored safe result and proved synchronized duplicates produce one bind, usage, extraction, AI, and completion effect.
- Replaced AI, title, conversation, replay, and OCR-fed question diagnostics with one allowlisted telemetry helper and cross-service private-canary tests.

## Task Commits

Each task was committed atomically with hooks enabled:

1. **Task 1: Implement the durable conversation command and exact replay state machine** - `376116b` (feat)
2. **Task 2: Replace AI, conversation, title, OCR-fed, and provider logs with private-safe telemetry** - `0c2535c` (fix)
3. **Acceptance follow-up: Prove synchronized duplicate convergence and AI lease fencing** - `4c92b52` (test)

**Plan metadata:** committed with this summary and tracking update.

## Files Created/Modified

- `src/stoa/db/repositories/attachment_repo.py` - Message command keys, atomic quota claim, command-aware message transaction, lease renewal/takeover, fenced completion, and terminal transition.
- `src/stoa/routers/conversations.py` - Canonical fingerprint, Stage A/Stage B shared executor, deterministic effects, replay polling, regular/SSE convergence, and safe telemetry calls.
- `src/stoa/services/attachment_service.py` - Command-aware deterministic binding and replay-safe authorized summary projection.
- `src/stoa/security/attachment_errors.py` - Stable idempotency-conflict and bounded in-progress response contracts.
- `src/stoa/security/private_telemetry.py` - Closed category/class/size/count/correlation telemetry helper.
- `src/stoa/services/ai_service.py` - Content-free injection, parse, policy, request, response, and hint telemetry.
- `src/stoa/routers/questions.py` - OCR-fed and AI question failure telemetry using server correlation only.
- `tests/test_conversations.py`, `tests/test_attachment_security.py`, `tests/test_questions.py` - Fingerprint, replay, zero-effect, synchronized duplicate, lease, bounded polling, and private-canary controls.

## Decisions Made

- A completed command stores the exact safe public result for regular/SSE re-projection; request fingerprint state stores no raw request content or attachment coordinates.
- A claim loser only re-reads and boundedly waits for the winner; a later retry of a command lost before message commit may safely resume with deterministic IDs.
- A retry lost after message commit reconstructs attachment context from the committed message's server-owned durable attachment IDs, never from the consumed upload identity.
- The 120-second AI lease permits an initial owner plus at most two fenced takeover attempts; active owners may renew, stale owners cannot renew or complete, and exhaustion becomes terminal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added safe telemetry at the OCR-fed question orchestration boundary**
- **Found during:** Task 2 private-canary acceptance gate
- **Issue:** The task's named file list omitted `src/stoa/routers/questions.py`, but the required OCR-to-AI and question-answer failure paths could not emit actionable safe categories without changing that orchestrator.
- **Fix:** Added only category/class/count/correlation telemetry around OCR and AI failures; response and persistence behavior is unchanged.
- **Files modified:** `src/stoa/routers/questions.py`, `tests/test_questions.py`
- **Verification:** Telemetry/canary filter: 20 passed; plan matrix: 200 passed; full suite: 1303 passed.
- **Committed in:** `0c2535c`

---

**Total deviations:** 1 auto-fixed (1 missing critical). **Impact:** Closed the explicitly required cross-service telemetry boundary without broadening question behavior or external effects.

## Issues Encountered

- The initial concurrency control test used a shorter synthetic wait than the winning thread required; the test clock was corrected while preserving the production 20x50 ms bound. No production behavior changed.

## User Setup Required

None - no external service configuration required. Provider crash-after-acceptance exactly-once semantics and deployed log capture remain external limitations for the final evidence gate; no production/provider mutation was performed.

## Verification

- Task 1 focused idempotency/replay/zero-effect filter: **8 passed** before the explicit concurrency follow-up.
- Task 2 telemetry/private-canary filter: **20 passed, 132 deselected**.
- Explicit idempotency/concurrency/lease/polling filter: **15 passed, 117 deselected**.
- Conversation and attachment task gate: **132 passed**.
- Plan-level files/question/conversation/practice gate: **200 passed**.
- Full Phase 473 privacy/practice/authorization matrix: **301 passed**.
- Full repository suite: **1303 passed** (supplied baseline 1277; +26 Plan 10 controls).
- Targeted Ruff and `git diff --check`: PASS.
- Unsafe logging scan across AI, conversation, question, OCR, and attachment sources: PASS.

## Next Phase Readiness

- Plan 473-11 can bind the implementation and checked inventory to one clean source SHA, rerun retained Phase 472/473 gates, and regenerate final evidence.
- Phase 473 remains intentionally open at 10/11 plans; real provider/versioned-storage, deployed cleanup schedule/IaC, and deployed log capture remain honestly NOT RUN until approved external evidence exists.

## Self-Check: PASSED

- All ten named created/modified files exist and all three Plan 10 commits are present.
- Every task acceptance filter, plan verification, Phase 473 matrix, Ruff/diff gate, unsafe-log scan, and full repository suite passed.
- Command replay, atomic quota claim, deterministic effects, synchronized duplicate convergence, lease fencing/takeover/terminal state, and private-canary telemetry each have direct executable controls.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
