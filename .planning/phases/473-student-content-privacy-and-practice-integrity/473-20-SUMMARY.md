---
phase: 473-student-content-privacy-and-practice-integrity
plan: 20
subsystem: conversation-integrity
tags: [dynamodb-transactions, idempotency, quota, usage-ledger, sse]

requires:
  - phase: 473-19
    provides: Exact attachment cleanup convergence and immutable attachment lifecycle
provides:
  - Closed typed message-command state machine for claim, resume, rejection, retry, lease, completion, terminal, expiry, and absence
  - Atomic message, attachment, quota, and usage-ledger identity with idempotent compensation
  - One durable executor and result projection shared by regular and SSE message transports
  - Rejected legacy initialMessage conversation-creation bypass
affects: [473-21, 473-verification, conversation-api, usage-ledger]

tech-stack:
  added: []
  patterns: [typed durable disposition, transaction-bound usage, state-aware polling, compensating rejection]

key-files:
  created:
    - tests/test_phase473_message_command.py
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/routers/conversations.py
    - src/stoa/security/attachment_errors.py
    - tests/test_conversations.py
    - tests/test_attachment_security.py

key-decisions:
  - "The first message-command claim persists the exact quota period, counter result, usage identity, request fingerprint, attachment order, message IDs, and history anchor; all retries reuse those facts across midnight."
  - "The usage-ledger event is written in the same durable bind transaction as message and attachment effects; deterministic pre-bind rejection conditionally compensates only that command's quota operation."
  - "Regular and SSE transports exhaustively project the same validated command schema and only a live claimed or leased command may return message_in_progress."

patterns-established:
  - "Typed command boundary: repository transitions return named dispositions rather than bools, tuples, or raw transaction exceptions."
  - "Durable response projection: completed and rejected responses come from validated persisted state, while ambiguous dependencies remain retryable."

requirements-completed: [V9PRIV-02]

duration: 38 min
completed: 2026-07-17
---

# Phase 473 Plan 20: Typed conversation command and durable usage lifecycle Summary

**Conversation sends now converge through a typed DynamoDB command whose message, attachment, quota, and usage effects share one durable identity across retries, contention, lost responses, and midnight rollover.**

## Performance

- **Duration:** 38 min
- **Started:** 2026-07-17T16:55:52Z
- **Completed:** 2026-07-17T17:34:01Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added a lower-boundary command suite covering claim contention, true quota exhaustion, transactional usage identity, deterministic compensation, completion ambiguity, state-aware polling, cross-midnight replay, safe transport faults, and regular/SSE rejection parity.
- Replaced boolean command transitions with closed typed dispositions and made claim/bind/completion/rejection preserve exact durable identity and safe retry semantics.
- Moved the usage-ledger event into the message bind transaction and added an exactly-once conditional compensation transaction for deterministic pre-bind rejection.
- Unified regular and SSE sends on one durable executor, removed the post-effect usage call and legacy send implementation, and rejected `initialMessage` at conversation creation.
- Added bounded retries for DynamoDB `UnprocessedKeys` so a resume never treats a partial attachment read as authoritative.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the failing message-command state and transport matrix** - `86fd149` (test)
2. **Task 2: Implement typed command transitions and transactional usage identity** - `5e4b9b6` (feat)
3. **Task 3: Drive regular and SSE responses from durable command state only** - `00b6a94` (fix)
4. **Task 3 deviation: Close partial batch-read ambiguity** - `cc17e8b` (fix)

## Files Created/Modified

- `tests/test_phase473_message_command.py` - Repository-client fault matrix, durable-state classifier tests, transport parity, midnight replay, and bypass regression.
- `src/stoa/db/repositories/attachment_repo.py` - Typed command results, atomic usage operation, compensation, completion reconciliation, and bounded batch rereads.
- `src/stoa/routers/conversations.py` - Exhaustive durable-state executor and shared regular/SSE projection without legacy/post-effect paths.
- `src/stoa/security/attachment_errors.py` - Closed safe public contracts for daily limit, terminal failure, expired command, and missing command.
- `tests/test_conversations.py` - Inherited conversation scenarios aligned with typed command state and the unified executor.
- `tests/test_attachment_security.py` - AI lease and terminal transition assertions aligned with typed repository dispositions.

## Decisions Made

- Persisted command facts, not retry-time wall clock or request reconstruction, determine quota period, counter value, usage event, attachment order, message IDs, and replay anchors.
- A deterministic pre-bind domain rejection becomes a durable safe rejection and conditionally reverses the command's quota operation; an ambiguous repository outcome remains retryable for reconciliation.
- Command rereads require the exact owner, request fingerprint, entity type, and `message-command.v2` schema before any stored state or result is used.
- `message_in_progress` is reserved for a live claimed or leased command. Rejected, terminal, expired, missing, malformed, and dependency-retry states retain distinct closed outcomes.

## Verification

- RED gate: **19 failed, 2 passed**, and the wrapper confirmed pytest exit status 1.
- Task 2 repository/usage gate: **76 passed, 165 deselected**.
- Task 3 exact command/transport gate: **61 passed, 15 deselected**.
- Complete new command, inherited conversation, and attachment-security files: **296 passed**.
- Targeted Ruff on all modified production and test files: **passed**.
- `git diff --check`: **passed**.
- Fixed-string production-source privacy-canary denial: **passed**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved initialMessage removal into the Task 2 green gate**
- **Found during:** Task 2 (Implement typed command transitions and transactional usage identity)
- **Issue:** The plan's exact Task 2 selector selected all tests in the new command module, including the already-authored initialMessage regression, so the repository implementation alone could not make the mandatory green gate pass.
- **Fix:** Removed the legacy request field and route-side processing during the Task 2 green implementation; Task 3 subsequently completed the shared executor and legacy-path removal.
- **Files modified:** `src/stoa/routers/conversations.py`, `tests/test_phase473_message_command.py`
- **Verification:** Task 2 gate passed with 76 tests; the final route regression returns 422 before any write.
- **Committed in:** `5e4b9b6`

**2. [Rule 1 - Bug] Updated inherited tests that depended on removed ambiguous paths**
- **Found during:** Task 3 (Drive regular and SSE responses from durable command state only)
- **Issue:** Inherited fixtures patched the deleted `_send_message_impl`, separate `_record_chat_usage`, and tuple/bool lease results, so they no longer exercised the production command boundary.
- **Fix:** Pointed fixtures at the unified executor and typed dispositions, removed obsolete post-effect expectations, and retained equivalent durable-command assertions.
- **Files modified:** `tests/test_conversations.py`, `tests/test_attachment_security.py`
- **Verification:** All 296 affected-file tests pass.
- **Committed in:** `00b6a94`

**3. [Rule 2 - Missing Critical] Retried partial DynamoDB attachment rereads**
- **Found during:** Plan-level lower-boundary fault review
- **Issue:** `get_attachments` ignored DynamoDB `UnprocessedKeys`, allowing an incomplete resume read to be mistaken for an authoritative missing attachment set.
- **Fix:** Added three bounded retries for both high-level and low-level batch clients and a redacted dependency failure after exhaustion.
- **Files modified:** `src/stoa/db/repositories/attachment_repo.py`, `tests/test_phase473_message_command.py`
- **Verification:** Explicit retry/exhaustion tests pass and the complete 296-test suite remains green.
- **Committed in:** `cc17e8b`

---

**Total deviations:** 3 auto-fixed (1 blocking issue, 1 bug, 1 missing critical safeguard)
**Impact on plan:** All changes were necessary to satisfy the planned typed-state, lower-boundary fault, and no-partial-replay contracts; no new infrastructure or public feature scope was added.

## Issues Encountered

None beyond the auto-fixed items above.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Next Phase Readiness

- Ready for Plan 473-21 to consume the persisted history anchor and durable message identities.
- No remaining blocker is known for the conversation command lifecycle.

## Self-Check: PASSED

- All created and modified key files exist.
- Task commits `86fd149`, `5e4b9b6`, `00b6a94`, and `cc17e8b` exist in repository history.
- RED, task-level, complete affected-file, Ruff, whitespace, and privacy-denial gates pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
