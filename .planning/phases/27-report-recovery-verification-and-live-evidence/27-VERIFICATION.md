---
phase: 27
phase_name: Report Recovery Verification and Live Evidence
status: passed
verified: 2026-06-04
requirements:
  - SEC-01
  - SEC-02
  - VER-01
  - VER-02
  - VER-03
---

# Phase 27 Verification: Report Recovery Verification and Live Evidence

## Verdict

`passed`

Phase 27 closes the report operations workflow with backend tests, frontend e2e coverage, and live deployment evidence.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SEC-01 | complete | Backend tests cover non-admin rejection for list, detail, retry generation, single resend, and bulk resend. Live unauthenticated `/admin/reports/ops` returns HTTP 401. |
| SEC-02 | complete | Backend tests and frontend e2e assert report operations responses/UI do not expose raw HTML, private artifact paths, S3 key fields, presigned URL markers, or direct S3 URL markers. |
| VER-01 | complete | Focused backend suite covers list/detail access, status filtering, generation retry, single resend, bulk resend, per-item results, audit fields, privacy, and non-admin rejection. |
| VER-02 | complete | Playwright e2e covers admin navigation, filters, list states, detail inspection, action eligibility, single resend result, bulk selection, bulk result rendering, and privacy markers. |
| VER-03 | complete | Live evidence records deployed API/Lambda state, frontend SPA route behavior, API health, admin auth gate behavior, and CDK diff; production mutation smoke was intentionally not run without a safe target. |

## Automated Checks

- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 89 passed.
- `uv run ruff check src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` - passed.
- `npm run build` - passed.
- `npm run lint` - passed.
- `npx playwright test tests/e2e/admin-report-operations.spec.ts` - 1 passed.

## Live Checks

| Check | Result |
|-------|--------|
| AWS profile `stoa` identity | `562923011260`, AdministratorAccess SSO role. |
| `stoa-api` Lambda config | Active, LastUpdateStatus Successful, python3.12, reports bucket env set. |
| `stoa-weekly-report` Lambda config | Active, LastUpdateStatus Successful, python3.12, reports bucket env set. |
| API `/health` | HTTP 200 body `{"status":"ok","version":"0.1.0"}`. |
| API `/admin/reports/ops` without token | HTTP 401 Unauthorized. |
| Frontend `/admin/report-operations` | HTTP 200 text/html through SPA path handling. |
| CDK diff | One stack with differences: expected Lambda code asset hash updates in `StoaApiStack`; no infra/policy drift elsewhere. |

## Privacy Evidence

Backend and frontend tests check absence of:

- raw report HTML
- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `presignedUrl`
- direct S3 URL markers

## Residual Risks

- Frontend route is implemented and locally/e2e verified, but the live frontend asset last-modified timestamp indicates the new bundle has not been deployed during this phase.
- No production retry/resend mutation was executed because no approved safe failed report target was available.
