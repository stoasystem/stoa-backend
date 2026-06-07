# Phase 85 Context: Admin Retention Governance And Legal Hold Runbook UI

**Milestone:** v2.9 Retention Governance And Legal Hold Operations
**Status:** Complete
**Created:** 2026-06-07

## Why This Phase Exists

Phase 84 added backend metadata operations for retention approval and legal-hold review evidence. Phase 85 exposes those operations in the existing admin report-operations UI so operators can inspect governance state, record approval metadata, record review evidence, and copy/download metadata-only payloads.

## Inputs

- Phase 83 governance contract, approval packet, and runbook specification.
- Phase 84 backend endpoints:
  - `POST /admin/reports/retention-governance/status`
  - `POST /admin/reports/retention-governance/approval`
  - `POST /admin/reports/legal-holds/review`
- Existing frontend immutable evidence and legal-hold controls in `stoa-frontend/src/pages/admin/ReportOperationsPage.tsx`.

## Non-Negotiable Boundaries

- UI must render allowlisted governance metadata only.
- UI must keep inspection separate from state-changing actions.
- UI must require operator reason fields for approval/review writes.
- UI must not render raw artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets.

## Output

Phase 85 completes when frontend API types, hooks, panel controls, and e2e coverage exist for retention governance and legal-hold review workflows.
