# Phase 374 Context

## Phase Boundary

Phase 374 verifies or explicitly disables notification, support, mobile, provider, BI/APM, and AI/provider dependencies needed for a narrow pilot.

## Decisions

- Disabled pilot dependencies need fallback, rollback control, support copy, and owner assignment.
- Email, push, realtime notification, support CRM, support queue, teacher SLA, mobile/TestFlight, payment provider, BI/APM, and AI/provider states are tracked separately.
- Missing provider evidence blocks the pilot unless the surface is explicitly disabled for pilot scope.

## Existing Code Insights

- Existing provider activation helpers already use disabled/read-only/live evidence classifications.
- v6 adds broader support and provider fallback mapping for first-cohort evidence.
