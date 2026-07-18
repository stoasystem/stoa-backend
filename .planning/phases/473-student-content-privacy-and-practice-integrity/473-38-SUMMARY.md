---
phase: 473-student-content-privacy-and-practice-integrity
plan: 38
subsystem: notification-delivery-security
tags: [dynamodb, strong-read, sealed-classification, websocket, privacy, pytest]

# Dependency graph
requires:
  - phase: 473-37
    provides: Crash-safe delivery intent claim/begin state machine and provider-neutral replay
  - phase: 473-34
    provides: Notification ownership envelope, account fence, and outbound intent retention boundary
provides:
  - Strong canonical event loading and closed authoritative legacy target-owner resolution
  - Immutable persisted global-nonprivate classification with exact content digest and contract allowlist
  - Unified digest, push, and per-connection WebSocket delivery over Plan 473-37 intent fencing
  - Stable fail-closed outcomes for malformed, stale, mixed, unresolved, and deletion-raced scope
affects: [473-39, 473-40, V9PRIV-02, notification-delivery, websocket]

# Tech tracking
tech-stack:
  added: []
  patterns: [strong base-key resolution, sealed ownerless exception, stable per-effect intent identity]

key-files:
  created:
    - tests/test_phase473_private_delivery_fencing.py
  modified:
    - src/stoa/db/repositories/notification_repo.py
    - src/stoa/services/notification_service.py
    - src/stoa/services/websocket_service.py
    - tests/test_notifications.py
    - tests/test_websocket_notifications.py

key-decisions:
  - "Provider delivery trusts only the strongly loaded persisted event; caller owner, generation, recipient, actor, role, metadata, and booleans never broaden scope."
  - "Ownerless delivery is an immutable repository-sealed global row whose exact contract, payload allowlist, event version, and classification digest are rechecked in the begin transaction."
  - "WebSocket fanout uses one stable intent per canonical event and redacted connection identity, so every provider post has an independent crash-safe ambiguity boundary."

patterns-established:
  - "Authoritative delivery: strong event read -> closed scope resolution -> stable operation digest -> Plan 473-37 claim/begin -> provider effect."
  - "Legacy delivery: exact target-family base-key read plus current positive account fence, with no metadata or recipient fallback."

requirements-completed: [V9PRIV-02]

# Metrics
duration: 21min
completed: 2026-07-18
---

# Phase 473 Plan 38: Authoritative Private Delivery And Sealed Global Exception Summary

**Strong persisted-event ownership, immutable sealed-global classification, and stable per-effect intent fencing now protect every digest, push, and WebSocket provider mutation from malformed metadata and account-deletion races**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-18T15:34:53Z
- **Completed:** 2026-07-18T15:56:06Z
- **Tasks:** 3
- **Files modified:** 6 implementation/test files plus this summary

## Accomplishments

- Added an exact strongly consistent event loader and a closed legacy resolver registry for question, moderation, report, assignment, learning, recommendation, and subscription targets.
- Added `AuthoritativeDeliveryOwnership`, stable scope/event-set digests, mixed-batch refusal, and provider-neutral fail-closed statuses.
- Replaced inferred ownerless delivery with an immutable repository-written global contract, payload allowlist, event version, and canonical classification digest.
- Removed digest and push direct-provider fallback; both channels now discard caller scope/payload facts and use the canonical persisted event through Plan 473-37 registration, recovery, claim, and begin.
- Replaced WebSocket `leased=False` fanout with one intent per redacted connection effect after authoritative scope resolution and before every post.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing authoritative-owner, sealed-global, and deletion-race delivery tests** — `df5675f` (test, RED)
2. **Task 2: Resolve one authoritative persisted delivery scope and fence digest/push** — `dfcdea6` (feat, GREEN)
3. **Task 3: Fence every WebSocket post with the same authoritative intent primitive** — `7b1bc3f` (feat, convergence)

## Files Created/Modified

- `tests/test_phase473_private_delivery_fencing.py` — Strong-read, malformed/stale generation, closed legacy resolver, sealed-global, mixed digest, and pre-list WebSocket refusal matrix.
- `src/stoa/db/repositories/notification_repo.py` — Strong event read, sealed global contract/digest, immutable ownerless rows, and begin-time event classification conditions.
- `src/stoa/services/notification_service.py` — Closed ownership resolver registry, authoritative delivery batch/adapter, stable operation identity, and digest/push rewiring.
- `src/stoa/services/websocket_service.py` — Strong pre-list resolution and independent intent-fenced provider posts with redacted connection evidence.
- `tests/test_notifications.py` — Canonical persisted-event fakes and provider-neutral digest/push expectations.
- `tests/test_websocket_notifications.py` — Canonical event lower fake, stable per-effect adapter, and redacted fanout evidence expectations.

## Decisions Made

- Kept legacy resolution closed to exact target families and base-table keys; direct-recipient legacy rows do not gain authority from recipient, actor, role, or metadata.
- Required current private events to carry exact `private_owner`, positive integer generation, and positive event version; malformed values do not fall back to legacy inference.
- Made sealed-global rows immutable and skipped per-event mutable attempt metadata for them; durable delivery intents remain the authoritative effect evidence.
- Bound digest operations to the canonical ordered event/version set and bound WebSocket effects to a domain-separated digest of the connection identity without persisting raw endpoints or connection IDs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Tooling Bug] Repaired state and roadmap progress projection**
- **Found during:** Plan metadata update
- **Issue:** The registered progress handlers wrote `percent: 10`, left Plan 38 status text stale, and replaced the four-column Phase 473 execution-order row with `38/40 | In Progress` cells while leaving the Plan 38 checkbox unchecked.
- **Fix:** Restored the state to 60/62 plans and 97%, advanced the visible position to Plan 39, preserved the execution-order row semantics, updated Phase 473 to 38/40, and checked only Plan 38.
- **Files modified:** `.planning/STATE.md`, `.planning/ROADMAP.md`
- **Verification:** State position/session/metric and roadmap row/checkbox agree with 38 summaries on disk; Plans 39-40 remain unchecked.

---

**Total deviations:** 1 auto-fixed (1 tooling bug)
**Impact on plan:** Metadata-only correction; no Plan 39 implementation or inventory refresh was performed.

## Verification

- **RED:** 12 behavioral tests failed; pytest exited exactly `1` with no collection/import errors.
- **Task 2 focused GREEN:** 21 passed, 12 deselected; targeted Ruff passed.
- **Task 2 broader non-WebSocket gate:** 48 passed, 2 deselected; targeted Ruff passed.
- **Task 3 focused WebSocket gate:** 18 passed; targeted Ruff passed.
- **Exact combined Plan 38 gate:** 56 passed; targeted Ruff passed; `git diff --check` passed.
- **Full repository suite:** 1,957 passed, 2 failed. Both failures are the acknowledged checked source-inventory drift owned by Plan 473-39; no functional test failed and no inventory was refreshed.

## Issues Encountered

- The `gsd-tools` shim was not on `PATH`; the checked GSD CLI was invoked through Node at `/Users/zhdeng/.codex/get-shit-done/bin/gsd-tools.cjs`.
- The full-suite inventory generators correctly named the Plan 36-38 mutating sources as drift. The user explicitly chose to continue, and Plan 473-39 owns their reviewed refresh.

## Authentication Gates

None.

## Known Stubs

None. Empty collections and `None` values found by the stub scan are deliberate negative state, optional parameters, or accumulator initialization; no provider path is unwired.

## User Setup Required

None - no dependency installation, provider credentials, external mutation, or deployment was required.

## Next Phase Readiness

- Plan 473-39 can now refresh and review the source-sealed inventories for the exact Plan 36-38 mutating source set.
- Plan 473-40 remains blocked until that inventory refresh is complete; no Plan 39 or later work was executed here.

## TDD Gate Compliance

- RED commit: `df5675f`
- GREEN commit: `dfcdea6`
- WebSocket convergence commit: `7b1bc3f`

## Self-Check: PASSED

- All six implementation/test artifacts and this summary exist.
- Task commits `df5675f`, `dfcdea6`, and `7b1bc3f` exist in repository history.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
