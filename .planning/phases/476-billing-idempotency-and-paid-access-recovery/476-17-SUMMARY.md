---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 17
subsystem: ai-billing
tags: [bedrock, count-tokens, allowance, idempotency, durable-replay]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    plan: 15
    provides: Conditional weekly token reservation, provider-cost evidence, finalization, and restoration
  - phase: 476-billing-idempotency-and-paid-access-recovery
    plan: 16
    provides: Strict AIProviderResult and authoritative configured-model CountTokens boundary
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    provides: Durable question command/effect receipts, terminal proof, and stable replay
provides:
  - Exact configured-model question token admission before InvokeModel
  - Content-free provider usage evidence bound to one durable question effect
  - Durable-result-only exact debit, terminal restoration, and disconnect-safe replay
affects: [476-18, question-ai, allowance-finalization, provider-cost-evidence]

tech-stack:
  added: []
  patterns:
    - Bedrock client boundary counts the exact InvokeModel body and reserves before generation
    - Phase 475 effect plus plan, grant, allowance version, and Zurich week derive one opaque allowance identity
    - Durable private answer metadata drives provider observation and replay-safe finalization

key-files:
  created:
    - tests/test_question_token_finalization.py
  modified:
    - src/stoa/routers/questions.py

key-decisions:
  - "Derive the allowance effect from the existing opaque question AI effect plus persisted plan, grant, allowance version, and Zurich week so transport retries cannot create a second debit."
  - "Use a question-local Bedrock client boundary to CountTokens over the exact InvokeModel body, reserve both dimensions, and only then permit generation."
  - "Persist only content-free allowance/evidence coordinates inside the durable private AI receipt; the public QuestionResponse model excludes them."
  - "Finalize only after the Phase 475 durable result transaction is readable; restore only a proven terminal result rejection, while timeout and storage ambiguity remain reserved."

patterns-established:
  - "Question allowance convergence: count -> reserve -> invoke -> observe provider cost -> store result -> finalize exact actual counts."
  - "Replay repairs provider observation or finalization from the original durable receipt without invoking Bedrock again."

requirements-completed: [V9BILL-04]

duration: 16min
completed: 2026-07-24
---

# Phase 476 Plan 17: Durable Question Token Finalization Summary

**Question AI now reserves authoritative configured-model tokens before generation, retains exact content-free provider cost, and finalizes one user debit only after the validated answer is durably replayable.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-24T12:48:29Z
- **Completed:** 2026-07-24T13:04:14Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Bound each question allowance reservation to the existing Phase 475 AI command/effect plus persisted plan, grant, allowance version, and Europe/Zurich week.
- Counted the exact configured-model InvokeModel body and reserved exact input plus bounded maximum output before the mocked/provider client can generate.
- Persisted actual AIProviderResult counts as immutable content-free provider evidence before projecting the private result into the public question.
- Finalized exact actual input/output counts only after the durable question transaction succeeds, with replay repairing a timed-out finalization without a second provider call.
- Restored user availability after proven terminal validation/storage rejection while retaining provider cost and evidence; timeout and ambiguous storage outcomes remain reserved.
- Preserved the Phase 475 one-provider-call recovery behavior and proved disconnect-style response loss replays the byte-stable answer with one final debit.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-17-01 RED: Add failing question token finalization contract** - `06a98325` (test)
2. **Task 476-17-01 GREEN: Finalize question tokens at durable result boundary** - `adff0d8b` (feat)

## Files Created/Modified

- `tests/test_question_token_finalization.py` - Count failure, denial, provider timeout, store ambiguity, terminal restoration, finalize timeout, disconnect replay, redaction, and key-link selectors using only in-memory provider and DynamoDB fakes.
- `src/stoa/routers/questions.py` - Stable allowance identity, exact CountTokens/reservation client boundary, provider observation, durable result metadata, finalization/restoration, and replay convergence.

## Decisions Made

- The allowance effect is a domain-separated SHA-256 identity over the existing Phase 475 AI effect, command, persisted plan/grant/version, and original Zurich week. HTTP request identifiers never participate.
- CountTokens and InvokeModel share one mocked/runtime client and the identical serialized request body, avoiding local estimates or drift between admission and generation.
- Provider request/model coordinates are already digested at the AI boundary and are digested again by the allowance service before persistence; prompt and answer bytes never enter allowance evidence.
- The durable AI receipt carries private content-free convergence fields. FastAPI's closed public AI response projection omits all allowance and provider-evidence coordinates.
- A result-store timeout or provider timeout remains recoverable and reserved. Only a closed terminal result rejection restores the user's reservation, and that restoration never removes provider cost.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- Before-reserve CountTokens failure returns `provider_token_count_unavailable`, writes no allowance effect, and never invokes the provider.
- Allowance denial returns `allowance_exhausted` and never invokes the provider.
- Provider timeout after reservation remains reserved with no finalization or restoration.
- Ambiguous result storage retains the reservation and provider cost without finalizing or restoring.
- Terminal validated-result storage rejection restores both reserved dimensions while preserving exact provider cost and immutable evidence.
- Finalization timeout returns `allowance_finalization_recoverable`; replay finalizes the original durable answer with no second provider call.
- Disconnect-style committed-response loss retains one exact debit and replays the same result.
- Public responses and provider evidence contain none of the private allowance fields, prompt canary, or answer canary.

## Known Stubs

None.

## Issues Encountered

- The GSD helper was not installed on `PATH`; its installed CLI was invoked directly with `node` as required.
- The aggregate `scripts/verify_phase476_security_gate.py` does not exist yet. This plan's source-bound High-threat selectors pass; aggregate phase-gate construction remains later Phase 476 ownership.

## Verification

- Exact plan command: 19 passed across question allowance finalization and inherited Phase 475 effect recovery.
- Broader question/replay/Bedrock/allowance regression: 130 passed.
- Ruff passed the exact planned source and test files.
- Targeted mypy passed `src/stoa/routers/questions.py`.
- `git diff --check` passed.
- RED and GREEN TDD gate commits exist in order.

## User Setup Required

None - no dependencies, credentials, external provider calls, deployments, customer charges, or production mutations were introduced.

## Next Phase Readiness

- Plan 18 can reuse the count/reserve/observe/durable-finalize sequence for conversation and hint effects.
- The source-bound question High-threat matrix is closed; the later aggregate Phase 476 gate still needs to bind this plan's selectors before phase completion.

## Self-Check: PASSED

- FOUND: `src/stoa/routers/questions.py`
- FOUND: `tests/test_question_token_finalization.py`
- FOUND: `06a98325`
- FOUND: `adff0d8b`
- PASS: exact plan verification (`19 passed`)
- PASS: expanded regression (`130 passed`)
- PASS: Ruff, targeted mypy, and diff check

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
