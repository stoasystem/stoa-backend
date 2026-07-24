---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 15
subsystem: billing
tags: [dynamodb, allowances, idempotency, europe-zurich, provider-usage]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical allowance models, four-plan vocabulary, and locked budget contracts from Plans 01 and 03
provides:
  - Conditional per-beneficiary Zurich-week input/output token reservations
  - Effect-idempotent provider observation, exact finalization, and user restoration
  - Immutable content-free provider-cost evidence retained independently of user debit
  - Parent remaining/percentage and admin exact redacted allowance projections
affects: [476-16, 476-17, 476-18, ai-admission, paid-access, account-operations]

tech-stack:
  added: []
  patterns:
    - Local-calendar Zurich week boundaries converted to UTC only after Monday dates are resolved
    - Payload-bound effect receipts plus counter CAS in one account-fenced transaction
    - Provider-cost evidence and user allowance debit advance through separate durable dimensions

key-files:
  created:
    - src/stoa/db/repositories/allowance_repo.py
    - src/stoa/services/allowance_service.py
    - tests/test_token_allowances.py
  modified: []

key-decisions:
  - "Key weekly counters by beneficiary and week rather than allowance version so a monotonic in-week plan upgrade preserves already consumed and reserved usage."
  - "Persist provider usage as an immutable redacted row and increment provider-cost totals before delivery finalization, allowing restoration to release only the user reservation."
  - "Domain-digest logical effects, provider request IDs, and model IDs before persistence; no prompt, answer, content, or raw provider coordinate enters allowance evidence."

patterns-established:
  - "Two-dimensional admission: finalized plus reserved input and output must each fit the current locked plan budget before one transaction can commit."
  - "Stable transition replay: reservation, provider observation, finalization, and restoration compare immutable payload digests and return the original durable model."

requirements-completed: [V9BILL-04]

duration: 8min
completed: 2026-07-24
---

# Phase 476 Plan 15: Weekly Token Allowance Ledger Summary

**Europe/Zurich weekly token budgets now use account-fenced conditional reservations, exact provider-reported finalization, and immutable redacted provider-cost evidence that survives user allowance restoration.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-24T10:06:45Z
- **Completed:** 2026-07-24T10:15:06Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Implemented the exact D-19 input/output budgets for `free_trial`, `student`, `teacher_supported`, and per-selected-beneficiary `family` allowance accounting.
- Derived each week from Europe/Zurich Monday calendar dates, including 167-hour spring and 169-hour fall UTC spans, with new counters rather than rollover.
- Added account-fenced, payload-bound conditional reservation transactions that prevent either token dimension from overspending under concurrent requests.
- Added immutable provider observation, exact delivered-result finalization, terminal user restoration, and byte-stable replay without double debit or double provider-cost recording.
- Added parent-safe remaining/percentage projections and admin-only exact evidence containing only digests, counts, timestamps, and closed outcome fields.
- Proved the implementation with 20 focused budget, DST, concurrency, replay, restoration, strict parsing, upgrade, projection, and redaction selectors.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-15-01 RED: Add failing weekly allowance contract** - `fff711f` (test)
2. **Task 476-15-01 GREEN: Implement weekly token allowance ledger** - `88f3ce1` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/allowance_repo.py` - Conditional counters, effect receipts, immutable provider evidence, exact finalization/restoration, strict persisted-count parsing, and evidence reads.
- `src/stoa/services/allowance_service.py` - Zurich calendar windows, canonical plan budgets, opaque identity derivation, reservation/finalization adapters, and role-safe projections.
- `tests/test_token_allowances.py` - Exact budgets, DST, no-rollover, concurrent overspend, replay, monotonic upgrade, provider cost, restoration, malformed-state, privacy, and key-link coverage.

## Decisions Made

- A counter is keyed by beneficiary plus ISO week, not allowance version. A higher allowance version can raise the current budget without resetting usage, while a stale or same-version mismatched plan fails closed.
- Provider usage is observed and costed exactly once before user-debit finalization. Restoration subtracts only the original user reservation and never decrements provider-cost counters or deletes evidence.
- Provider request/model coordinates and caller effect identities are domain-separated SHA-256 digests before persistence.
- Final user debit requires technical validation, safety approval, durable storage, and stable replay readability; any terminally undelivered result uses the separate restoration operation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Allowed restoration after provider usage exceeds the reserved estimate**
- **Found during:** Task 476-15-01 GREEN security review
- **Issue:** The first shared completion guard rejected both finalization and restoration when provider-reported counts exceeded the reservation, which could leave an undelivered user's reservation permanently held.
- **Fix:** Exact delivered finalization still refuses an over-reservation debit, while restoration can release the original user reservation and retain the full immutable provider cost.
- **Files modified:** `src/stoa/db/repositories/allowance_repo.py`, `tests/test_token_allowances.py`
- **Verification:** `test_provider_overage_cannot_finalize_but_can_restore_user_reservation`
- **Committed in:** `88f3ce1`

**2. [Rule 2 - Missing Critical] Prevented stale allowance versions from regressing an upgraded weekly counter**
- **Found during:** Task 476-15-01 GREEN security review
- **Issue:** A stale entitlement caller could otherwise replace the counter's newer plan/version metadata even though existing usage remained, weakening monotonic paid-access convergence.
- **Fix:** Lower allowance versions fail closed; an equal version must match the persisted plan and budgets; only a higher version may advance the plan while preserving all usage dimensions.
- **Files modified:** `src/stoa/db/repositories/allowance_repo.py`, `tests/test_token_allowances.py`
- **Verification:** `test_higher_allowance_version_preserves_usage_and_stale_version_fails_closed`
- **Committed in:** `88f3ce1`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical functionality).
**Impact on plan:** Both changes enforce D-15/D-22 correctness and fail-closed accounting without adding product or operational scope.

## Security Verification

- Every reservation transaction binds the active account fence, one create-only payload-bound effect, and one version-conditional weekly counter replacement.
- Barrier tests independently exhaust the input and output dimensions; exactly one competing final-slot reservation commits.
- Persisted booleans, fractions, negative values, numeric strings, malformed plan IDs, and overflowing exact counts fail closed.
- Provider evidence contains only domain-digested coordinates, exact counts, retention state, and observation time; prompt, answer, content, and raw provider canaries are absent.
- Restoration preserves provider-cost counters and evidence while removing only user reservation/debit.
- The plan's 20 source-bound High-threat selectors pass. The aggregate `scripts/verify_phase476_security_gate.py` does not yet exist and remains later Phase 476 gate ownership; this plan does not claim aggregate phase completion.

## Known Stubs

None.

## Issues Encountered

- The phase-wide security gate script named by the plan frontmatter is not present yet. Focused source-bound verification is complete; aggregate phase-gate construction remains assigned to a later Phase 476 plan.

## User Setup Required

None - no dependencies, credentials, provider calls, customer charges, frontend changes, deployments, or production mutations were introduced.

## Next Phase Readiness

- AI provider boundaries can reserve predicted maximum output, record actual provider counts, and finalize only after durable safe delivery.
- Parent/admin account operations can consume the role-safe projections without handling prompts, answers, raw provider IDs, or storage coordinates.
- Teacher-support case accounting remains separate Phase 476 work; this plan implements only the repository half of D-22 and token dimensions required by V9BILL-04.

## Self-Check: PASSED

- FOUND: `src/stoa/db/repositories/allowance_repo.py`
- FOUND: `src/stoa/services/allowance_service.py`
- FOUND: `tests/test_token_allowances.py`
- FOUND: `fff711f`
- FOUND: `88f3ce1`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_token_allowances.py` (`20 passed`)
- PASS: combined allowance model/repository verification (`98 passed`)
- PASS: `.venv/bin/ruff check src/stoa/db/repositories/allowance_repo.py src/stoa/services/allowance_service.py tests/test_token_allowances.py`
- PASS: window/budget resolution precedes `allowance_repo.reserve_allowance`

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
