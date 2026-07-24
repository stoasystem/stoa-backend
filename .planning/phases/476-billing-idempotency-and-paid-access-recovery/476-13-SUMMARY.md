---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 13
subsystem: payments
tags: [billing, entitlements, dynamodb, grace, attachments, idempotency]

requires:
  - phase: 476-12
    provides: Exact relationship-fenced beneficiary grants and monotonic paid upgrades
provides:
  - Versioned period-end cancellation and downgrade schedules that preserve paid access until due
  - Immutable 72-hour renewal grace with conditional recovery and exact-once free fallback
  - Historical grant retention plus shared admission-only 5 GB free and 15 GB paid attachment limits
affects: [billing-lifecycle, effective-entitlements, attachment-admission, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Subscription-digest and plan-version transition identities with conditional version receipts
    - Atomic current-grant transition plus immutable prior-grant history
    - Storage downgrade changes only fresh-byte admission and never invokes deletion

key-files:
  created:
    - tests/test_paid_entitlement_transitions.py
  modified:
    - src/stoa/services/paid_entitlement_service.py
    - src/stoa/services/entitlement_service.py
    - src/stoa/services/attachment_service.py

key-decisions:
  - "Keep period-end schedules and renewal grace as separate paid_transition.v1 records under the exact subscription digest so either lifecycle can replay independently."
  - "Derive the first renewal-failure deadline once and treat every same-plan-version failure as replay, even when a delayed event carries a different delivery identity."
  - "Apply due transitions in one transaction that retains an immutable prior-grant row, conditionally advances the current grant, and records the transition receipt without touching allowance counters or attachment storage."

patterns-established:
  - "Transition authority is exact subscription digest, plan version, effective timestamp, beneficiary set, transition identity, status, and transition version."
  - "Attachment capacity is resolved through attachment_service.attachment_storage_limit for both effective entitlement projection and paid-transition receipts."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 8min
completed: 2026-07-24
---

# Phase 476 Plan 13: Monotonic Paid Lifecycle Transitions Summary

**Paid cancellations, downgrades, and renewal failures now preserve purchased access until an exact due boundary, retain historical grants and stored bytes, and replay through one versioned transition receipt.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-24T14:30:40Z
- **Completed:** 2026-07-24T14:38:17Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added `PaidTransitionDisposition`, `schedule_period_end_transition()`, `start_renewal_grace()`, `clear_renewal_grace()`, and `apply_due_paid_transition()`.
- Persisted source-bound `paid_transition.v1` records with exact subscription, plan-version, beneficiary, effective-time, grace, identity, status, and transition-version coordinates.
- Kept cancellation and downgrade grants unchanged one second before the paid-period boundary, applied them at the boundary, and returned the same receipt after it.
- Fixed the first renewal-failure deadline at exactly 72 hours, refused delayed duplicate extension, and preserved paid grants plus consumed allowance after pre-expiry recovery.
- Retained immutable prior-grant history during due downgrade/free fallback while leaving attachment objects, byte counters, and weekly usage counters untouched.
- Centralized the 5 GB free / 15 GB paid attachment admission limit and proved over-limit downgrade rejects only the next fresh-byte reservation with the stable `storage_quota_exceeded` code.

## Task Commits

TDD execution produced the mandatory RED and GREEN gates:

1. **Task 476-13-01 RED: Add failing paid transition contract** - `4d908a3` (test)
2. **Task 476-13-01 GREEN: Implement monotonic paid transitions** - `fb0aa95` (feat)

## Files Created/Modified

- `tests/test_paid_entitlement_transitions.py` - Period/grace time travel, immutable deadline, recovery, fallback, replay, history, aggregate stability, no-delete, and exact key-link selectors.
- `src/stoa/services/paid_entitlement_service.py` - Versioned schedule/grace persistence, conditional recovery, due transition transaction, historical grant rows, and transition receipts.
- `src/stoa/services/entitlement_service.py` - Effective entitlement storage projection now delegates to the shared attachment admission authority.
- `src/stoa/services/attachment_service.py` - Shared settings-aware `attachment_storage_limit()` with the existing compatibility admission wrapper.

## Decisions Made

- Used one subscription-scoped record per transition kind (`period_end` and `renewal_grace`) rather than allowing event-delivery rows to control effective access. A newer plan version may replace a terminal older record; an equal/older delayed fact cannot.
- Preserved grace timestamps after recovery as historical evidence while changing only status, `cleared_at`, and transition version. Recovery never rewrites usage or grants.
- Retained the old grant as `paid_grant_history.v1` before conditionally advancing the current grant. Free fallback makes the current paid grant historical so the existing effective-entitlement resolver falls back to `free_trial`.
- Stored the post-transition attachment admission limit on the receipt through an exact call to `attachment_service.attachment_storage_limit`; no transition code imports or calls an object-deletion path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Established the planned paid-transition to attachment-admission source link**
- **Found during:** Task 476-13-01 pre-wave verification
- **Issue:** Attachment admission had a local tier mapper, and `paid_entitlement_service.py` had no `attachment_storage_limit` link, so the planned effective-plan-to-upload-limit boundary was not source-verifiable.
- **Fix:** Added one settings-aware `attachment_service.attachment_storage_limit()` authority, delegated entitlement projection to it, and recorded its exact result on every applied transition receipt.
- **Files modified:** `src/stoa/services/attachment_service.py`, `src/stoa/services/entitlement_service.py`, `src/stoa/services/paid_entitlement_service.py`
- **Verification:** Exact source-link selector passes; over-free-limit fresh-byte admission returns `storage_quota_exceeded` and invokes no deletion.
- **Committed in:** `fb0aa95`

---

**Total deviations:** 1 auto-fixed (1 Rule 2 missing critical integration)
**Impact on plan:** The change establishes the specified trust-boundary link without adding a provider call, deletion path, new dependency, network endpoint, or production operation.

## Security Verification

- Period-end identity binds the subscription digest, provider plan version, current/target plans, and exact paid-period timestamp; an equal/older delayed schedule cannot replace it.
- Grace identity and deadline derive from the first renewal-failure fact, while every same-plan-version duplicate returns the persisted record without moving `grace_expires_at`.
- Recovery and scheduler application both condition on identity, status, and transition version; the first committed outcome wins and subsequent processing replays its receipt.
- Due application writes prior-grant history, current grants, and transition receipt in one conditional transaction. It writes no weekly allowance counter or attachment-storage aggregate.
- One-second-before, exact-boundary, and one-second-after selectors pass for the paid period; equivalent pre-expiry/exact-expiry/replay selectors pass for grace.
- Failed upgrade and expired checkout regression selectors preserve prior active access; focused byte-stability tests preserve grants, counters, stored bytes, and object count.
- The exact planned key link is observed: `paid_entitlement_service.py` calls `attachment_service.attachment_storage_limit`.
- No provider SDK, network request, charge, refund, object deletion, deployment, production data operation, or production mutation was performed.
- The later aggregate `scripts/verify_phase476_security_gate.py` is not present yet; this summary records focused source-bound ASVS L1 evidence without claiming the aggregate phase gate.

## Known Stubs

None introduced. Optional transition fields and empty in-memory test collections are bounded persisted/test state, not unwired application data.

## Issues Encountered

- The repository sandbox denied direct `.git/index.lock` creation for the RED commit; the managed approval path created both normal commits with hooks enabled and no verification bypass.
- Targeted mypy passes for the new paid-transition service. Four inherited diagnostics remain in untouched account-purge narrowing and untyped DynamoDB access sections of the attachment/entitlement services; they are recorded in `deferred-items.md`.
- One existing Starlette test-client deprecation warning remains for the future `httpx2` migration.

## User Setup Required

None - no dependency, credential, provider, schema migration command, or external configuration was added.

## Next Phase Readiness

- Signed billing lifecycle orchestration and the scheduled worker can call the exact transition APIs without reimplementing period, grace, storage, or replay rules.
- Later Phase 476 plans must include these six focused selectors in the aggregate security gate and prove the approved sandbox Web journey before phase-level completion.

## Self-Check: PASSED

- FOUND: `src/stoa/services/paid_entitlement_service.py`
- FOUND: `src/stoa/services/entitlement_service.py`
- FOUND: `src/stoa/services/attachment_service.py`
- FOUND: `tests/test_paid_entitlement_transitions.py`
- FOUND: `476-13-SUMMARY.md`
- FOUND: `4d908a3`
- FOUND: `fb0aa95`
- PASS: focused transition suite (`6 passed`)
- PASS: paid-transition plus attachment/subscription/webhook/grant regression (`300 passed`)
- PASS: planned Ruff gate, targeted paid-transition mypy, and `git diff --check`
- PASS: exact paid-transition-to-attachment admission-limit source link

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
