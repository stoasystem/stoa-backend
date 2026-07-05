# Phase 259 Plan: Notification And Support Provider Smoke Operations

## Objective

Make notification and support-provider activation status verifiable through a single admin-facing smoke report.

## Tasks

1. Add notification/support readiness aggregation to the external activation service.
2. Add an admin-only endpoint for the new smoke report.
3. Add focused tests for blocked, configured/read-only, and admin-only behavior.
4. Record verification evidence and update milestone tracking.

## Verification

- Run focused external activation, notification, WebSocket, and support-provider tests.
- Run Ruff on touched source and test files.
- Confirm customer-impacting sends remain disabled unless explicit provider flags are present.
