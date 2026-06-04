---
phase: 29
phase_name: Frontend Production Deployment Verification
status: passed
verified: 2026-06-04
requirements:
  - REL-02
  - REL-03
  - LIVE-03
---

# Phase 29 Verification: Frontend Production Deployment Verification

## Verdict

`passed`

Phase 29 verifies that the production frontend route and deployed bundle include the admin report operations workflow, use the production API base URL, and do not expose private report artifact paths.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REL-02 | complete | `/Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml` builds with `VITE_API_MODE=production`, `VITE_API_BASE_URL=https://api.stoaedu.ch`, `VITE_ENABLE_DEMO_API=false`, `VITE_SHOW_DEMO_ACCOUNTS=false`, `VITE_SHOW_DEMO_BADGES=false`, and `VITE_SHOW_DEMO_SURFACES=false`; deploys to `stoa-frontend-562923011260`; and invalidates CloudFront distribution `E27CVAMQHDMW80`. |
| REL-03 | complete | Evidence records frontend SHA, production route headers, index.html timestamp/etag, production asset path, asset timestamp/etag, API URL, and local verification commands. |
| LIVE-03 | complete | `https://app.stoaedu.ch/admin/report-operations` returns HTTP 200 SPA HTML and references `/assets/index-DliuvgBM.js`; the production bundle contains `report-operations`, `retry-generation`, `bulk-resend`, and admin report API markers, and contains `https://api.stoaedu.ch`. Admin-authenticated browser click-through was not automated because no admin browser session/token was available in the current environment; local Playwright e2e covers the authenticated admin workflow and production bundle evidence proves the route is deployed. |

## Source State

| Repository | Status | SHA |
|------------|--------|-----|
| Frontend `/Users/zhdeng/stoa-frontend` | `## main...origin/main` | `1f4b88bfc93dea50c928502333f7e2b8084a12b4` |
| Backend `/Users/zhdeng/stoa-backend` | Phase 29 docs in progress during verification | `08223e76ad66747f5df79562661ca1a5c929757c` before Phase 29 commit |
| Infra `/Users/zhdeng/stoa-infra` | SHA recorded for release ledger | `2b9aba9bb0ea62d2a39082da0eb5d9ead163317a` |

## Deployment Workflow Evidence

`/Users/zhdeng/stoa-frontend/.github/workflows/deploy.yml` contains:

- `VITE_API_MODE: production`
- `VITE_API_BASE_URL: https://api.stoaedu.ch`
- `VITE_ENABLE_DEMO_API: "false"`
- `VITE_SHOW_DEMO_ACCOUNTS: "false"`
- `VITE_SHOW_DEMO_BADGES: "false"`
- `VITE_SHOW_DEMO_SURFACES: "false"`
- `aws s3 sync dist/ s3://stoa-frontend-562923011260/`
- `aws s3 cp dist/index.html s3://stoa-frontend-562923011260/index.html`
- `--distribution-id E27CVAMQHDMW80`

## Automated Checks

| Check | Result |
|-------|--------|
| `npm run build` from `/Users/zhdeng/stoa-frontend` | Passed. Vite emitted the existing chunk-size warning for `index-CNcAdHW0.js`. |
| `npm run lint` from `/Users/zhdeng/stoa-frontend` | Passed. |
| `npx playwright test tests/e2e/admin-report-operations.spec.ts` | Passed: 1 chromium test passed. |
| `git diff --check` from `/Users/zhdeng/stoa-backend` | Passed after Phase 29 docs update. |

## Production Route Evidence

`curl -I https://app.stoaedu.ch/admin/report-operations`:

- HTTP status: `HTTP/2 200`
- Content type: `text/html`
- `Last-Modified: Thu, 04 Jun 2026 16:01:42 GMT`
- `ETag: "ea5bde08ae8f0e08a71c09ccb23c2011"`
- `Cache-Control: no-cache,no-store,must-revalidate`
- Served by Amazon S3 through CloudFront.

Fetched HTML references:

- `/assets/index-DliuvgBM.js`
- `/assets/vendor-react-EQo9hmIT.js`
- `/assets/vendor-CLknepMi.js`
- `/assets/vendor-router-state-5t0JAZev.js`
- `/assets/vendor-ui-C1Nxz-Js.js`
- `/assets/vendor-http-DcNlVx-A.js`
- `/assets/vendor-i18n-DOhDEnRQ.js`
- `/assets/index-CBlTspVu.css`

`curl -I https://app.stoaedu.ch/assets/index-DliuvgBM.js`:

- HTTP status: `HTTP/2 200`
- Content type: `text/javascript`
- Content length: `654581`
- `Last-Modified: Thu, 04 Jun 2026 16:01:39 GMT`
- `ETag: "82a010cc1f0c6a122e2dcb6b1f5e4683"`
- `Cache-Control: public,max-age=31536000,immutable`
- `X-Cache: Hit from cloudfront`

## Production Bundle Evidence

Downloaded production asset:

- URL: `https://app.stoaedu.ch/assets/index-DliuvgBM.js`
- Local verification copy: `/tmp/stoa-prod-index-DliuvgBM.js`

Markers found:

- `report-operations`
- `retry-generation`
- `bulk-resend`
- `admin/report`
- `https://api.stoaedu.ch`

Privacy markers not found:

- `weekly-reports/`
- `json_s3_key`
- `html_s3_key`
- `presignedUrl`
- `s3.amazonaws.com`
- direct S3 weekly-report URL markers

## Residual Manual Evidence

Admin-authenticated browser click-through against production was not automated because no reusable admin browser session or token was available in this environment.

This is accepted as residual manual evidence rather than a blocker because:

- The production route serves the current deployed SPA bundle.
- The production bundle contains report operations route/action markers.
- The production bundle contains the production API base URL.
- Local Playwright e2e passed for the admin report operations workflow.
- No private artifact path or direct S3 markers were found in the production bundle.

## Residual Risks

- A human admin should still perform one production browser click-through before using the report operations UI for real support work.
- Backend authenticated API behavior is not covered here; it remains Phase 30 scope.
