---
phase: 163-retry-workers-and-two-way-ticket-synchronization
plan: 01
subsystem: support-operations
tags: [support-handoff, provider-adapters, retry, ticket-sync, admin-api]
requires:
  - phase: 162-approved-third-party-support-adapter-and-delivery-worker
    provides: approved third-party support delivery records and provider metadata
provides:
  - Admin-only bounded retry mutation for failed third-party support deliveries.
  - Provider-neutral ticket synchronization with duplicate, stale, unknown, and conflict handling.
  - Queue/detail response metadata for retry state, sync freshness, provider status, and conflicts.
affects: [support-provider, support-handoff, admin-report-operations]
tech-stack:
  added: []
  patterns: [bounded provider retries, metadata-only provider sync, conflict-marked lifecycle updates]
key-files:
  created: []
  modified:
    - src/stoa/db/repositories/report_repo.py
    - src/stoa/routers/admin.py
    - src/stoa/services/support_destination_service.py
    - tests/test_admin_report_ops.py
key-decisions:
  - "Implement retry and sync as admin API mutations over existing support handoff delivery records."
  - "Keep provider synchronization provider-neutral and store only normalized metadata."
  - "Surface duplicate provider events in responses without persisting a redundant update."
patterns-established:
  - "Provider retry attempts are bounded by `MAX_PROVIDER_RETRY_ATTEMPTS` and expose exhaustion metadata."
  - "Provider sync conflicts use `sync_conflict` status plus redacted operator-visible reasons."
requirements-completed: [SUPPORTPROV-03]
duration: 38min
completed: 2026-06-12
---

# Phase 163: Retry Workers And Two-Way Ticket Synchronization Summary

**Failed provider deliveries can now be retried safely, and provider ticket status updates can be synchronized without storing raw provider payloads.**

## Performance

- **Duration:** 38 min
- **Started:** 2026-06-12T13:35:00Z
- **Completed:** 2026-06-12T14:13:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added repository support for delivery status updates with extra provider metadata.
- Added admin-only retry endpoint for failed `third_party_support` deliveries with attempt count, retry exhaustion, retryability, retry timestamps, and audit events.
- Added provider-neutral sync endpoint for ticket status updates with normalized lifecycle mapping.
- Added duplicate event detection, stale update refusal, unknown status conflicts, and terminal-state conflict protection.
- Extended delivery responses with retry and sync fields used by admin queue/detail views.
- Added focused tests for retry success, retry exhaustion, admin-only access, sync success, duplicate events, stale events, and unknown provider statuses.

## Task Commits

1. **Tasks 1-3: Retry mutation, provider sync, and focused tests** - `b65e2c0` (feat)
2. **Code review fix: surface duplicate sync events and route body default** - `8ecdbf8` (fix)

**Plan metadata:** pending in the metadata commit that adds this SUMMARY.

## Files Created/Modified

- `src/stoa/db/repositories/report_repo.py` - Allows delivery status updates to persist additional provider retry/sync metadata.
- `src/stoa/routers/admin.py` - Adds retry and provider sync admin endpoints.
- `src/stoa/services/support_destination_service.py` - Adds retry, sync normalization, conflict handling, audit writes, and response metadata.
- `tests/test_admin_report_ops.py` - Adds focused retry and sync coverage.

## Decisions Made

- Used admin API mutations as the local worker surface so webhook and polling adapters can call the same normalized service behavior later.
- Stored provider event IDs as a bounded list on delivery records for duplicate detection.
- Treated stale, unknown, and locally conflicting provider updates as explicit `sync_conflict` states.
- Returned duplicate sync events as `last_sync_result=duplicate` without writing a redundant repository update.

## Deviations from Plan

None - plan executed within scope.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- Advisory code review found duplicate provider events were ignored but not surfaced in the response. Fixed in `8ecdbf8`.
- Advisory code review replaced a Pydantic model instance route default with an optional request body default. Fixed in `8ecdbf8`.

## User Setup Required

None for local retry/sync behavior. Real provider webhook or polling adapters can call the new admin sync surface once external provider credentials and routing are approved.

## Verification

- `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` -> 41 passed, 85 deselected.
- `./.venv/bin/ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py src/stoa/services/support_destination_service.py tests/test_admin_report_ops.py` -> all checks passed.
- Advisory code review: `163-REVIEW.md` -> clean after remediation.

## Next Phase Readiness

Phase 164 can build CRM automation and customer timeline stitching on top of provider retry/sync metadata, provider lifecycle status, conflict markers, and audit history.

---
*Phase: 163-retry-workers-and-two-way-ticket-synchronization*
*Completed: 2026-06-12*
