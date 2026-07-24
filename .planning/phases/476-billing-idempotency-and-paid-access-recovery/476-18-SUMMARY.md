---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 18
subsystem: ai-billing
tags: [bedrock, conversations, sse, allowances, idempotency, durable-replay]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    plan: 15
    provides: Conditional Zurich-week reservation, provider-cost evidence, exact finalization, and restoration
  - phase: 476-billing-idempotency-and-paid-access-recovery
    plan: 16
    provides: Strict AIProviderResult usage evidence and configured-model CountTokens boundary
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    provides: Durable conversation message commands, AI leases, and regular/SSE stable replay
provides:
  - Exact configured-model conversation admission before InvokeModel
  - One durable allowance identity shared by regular, SSE, and generated-hint projection
  - Content-free provider evidence and replay-repairable final debit metadata
  - Explicit provider-cost-only conversation title classification
affects: [476-19, conversation-ai, hint-generation, allowance-finalization, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Durable message command snapshots plan, grant, allowance version, and Zurich week before provider invocation
    - Private replay payload carries allowance convergence metadata while the public response model drops it
    - Provider timeout and ambiguous storage retain reservation; only terminal validated-result rejection restores it

key-files:
  created:
    - tests/test_conversation_token_finalization.py
  modified:
    - src/stoa/routers/conversations.py

key-decisions:
  - "Derive one allowance effect from the durable message command, assistant message, persisted plan/grant/version, and original Zurich week; transport correlation IDs never own the debit."
  - "Persist content-free allowance convergence metadata inside the existing command result JSON so regular and SSE replay can repair finalization without another provider call."
  - "Treat the hint embedded in the validated conversation provider result as part of that same durable message effect and debit, while title generation remains explicitly provider-cost-only."

patterns-established:
  - "Conversation allowance convergence: count -> reserve -> invoke -> observe provider cost -> store durable command result -> finalize exact actual counts."
  - "Replay repair: completed message command finalizes from private result metadata before projecting the closed public response."

requirements-completed: [V9BILL-04]

duration: 11min
completed: 2026-07-24
---

# Phase 476 Plan 18: Durable Conversation Token Finalization Summary

**Regular, SSE, and generated-hint conversation results now share one configured-model reservation, content-free provider receipt, durable replay boundary, and exact actual-token debit.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-24T13:08:16Z
- **Completed:** 2026-07-24T13:19:07Z
- **Tasks:** 1
- **Files modified:** 2 implementation/test files

## Accomplishments

- Bound conversation allowance identity to the existing durable message command, deterministic assistant message, persisted entitlement snapshot, and original Europe/Zurich week.
- Counted the exact configured-model InvokeModel body and reserved input plus bounded output before the mocked/runtime generation boundary.
- Recorded actual provider input/output evidence before durable storage and finalized only after the command result became stable-replay readable.
- Stored private content-free convergence fields in the durable result JSON while preserving the unchanged public `SendMessageResponse` projection.
- Made regular and SSE replay repair the same finalization without another provider call or debit; the generated hint in the answer remains part of the same effect.
- Kept provider timeout and ambiguous store outcomes reserved, restored only terminal validated-result rejection, and retained provider cost through restoration.
- Marked conversation title generation explicitly `PROVIDER_COST_ONLY`, with no student reservation or finalization path.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-18-01 RED: Add failing conversation token finalization contract** - `901f0da6` (test)
2. **Task 476-18-01 GREEN: Finalize conversation tokens at durable result boundary** - `9fb6a8d4` (feat)

## Files Created/Modified

- `tests/test_conversation_token_finalization.py` - Mocked CountTokens/InvokeModel admission, denial, timeout, storage ambiguity, terminal restoration, finalization repair, regular/SSE/hint replay, privacy, title isolation, and key-link selectors.
- `src/stoa/routers/conversations.py` - Durable allowance identity snapshot, CountTokens reservation client, provider observation, private replay metadata, exact finalization/restoration, and closed title classification.

## Decisions Made

- The existing durable message command remains the sole conversation effect owner. HTTP request and stream transport identifiers do not participate in allowance identity.
- The original command creation timestamp selects the Zurich week, preventing retries across midnight or week boundaries from moving the debit.
- Private allowance metadata is stored alongside the durable command result rather than exposed on `ChatMessage` or `SendMessageResponse`.
- The conversation answer’s validated hint is one output from the same provider invocation, durable assistant message, and allowance effect; it never creates a second debit.
- Legacy inherited test doubles may return a plain mapping, but production provider execution must return the Plan 16 `AIProviderResult` with the closed `USER_ALLOWANCE` class.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deferred entitlement resolution until after attachment validation**
- **Found during:** Task 476-18-01 expanded conversation regression
- **Issue:** Resolving the allowance snapshot before attachment validation changed a foreign-attachment rejection into a dependency error and broke the established zero-command/zero-provider-effect boundary.
- **Fix:** Resolve and persist allowance coordinates immediately before the durable command claim, after deterministic attachment validation; resume paths reconstruct only missing legacy coordinates before AI lease admission.
- **Files modified:** `src/stoa/routers/conversations.py`
- **Verification:** The three initially failing inherited conversation selectors pass, and the 189-test expanded regression is green.
- **Committed in:** `9fb6a8d4`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** The correction preserves the Phase 473 attachment concealment/effect-ordering contract while retaining before-provider allowance admission. No product or operational scope was added.

## Security Verification

- CountTokens failure and weekly allowance denial never invoke the mocked provider.
- Provider timeout retains the original reservation without finalization or restoration.
- Ambiguous durable-result storage retains reservation plus provider cost without claiming delivery.
- Terminal validated-result rejection restores only user availability and retains exact provider evidence/cost.
- Regular and SSE replay finalize the same durable answer and generated hint exactly once.
- Finalization timeout is repaired from the original command result without another provider call.
- Public models omit allowance effect/evidence/finalization fields, and provider evidence contains neither message nor answer canaries.
- The closed direct-InvokeModel inventory passes and title generation is explicitly provider-cost-only.
- No real provider, credentials, external service, deployment, customer charge, or production mutation was used.

## Known Stubs

None.

## Issues Encountered

- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet; its construction and final zero-High phase closure remain assigned to Plan 476-29. This plan’s source-bound High-threat selectors pass.
- Targeted mypy still reports 17 pre-existing errors in `conversations.py`; Plan 476-18 introduced no remaining mypy error. The existing debt is recorded in `deferred-items.md`.

## Verification

- Exact plan command: 41 passed across new conversation token finalization and inherited durable message behavior.
- Expanded conversation/replay/deletion/provider/allowance regression: 189 passed.
- Closed InvokeModel caller inventory selector: 1 passed.
- Ruff passed the exact planned source and test files.
- `git diff --check` passed.
- TDD RED and GREEN commits exist in order.

## User Setup Required

None - all provider behavior was mocked and no external configuration or manual action is required.

## Next Phase Readiness

- Plan 476-19 can add teacher-support case admission without changing message/reply token finalization.
- Plan 476-29 can bind these source selectors into the aggregate Phase 476 security gate and independently verify zero open ASVS L1 High threats.

## Self-Check: PASSED

- FOUND: `src/stoa/routers/conversations.py`
- FOUND: `tests/test_conversation_token_finalization.py`
- FOUND: `901f0da6`
- FOUND: `9fb6a8d4`
- PASS: exact plan verification (`41 passed`)
- PASS: expanded regression (`189 passed`)
- PASS: closed InvokeModel inventory, Ruff, and diff check

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
