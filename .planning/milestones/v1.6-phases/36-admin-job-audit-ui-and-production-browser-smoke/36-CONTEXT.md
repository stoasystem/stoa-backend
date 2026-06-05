# Phase 36 Context: Admin Job/Audit UI And Production Browser Smoke

**Milestone:** v1.6 Report Recovery Operations Hardening
**Date:** 2026-06-05
**Status:** In progress

## Goal

Admins need a usable UI for async report recovery jobs and audit timelines, then a read-only production browser smoke proving route, auth, and privacy behavior.

## Starting Point

Phase 35 added backend APIs for async resend job preview/create/list/detail/results/cancel, report-local audit, and job-local audit. The existing frontend page `AdminReportOperationsPage` only supported report triage, single resend/retry, and selected synchronous bulk resend.

## Constraints

- Keep the admin workflow inside the existing `/admin/report-operations` surface.
- Do not expose private S3 keys, raw report JSON/HTML, presigned URLs, or auth tokens.
- Production browser smoke must use a real existing admin session or approved secret-backed credential path.
- Production browser smoke cannot be completed until the frontend/backend changes are deployed and an admin credential/session path is available.

## Implementation Notes

- Frontend commit: `d5ae3d7 feat: add report recovery jobs admin UI`.
- UI work adds async resend preview/start controls, job list/results/cancel controls, report audit timeline, and job audit timeline.
- Playwright e2e now covers preview/create/results/audit/cancel with metadata-only privacy assertions.
