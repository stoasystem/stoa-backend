# Phase 260 Plan: Production Deploy Readiness And Read-Only Browser Smoke

## Objective

Make production deploy and read-only smoke requirements explicit, repeatable, and no-mutation by default.

## Tasks

1. Add a production readiness smoke report to the external activation service.
2. Add an admin-only endpoint for the report.
3. Add focused tests for local/production classification, read-only route inventory, and admin-only behavior.
4. Record runbook/evidence artifacts and update milestone tracking.

## Verification

- Run focused external activation and release evidence tests.
- Run Ruff on touched files.
- Confirm the report contains no secrets, no raw provider payloads, and no mutation instructions without fixture/mode gates.
