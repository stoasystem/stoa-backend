---
phase: 164-support-sla-analytics-and-controlled-crm-messaging
plan: 01
subsystem: support-operations
tags: [support-handoff, sla-analytics, crm-messaging, admin-api]
requires:
  - phase: 163-retry-workers-and-two-way-ticket-synchronization
    provides: retry state, provider sync metadata, and conflict markers
provides:
  - Metadata-only support SLA analytics for delivery lifecycle and provider health.
  - Controlled CRM/customer message evidence for approved templates and destinations.
  - Admin endpoints for SLA analytics and support-message outcome recording.
affects: [support-provider, support-handoff, admin-report-operations, crm-messaging]
tech-stack:
  added: []
  patterns: [metadata-only analytics, fail-closed messaging approval, message outcome evidence]
key-files:
  created:
    - src/stoa/services/support_sla_service.py
  modified:
    - src/stoa/config.py
    - src/stoa/db/repositories/report_repo.py
    - src/stoa/routers/admin.py
    - tests/test_admin_report_ops.py
key-decisions:
  - "Implement SLA analytics as a bounded read over existing support handoff delivery summaries."
  - "Persist controlled message outcomes as metadata-only events correlated to support deliveries."
  - "Keep local CRM/customer messaging as evidence recording only unless destination and template approval are configured."
patterns-established:
  - "Support message sends, refusals, and failures share one redacted evidence shape."
  - "SLA analytics include lifecycle counts, overdue references, provider failure rate, retry backlog, sync conflicts, and message outcome counts."
requirements-completed: [SUPPORTPROV-04]
duration: 42min
completed: 2026-06-12
---

# Phase 164: Support SLA Analytics And Controlled CRM Messaging Summary

**Support operations now have metadata-only SLA analytics and controlled CRM/customer message evidence tied to support handoff deliveries.**

## Performance

- **Duration:** 42 min
- **Started:** 2026-06-12T14:13:00Z
- **Completed:** 2026-06-12T14:55:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added `support_sla_service` for support lifecycle analytics, overdue classification, provider failure rate, retry backlog, sync conflict counts, and message outcome counts.
- Added metadata-only CRM/customer message event persistence and recent message outcome listing.
- Added fail-closed CRM messaging settings for approval, destination approval, approved templates, opt-outs, and simulated provider failure.
- Added `GET /admin/reports/support-handoff-sla` for admin SLA analytics.
- Added `POST /admin/reports/support-handoff-deliveries/{delivery_id}/messages` for controlled template-gated message outcome evidence.
- Added focused tests for SLA aggregation, overdue classification, provider failure analytics, approved send, unapproved refusal, opt-out refusal, provider failure, and admin-only access.

## Task Commits

1. **Tasks 1-3: SLA analytics, controlled message evidence, admin endpoints, and tests** - `ebedee8` (feat)

**Plan metadata:** pending in the metadata commit that adds this SUMMARY.

## Files Created/Modified

- `src/stoa/services/support_sla_service.py` - Adds SLA analytics and controlled message outcome service behavior.
- `src/stoa/config.py` - Adds fail-closed support CRM messaging settings.
- `src/stoa/db/repositories/report_repo.py` - Adds metadata-only support CRM message event persistence/listing helpers.
- `src/stoa/routers/admin.py` - Adds SLA analytics and support message endpoints.
- `tests/test_admin_report_ops.py` - Adds focused Phase 164 tests.

## Decisions Made

- Did not add a real CRM/email transport in this phase; the endpoint records approved/refused/failed message evidence only.
- Used existing support handoff delivery records as the source of SLA truth.
- Represented customer opt-out as request/config metadata so tests can prove refusal behavior without adding a customer-preferences subsystem.
- Counted provider failures from third-party delivery failure status, provider error code, or failed provider result.

## Deviations from Plan

None - plan executed within scope.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

None.

## User Setup Required

Controlled message sends remain refused by default. To enable local approved-message evidence:

- `SUPPORT_CRM_MESSAGING_APPROVED=true`
- `SUPPORT_CRM_DESTINATION_APPROVED=true`
- Optional `SUPPORT_CRM_APPROVED_TEMPLATES=support_receipt,status_update,resolution,escalation`

## Verification

- `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` -> 48 passed, 85 deselected.
- `./.venv/bin/ruff check src/stoa/config.py src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py src/stoa/services/support_sla_service.py tests/test_admin_report_ops.py` -> all checks passed.
- Advisory code review: `164-REVIEW.md` -> clean.

## Next Phase Readiness

Phase 165 can close v4.8 with release-gate evidence across provider readiness, delivery, retry/sync, SLA analytics, controlled messaging, docs, and next-milestone selection.

---
*Phase: 164-support-sla-analytics-and-controlled-crm-messaging*
*Completed: 2026-06-12*
