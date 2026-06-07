# Phase 68: Admin Support Handoff UI - Context

**Gathered:** 2026-06-07
**Status:** Ready for implementation
**Mode:** Autonomous from Phase 67 API

<domain>
## Phase Boundary

Phase 68 adds admin report operations UI controls for backend support handoff packages. Admins can preview package metadata, copy copy-ready handoff text, download JSON, and see direct external write refusal without writing to third-party systems.

The phase must stay inside `/admin/report-operations`, preserve the existing dense admin operations layout, and never render private artifact markers.
</domain>

<decisions>
## Implementation Decisions

### UI Scope

- Add a support handoff panel near existing recovery evidence and release evidence automation controls.
- Reuse current selected recovery job, release evidence input, and safe-fixture name state where possible.
- Provide destination controls for `preview`, `copy`, `download`, and refused `external_write`.
- Display package status, validation status, evidence refs, section names, copy/download affordances, and refusal reasons.

### API Usage

- Call `POST /admin/reports/support-handoff-package`.
- Use `recovery_job_ids` from the selected recovery job when available.
- Include release evidence JSON only when the operator opts into it and the JSON parses successfully.
- Include fixture reference from the existing approved fixture name.
- Send operator note/reason as free text and rely on backend redaction.

### Safety

- UI must not perform direct third-party writes.
- UI must not render S3 keys, presigned URLs, raw report JSON/HTML, auth tokens, or raw artifact payloads.
- Tests should mock the backend route and assert privacy denylist absence in page text.
</decisions>

<code_context>
## Frontend Code Context

- Main page: `/Users/zhdeng/stoa-frontend/src/pages/admin/ReportOperationsPage.tsx`.
- Admin API client: `/Users/zhdeng/stoa-frontend/src/services/admin/adminApi.ts`.
- React Query hooks: `/Users/zhdeng/stoa-frontend/src/hooks/admin/useAdminReportOperations.ts`.
- E2E coverage: `/Users/zhdeng/stoa-frontend/tests/e2e/admin-report-operations.spec.ts`.
- Existing page already exposes recovery evidence export, support package JSON for one recovery job, release evidence validation, and fixture status panels.
</code_context>

<deferred>
## Deferred Ideas

- Direct Zendesk/Intercom/Jira/Linear writes.
- Credential configuration UI.
- Long-term retention controls.
- Support package history browser.
</deferred>
