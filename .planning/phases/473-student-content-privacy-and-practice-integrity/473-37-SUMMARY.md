---
phase: 473-student-content-privacy-and-practice-integrity
plan: 37
subsystem: notification-delivery-security
tags: [dynamodb, cas, leases, crash-recovery, provider-ambiguity, privacy]

# Dependency graph
requires:
  - phase: 473-28
    provides: Immutable source-bound Phase 473 evidence and delivery-intent review baseline
  - phase: 473-34
    provides: Owner-fenced notification delivery intents and deletion retention policy
provides:
  - Closed private-owner and sealed-global delivery scope contracts
  - Opaque versioned pre-effect and inflight delivery claims
  - Explicit-time expired takeover and ambiguity-terminal recovery
  - Provider invocation ordered immediately after one durable begin CAS
affects: [473-38, 473-39, 473-40, V9PRIV-02, notification-delivery]

# Tech tracking
tech-stack:
  added: []
  patterns: [pre-effect lease recovery, durable effect-inflight marker, provider-neutral terminal replay]

key-files:
  created:
    - tests/test_phase473_delivery_intent_recovery.py
  modified:
    - src/stoa/db/repositories/notification_repo.py
    - src/stoa/services/notification_service.py
    - tests/test_phase473_notification_deletion.py

key-decisions:
  - "Only expired claimed_pre_effect work can be taken over; effect_inflight is conditionally terminalized as provider_acceptance_unknown and never becomes claimable."
  - "The final pre-provider transition carries exact scope, payload, lease-owner, and intent-version CAS facts; private scope also carries the current active account fence."
  - "Delivery replay returns only accepted, provider_acceptance_unknown, canceled_account_deletion, or retryable_claim_conflict and never returns provider payloads or exceptions."

patterns-established:
  - "Delivery CAS chain: registered -> claimed_pre_effect -> effect_inflight -> one provider-neutral terminal outcome."
  - "Crash classification: before durable begin is recoverable after actual expiry; at or after durable begin is permanently ambiguity-safe."

requirements-completed: [V9PRIV-02]

# Metrics
duration: 13min
completed: 2026-07-18
---

# Phase 473 Plan 37: Crash-Safe Delivery-Intent State Machine Summary

**Explicit-time pre-effect takeover, exact versioned effect-begin CAS, and terminal provider-ambiguity replay now recover worker crashes without blind duplicate email, push, or realtime effects**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-18T14:59:51Z
- **Completed:** 2026-07-18T15:12:16Z
- **Tasks:** 3
- **Files modified:** 4 implementation/test files plus this summary

## Accomplishments

- Added closed `DeliveryIntentScope` and opaque `DeliveryIntentClaim` contracts, canonical scope/payload digests, immutable registration identity, and advancing intent versions.
- Made only expired `claimed_pre_effect` work eligible for takeover relative to explicit current time; unexpired claims, inflight effects, and terminal outcomes cannot be stolen.
- Added the final `begin_delivery_effect` transaction with exact claim/version/digest conditions and the active private account fence or persisted sealed-global classification facts.
- Terminalized observed inflight work as `provider_acceptance_unknown`, bound cancel/complete to exact claims, and kept terminal replay provider-neutral.
- Proved pre-begin, post-begin, post-acceptance, and lost-terminal-response crash behavior with exact provider-call counters and stale-owner/version races.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing delivery-intent crash and stale-claim state-machine tests** — `c15b603` (test, RED)
2. **Task 2: Implement explicit-time pre-effect recovery and effect-inflight CAS** — `0ecab26` (feat, GREEN)
3. **Task 3: Drive provider calls only after durable begin and replay crash states safely** — `af0f52f` (feat, service convergence)

## Files Created/Modified

- `tests/test_phase473_delivery_intent_recovery.py` — Explicit-time predicates, exact transition CAS, crash injection, provider counters, stale takeover, scope contracts, and call-order coverage.
- `src/stoa/db/repositories/notification_repo.py` — Scope/claim types, v2 durable intent schema, explicit-time claim, final begin transaction, inflight recovery, and exact terminal writes.
- `src/stoa/services/notification_service.py` — Stable operation registration/recovery/claim/check/begin/provider/complete orchestration with redacted replay outcomes.
- `tests/test_phase473_notification_deletion.py` — Updated source registry and inherited deletion-fence/provider-ambiguity assertions for the versioned state machine.

## Decisions Made

- Kept claims free of raw payloads, provider coordinates, endpoints, and private owner identifiers; claims carry only opaque operation/lease IDs, digests, versions, and expiry.
- Compared stored lease expiry with caller-supplied current epoch and treated equality as still leased, requiring actual passage (`lease_expires_at < now_epoch`) before takeover.
- Advanced the version when claiming, beginning, and terminalizing so a previous owner or transition version cannot begin, cancel, complete, or recover newer work.
- Preserved an exact-version legacy adapter for currently untouched Plan 473-38 callers while all new service execution uses typed scope/claim operations.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- **RED:** 9 tests failed behaviorally; pytest exited exactly `1` with no collection/import errors.
- **Task 2 GREEN:** 5 passed, 5 deselected; targeted Ruff passed.
- **Task 3 plan gate:** 12 passed, 5 deselected; targeted Ruff passed.
- **Combined delivery/deletion suite:** 17 passed.
- **Full repository suite:** 1,945 passed, 2 failed. Both failures are the expected checked source-inventory drift owned by Plan 473-39; they now report the two Plan 473-36 sources plus `notification_repo.py` and `notification_service.py`. No inventory was refreshed in this plan.
- **Diff hygiene:** `git diff --check` passed.

## Issues Encountered

- The repository CLI shim was not on `PATH`; execution used the checked SDK entrypoint through `node /Users/zhdeng/.codex/get-shit-done/bin/gsd-tools.cjs`.
- Full-suite source inventory generators correctly rejected the four intentionally modified mutating sources. Plan 473-39 owns refreshing and reviewing both checked inventories.

## Authentication Gates

None.

## Known Stubs

None. Empty collections in focused tests and existing notification aggregation code are deliberate initial/negative states, not unwired production behavior.

## User Setup Required

None - no package installation, provider access, deployment, or production mutation was required.

## Next Phase Readiness

- Plan 473-38 can authoritatively resolve private ownership/global classification and route digest, push, and WebSocket callers through this typed primitive.
- Plan 473-39 must refresh and review the checked boundary/private-store inventories for all four Plan 36/37 source changes.
- Plan 473-40 can then capture immutable evidence against the unchanged final candidate.

## TDD Gate Compliance

- RED commit: `c15b603`
- GREEN commit: `0ecab26`
- Service convergence commit: `af0f52f`

## Self-Check: PASSED

- All four implementation/test artifacts and this summary exist.
- Task commits `c15b603`, `0ecab26`, and `af0f52f` exist in repository history.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
