---
phase: 473-student-content-privacy-and-practice-integrity
plan: 34
subsystem: notification-device-realtime-deletion
tags: [dynamodb-transactions, account-fence, notifications, websocket, push, privacy, tdd]
requires:
  - phase: 473-29
    provides: canonical permanent account fence and restartable deletion branch protocol
  - phase: 473-30
    provides: authoritative moderation ownership and deletion-generation lineage
  - phase: 473-33
    provides: post-wave25 green baseline and two-clean-epoch branch pattern
provides:
  - authoritative owner envelopes for notification, assistance, device, and realtime rows
  - durable digest, push, and WebSocket provider-send intents with immediate fence rechecks
  - strict notification/assistance tombstones and complete push/WebSocket credential revocation
  - restartable notification_device_realtime branch with minimized external-delivery policy facts
affects: [473-35, notifications, teacher-assistance, push-delivery, websocket, account-deletion]
tech-stack:
  added: []
  patterns:
    - private role broadcasts carry the authoritative student owner and exact permanent-fence generation
    - provider mutations use owner-partitioned intents and classify lost responses as non-retryable acceptance unknown
    - notification and realtime families prove quiescence only after two later clean strong scans
key-files:
  created:
    - tests/test_phase473_notification_deletion.py
  modified:
    - src/stoa/db/repositories/notification_repo.py
    - src/stoa/db/repositories/websocket_repo.py
    - src/stoa/services/notification_service.py
    - src/stoa/services/websocket_service.py
    - src/stoa/services/teacher_assistance_service.py
    - src/stoa/services/account_deletion_service.py
key-decisions:
  - Notification ownership is an internal owner envelope; recipient role, actor identity, and recipient absence never establish or waive student ownership.
  - Digest, push, and WebSocket effects claim one durable operation and recheck the exact active generation twice, including immediately before provider mutation.
  - Provider accepted and acceptance-unknown outcomes retain only operation, channel, time, and status policy facts and are never reported as purged external copies.
  - Notification, assistance, preference, token, delivery-intent, and connection discovery uses strong base-table pagination and two later clean epochs.
patterns-established:
  - Existing notification and connection updates require both the owner row and the exact canonical active fence.
  - Account deletion revokes endpoint/token usability before private content is replaced by a closed tombstone.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 14 min
completed: 2026-07-18
---

# Phase 473 Plan 34: Notification, Assistance, Device, and Realtime Deletion Closure Summary

Private notification broadcasts, assistance summaries, push credentials, WebSocket endpoints, and outbound delivery work now share the permanent account fence and converge through a restartable two-clean-epoch purge branch.

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-18T09:55:38Z
- **Completed:** 2026-07-18T10:09:35Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added closed row, writer, private-field, credential, tombstone, and external-retention registries across notification events, assistance seeds, preferences, push tokens, delivery intents, and WebSocket connections.
- Made private direct and role-broadcast events carry authoritative owner/generation envelopes; event, assistance, preference, token, and connection writers now lose atomically to the canonical account fence.
- Added durable owner-partitioned digest, push, and WebSocket delivery intents with claim leases, two active-fence checks, acceptance-unknown classification, and no blind retry after ambiguous provider responses.
- Registered `notification_device_realtime` with independent notification and connection cursors, item debt, strict content minimization, credential deletion, external policy-fact counts, restart behavior, and two later clean scans.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing notification-owner, provider-race, credential, and assistance purge tests** - `ea96383` (test)
2. **Task 2: Fence notification/device writers and add deletion-aware delivery leases** - `e79ce53` (feat)
3. **Task 3: Revoke devices and exhaustively scrub notification/assistance/delivery state** - `f61b622` (feat)

## Files Created/Modified

- `tests/test_phase473_notification_deletion.py` - RED/GREEN registries, exact fence builders, private-broadcast owner checks, provider races, strict raw tombstones, credential revocation, and later-zero branch proof.
- `src/stoa/db/repositories/notification_repo.py` - Fenced notification-family transactions, delivery-intent state machine, strong discovery, strict tombstones, and external-retention boundary.
- `src/stoa/db/repositories/websocket_repo.py` - Fenced connection lifecycle transactions, strong owner scans, and conditional account-deletion revocation.
- `src/stoa/services/notification_service.py` - Owner classification, owner propagation, digest/push delivery leases, exact pre-provider rechecks, and ambiguity-safe completion.
- `src/stoa/services/websocket_service.py` - Fenced connection registration and deletion-aware fanout claims/rechecks.
- `src/stoa/services/teacher_assistance_service.py` - Assistance seeds inherit the authorized question owner and exact fence generation.
- `src/stoa/services/account_deletion_service.py` - Independent notification/device/realtime purge handler with external-delivery policy substate and two-clean-epoch proof.

## Decisions Made

- Recipient absence means broadcast, not owner absence. Private question/moderation/report/assignment-derived notifications still carry the closing student's authoritative envelope.
- A claimed provider operation is not sufficient authorization: the worker performs one post-claim check and another check immediately adjacent to the outbound mutation.
- Provider exceptions after mutation are conservatively classified as `provider_acceptance_unknown`; the same operation is never blindly retried.
- Accepted or unknown provider-held copies are outside backend deletion authority. Only a provider-neutral receipt fact survives for Plan 35 composition.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Git metadata is read-only in the normal workspace sandbox. Required atomic commits used the approved escalated Git path with repository hooks enabled.

## Verification

- RED gate: seven intended assertion failures, pytest exit code exactly 1, with no collection or import failure.
- Task 2 focused gate: 21 selected owner/broadcast/writer/fence/digest/push/WebSocket/lease tests passed; 13 were intentionally deselected.
- Final focused gate: 34 tests passed across notification deletion, notifications, assistance coverage, and WebSocket notifications.
- Targeted Ruff passed across every Plan 473-34 source path; `git diff --check` passed.
- Full repository regression: 1819 tests passed.
- TDD order is present in Git history: `ea96383` precedes `e79ce53` and `f61b622`.

## Known Stubs

None.

## Threat Flags

No unplanned security surface was introduced. The new provider-send intent path is the delivery trust boundary explicitly covered by T-473-34-03.

## User Setup Required

None - no package, configuration, provider, or external-service change is required.

## Next Phase Readiness

- Plan 35 can compose the `notification_device_realtime` branch and its accepted/unknown external-delivery policy facts while retaining sole authority to seal and finalize the account deletion registry.
- External provider/client copy erasure remains explicitly outside backend control; no Plan 34 evidence overclaims it.
- No unresolved Plan 473-34 blocker remains.

## Self-Check: PASSED

- All seven created or modified delivery paths exist.
- Commits `ea96383`, `e79ce53`, and `f61b622` exist in repository history.
- All mandatory Plan 473-34 local verification gates pass from committed source.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
