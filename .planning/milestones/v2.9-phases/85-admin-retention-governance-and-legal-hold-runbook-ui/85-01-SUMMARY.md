# Summary: Phase 85 Admin Retention Governance And Legal Hold Runbook UI

**Phase:** 85
**Milestone:** v2.9 Retention Governance And Legal Hold Operations
**Status:** Complete
**Completed:** 2026-06-07

## Completed

- Added frontend API types/client functions for governance status, retention approval metadata, and legal-hold review metadata.
- Added React Query mutation hooks for the new governance endpoints.
- Extended `/admin/report-operations` immutable evidence panel with retention governance controls:
  - policy version and approval state;
  - owner, approver, review due date, and approval reason;
  - legal-hold review owner, reviewer, due date, and reason;
  - check governance, record approval, and record review actions.
- Added readback rows for retention approval state and legal-hold review state.
- Included governance approval/review payloads in copy/download evidence behavior.
- Extended Playwright coverage for route mocks, visible governance results, and privacy marker assertions.

## Frontend Commit

- `stoa-frontend` commit `b88c673 feat(85): add retention governance admin controls`.

## Verification

- `npm run lint` — passed.
- `npm run build` — passed.
- `npx playwright test tests/e2e/admin-report-operations.spec.ts` — passed.
- In-app Browser visual check was attempted, but Chromium launch from the MCP process was blocked by macOS Mach port permissions. The normal Playwright runner passed the targeted page workflow.

## Production Safety

No production deploy, production mutation, audit deletion, immutable object deletion, customer report artifact mutation, or external support-system write was performed.
