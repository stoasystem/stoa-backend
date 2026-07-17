---
phase: 473-student-content-privacy-and-practice-integrity
plan: 16
subsystem: storage-security
tags: [privacy, provider-body, dynamodb, idempotency, sse]

requires:
  - phase: 473-13
    provides: Exact-version provider reads and the original body-close boundary
  - phase: 473-15
    provides: Strict provider-coordinate invariants and isolated cleanup recovery
provides:
  - Provider Body ownership before readable-shape inspection with best-effort exact-once close
  - Closed conversation repository transport classification across lookup, transaction, replay, lease, and completion paths
  - Same-fingerprint convergence after ambiguous committed message transactions with regular/SSE retry parity
affects: [473-17, V9PRIV-01, V9PRIV-02, phase-480-observability]

tech-stack:
  added: []
  patterns:
    - Own non-None provider bodies before property inspection and close from one outer finally
    - Translate all conversation repository transport through one closed retry boundary

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/routers/conversations.py
    - tests/test_attachment_security.py
    - tests/test_conversations.py

key-decisions:
  - "Provider Body ownership begins immediately after a non-None Body is returned; read and close properties are each inspected inside best-effort boundaries so cleanup cannot replace the primary outcome."
  - "Every conversation command repository call crosses one classifier; known semantic outcomes remain distinct while generic transport becomes a redacted bounded retry and ambiguous commits reread the original fingerprinted command."

patterns-established:
  - "Literal body ownership: acquire Body, enter try/finally, inspect read once, and offer close once without surfacing cleanup diagnostics."
  - "Conversation transport convergence: Stage A, claim, transaction, polling, recovery reads, AI lease, terminal marking, and completion share one structured adapter."

requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 12 min
completed: 2026-07-17
---

# Phase 473 Plan 16: Provider-body ownership and conversation transport convergence Summary

**Provider response bodies are now owned before shape inspection, and every conversation command repository outage converges through one redacted retry/replay contract without duplicating messages, attachments, quota, or AI work.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-17T08:45:03Z
- **Completed:** 2026-07-17T08:57:21Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Moved both staging validation/promotion and immutable conversation extraction into an outer Body ownership region before any `read` property lookup, while making missing, non-callable, and raising `close` shapes best effort.
- Added one conversation repository classifier covering Stage A, command/quota claim, attachment transaction, race/lost-response rereads, replay polling, stored-message recovery, AI lease/current reread, terminal marking, and completion.
- Classified non-`ClientError` described transactions as retryable dependencies without serializing provider, table, coordinate, content, owner, or exception diagnostics.
- Proved that a committed-then-lost attachment transaction resumes under the same fingerprint and produces one original message, attachment set, quota charge, extraction, AI call, and completion; regular and SSE failures expose the same bounded retry contract.

## Task Commits

Each task was committed atomically:

1. **Task 1: Own and close every returned provider body before shape validation** — `2d8405b` (fix)
2. **Task 2: Normalize conversation repository transport and preserve lost-response replay** — `7aa0deb` (fix)

## Files Created/Modified

- `src/stoa/services/attachment_service.py` — owns Body before readable-shape inspection, suppresses close lookup/call failures, and normalizes unexpected message-transaction failures.
- `src/stoa/db/repositories/attachment_repo.py` — classifies generic described transaction transport as `RETRYABLE_DEPENDENCY` and prevents dependency failures from collapsing into claim races.
- `src/stoa/routers/conversations.py` — routes every message-command repository stage through one closed adapter and emits matching regular/SSE 503 plus bounded `Retry-After` guidance.
- `tests/test_attachment_security.py` — covers missing, non-callable, and property-raising Body shapes plus generic transaction transport classification.
- `tests/test_conversations.py` — covers every named repository stage, regular/SSE parity, stored recovery reads, and committed lost-response same-fingerprint convergence.

## Decisions Made

- Bound `read` once inside the Body ownership region and made `close` lookup plus invocation independently best effort. This preserves maximum-plus-one reads, spool limits, checksum/length validation, parser semantics, and the original stable result even when cleanup itself is malformed.
- Kept semantic transaction outcomes closed and distinct while treating all unclassified repository/SDK transport as `upload_service_unavailable`. Fingerprint mismatch remains a conflict before attachment resolution; foreign ownership remains concealed.
- Kept ambiguous committed work in bounded convergence: a `message_committed`/`ai_running` reread never repeats binding or quota work, and the next exact retry resumes the deterministic command to its original stored result.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The initial atomic commit attempt was blocked by the managed sandbox's read-only `.git` metadata. The approved git operation was rerun with repository-write permission; hooks completed successfully and no verification was bypassed.

## Verification

- Provider Body ownership selector: **16 passed, 243 deselected**.
- Conversation transport/replay selector: **13 passed, 246 deselected**.
- Exact nine-module Phase 473 focused matrix: **445 passed**.
- Intermediate full attachment/conversation regression: **257 passed**; broader files/attachments/questions/conversations/practice regression: **344 passed**.
- Targeted Ruff over all five changed Python files and `git diff --check`: **passed**.

## Known Stubs

None. Stub-pattern matches were test-only mutable state accumulators used to prove post-commit replay convergence; all production paths are wired.

## Threat Flags

None. The modified provider-body and repository trust boundaries were explicitly covered by the plan threat model; no new endpoint, schema, authentication path, or file-access surface was introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- WR-010 and WR-011 are locally closed with adversarial executable coverage while V9PRIV-01 replay and V9PRIV-02 stable privacy/error behavior remain intact.
- Plan 473-17 can now lock a clean source candidate and regenerate evidence; real provider connection-pool behavior and deployed logs remain explicitly NOT RUN and Phase 480-owned.

## Self-Check: PASSED

- Both task commits exist in repository history and all five modified implementation/test files plus this summary exist on disk.
- Both plan selectors, the exact 445-test Phase 473 matrix, targeted Ruff, and diff hygiene passed on the committed implementation.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
