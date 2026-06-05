# Phase 40: Admin Export UI And Read-only Smoke

**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Status:** Complete
**Created:** 2026-06-05

## Goal

Expose the Phase 39 metadata-only recovery evidence export backend in the admin report operations UI and verify the path remains read-only and privacy-safe.

## Requirements

- UI-01: read-only admin evidence export UI on `/admin/report-operations`.

## Scope

- Add frontend API types and service call for `GET /admin/reports/recovery-evidence`.
- Add React Query mutation hook for evidence export.
- Add export controls to `/admin/report-operations`.
- Support selected-job export and recent-jobs export.
- Support copy/download of metadata-only JSON.
- Extend Playwright e2e to cover export controls and privacy-boundary assertions.

## Non-goals

- No backend mutation changes.
- No production mutation.
- No production browser smoke; Phase 41 owns production read-only smoke after release gate evidence is assembled.
- No support ticket integration.
- No report editing or WORM audit.

## Frontend Commit

- Repository: `/Users/zhdeng/stoa-frontend`
- Commit: `12e2ab6f148447b3b59044de332a1908d1353c9a`
- Message: `feat: add recovery evidence export UI`
